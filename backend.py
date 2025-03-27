# backend.py
import io
import zipfile
import fitz  # PyMuPDF - Used for PDF text extraction
import google.generativeai as genai
from docx import Document
from docx.shared import Pt  # Optional: For setting font size
from docx.enum.text import WD_ALIGN_PARAGRAPH  # Import alignment enum for clarity
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Use a specific logger if preferred

# --- PDF Processing ---
def extract_text_from_pdf(pdf_file_obj):
    """
    Extracts text from a PDF file object using PyMuPDF (fitz), respecting CropBox.
    Args:
        pdf_file_obj: A file-like object representing the PDF.
    Returns:
        str: The extracted text, or None if extraction fails.
    """
    try:
        # PyMuPDF works with bytes, so read the file object's content
        pdf_bytes = pdf_file_obj.read()
        text = ""
        # Open the PDF from bytes
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            logger.info(f"Opened PDF with PyMuPDF. Number of pages: {len(doc)}")
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Extract text respecting the page's effective area (incl. CropBox)
                # sort=True attempts to maintain reading order
                page_text = page.get_text("text", sort=True)
                if page_text:
                    text += page_text + "\n"  # Add newline between pages

        logger.info(f"Successfully extracted text using PyMuPDF.")
        # Basic check if extraction yielded *any* text
        if not text.strip():
            logger.warning("PyMuPDF extraction resulted in empty text. PDF might be image-based or lack text content.")
            # Return empty string instead of None to avoid downstream errors expecting a string
            return ""
        return text
    except Exception as e:
        # Catch fitz-specific errors or general exceptions
        logger.error(f"Error extracting text from PDF using PyMuPDF: {e}", exc_info=True) # Log traceback
        return None  # Indicate failure clearly


# --- Gemini Processing ---
def process_text_with_gemini(api_key: str, model_name: str, raw_text: str, rules_prompt: str):
    """
    Processes raw text using the Gemini API based on provided rules.
    Args:
        api_key (str): The Gemini API key.
        model_name (str): The Gemini model name (e.g., 'gemini-1.5-flash-latest').
        raw_text (str): The raw text extracted from the PDF.
        rules_prompt (str): User-defined rules/instructions for Gemini.
    Returns:
        str: The processed text from Gemini, or an error string if an error occurs.
    """
    if not api_key:
        logger.error("Gemini API key is missing.")
        # Return an error string that can be displayed in the UI
        return "Error: Gemini API key is missing."
    # Check specifically for empty string OR None if extract_text_from_pdf returns None on error
    if not raw_text:
        logger.warning("Skipping Gemini call: No raw text provided.")
        # Return empty string if raw_text was empty, consistent with extract_text_from_pdf
        # If raw_text was None (extraction failed), maybe return an error or None?
        # For consistency with the flow where empty text leads to empty docx, return ""
        return ""

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)

        # Construct a clear prompt for Gemini
        full_prompt = f"""
        **Instructions:**
        {rules_prompt}

        **Arabic Text to Process:**
        ---
        {raw_text}
        ---

        **Output:**
        Return ONLY the processed text according to the instructions. Do not add any introductory phrases like "Here is the processed text:". Ensure the output is purely the processed Arabic content.
        """

        logger.info(f"Sending request to Gemini model: {model_name}")
        # Add safety settings to potentially allow more content if needed, adjust as necessary
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        # Consider making generation_config configurable (temperature, top_p, etc.) if needed
        generation_config = genai.types.GenerationConfig(
            # candidate_count=1, # Default is 1
            # stop_sequences=["\n\n\n"], # Example stop sequence
            # max_output_tokens=8192, # Model dependent, adjust if needed
            temperature=0.7, # Adjust creativity vs factualness
        )

        response = model.generate_content(
            full_prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
            )

        # Enhanced Response Handling
        try:
            # Access text via response.text, handles potential errors internally in the library
            processed_text = response.text
            logger.info("Successfully received response from Gemini.")
            return processed_text

        except ValueError as ve:
            # Raised if the response payload is problematic (e.g., function calls not expected)
             logger.error(f"Gemini response format issue (ValueError): {ve}", exc_info=True)
             # Check for blocking/safety issues in prompt_feedback
             if response.prompt_feedback.block_reason:
                 block_reason = response.prompt_feedback.block_reason
                 logger.error(f"Gemini request potentially blocked. Reason: {block_reason}")
                 return f"Error: Content blocked by Gemini. Reason: {block_reason}"
             else:
                 return f"Error: Gemini response format issue (ValueError). Details: {ve}"
        except Exception as resp_err:
             # Catch other potential errors during response processing
             logger.error(f"Error processing Gemini response: {resp_err}", exc_info=True)
             return f"Error: Failed to parse Gemini response. Details: {resp_err}"


    # Handle potential API call errors, configuration errors etc.
    except google.api_core.exceptions.PermissionDenied as perm_denied:
         logger.error(f"Gemini API Permission Denied (check API Key permissions): {perm_denied}", exc_info=True)
         return f"Error: Gemini API Permission Denied. Check your API key and its permissions. Details: {perm_denied}"
    except google.api_core.exceptions.GoogleAPIError as api_err:
         logger.error(f"Gemini API Error: {api_err}", exc_info=True)
         return f"Error: Gemini API communication failed. Details: {api_err}"
    except Exception as e:
        logger.error(f"General error interacting with Gemini API: {e}", exc_info=True)
        # Provide a user-friendly error string
        return f"Error: Failed to process text with Gemini. Details: {e}"


# --- Word Document Creation ---
def create_word_document(processed_text: str):
    """
    Creates a Word document (.docx) in memory containing the processed text.
    Sets text direction to RTL, alignment to right, and uses Arial font.
    Args:
        processed_text (str): The text to put into the document.
    Returns:
        io.BytesIO: A BytesIO stream containing the Word document data, or None on error.
    """
    try:
        document = Document()
        # Add a paragraph
        paragraph = document.add_paragraph()

        # 1. Set Paragraph Formatting (Alignment and Base Direction)
        paragraph_format = paragraph.paragraph_format
        paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT # Use enum for clarity
        paragraph_format.right_to_left = True

        # 2. Add Text as a Run
        # Ensure processed_text is a string, handle potential None (though Gemini func aims to return string)
        text_to_add = processed_text if isinstance(processed_text, str) else ""
        run = paragraph.add_run(text_to_add)

        # 3. Set Font Formatting for the Run
        font = run.font
        font.name = 'Arial'  # Good choice for Arabic support
        # Explicitly tell the font to handle RTL script characteristics
        font.rtl = True
        # Optional: Set font size if desired
        # font.size = Pt(12)

        # Save document to a BytesIO stream
        doc_stream = io.BytesIO()
        document.save(doc_stream)
        doc_stream.seek(0) # Rewind the stream to the beginning
        logger.info("Successfully created Word document in memory with RTL settings.")
        return doc_stream
    except Exception as e:
        logger.error(f"Error creating Word document: {e}", exc_info=True) # Log traceback
        return None

# --- Zipping Files ---
def create_zip_archive(files_data: list):
    """
    Creates a Zip archive in memory containing multiple files.
    Args:
        files_data (list): A list of tuples, where each tuple is
                           (filename_str, file_bytes_io_obj).
    Returns:
        io.BytesIO: A BytesIO stream containing the Zip archive data, or None on error.
    """
    if not files_data:
        logger.warning("No files provided to create zip archive.")
        return None
    try:
        zip_stream = io.BytesIO()
        # Use ZIP_DEFLATED for compression
        with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename, file_stream in files_data:
                if not isinstance(filename, str) or not hasattr(file_stream, 'read'):
                    logger.warning(f"Skipping invalid data entry in files_data: ({filename}, {type(file_stream)})")
                    continue
                try:
                    # Ensure the stream is at the beginning before reading
                    file_stream.seek(0)
                    zipf.writestr(filename, file_stream.read())
                    logger.info(f"Added '{filename}' to zip archive.")
                except Exception as write_err:
                    logger.error(f"Error writing file '{filename}' to zip: {write_err}", exc_info=True)
                    # Decide if you want to continue or fail the whole zip process
                    # For robustness, let's continue adding other files

        zip_stream.seek(0) # Rewind the zip stream
        logger.info("Successfully created zip archive in memory.")
        return zip_stream
    except Exception as e:
        logger.error(f"Error creating zip archive: {e}", exc_info=True) # Log traceback
        return None
