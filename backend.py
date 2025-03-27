# backend.py
import io
import zipfile
# from PyPDF2 import PdfReader # REMOVE THIS LINE
import fitz # PyMuPDF - ADD THIS LINE
import google.generativeai as genai
from docx import Document
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
            logging.info(f"Opened PDF with PyMuPDF. Number of pages: {len(doc)}")
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Extract text respecting the page's effective area (incl. CropBox)
                # sort=True attempts to maintain reading order
                page_text = page.get_text("text", sort=True)
                if page_text:
                    text += page_text + "\n" # Add newline between pages

        logging.info(f"Successfully extracted text using PyMuPDF.")
        # Basic check if extraction yielded *any* text
        if not text.strip():
             logging.warning("PyMuPDF extraction resulted in empty text. PDF might be image-based or lack text content.")
             # Return empty string instead of None to avoid downstream errors expecting a string
             return ""
        return text
    except Exception as e:
        # Catch fitz-specific errors or general exceptions
        logging.error(f"Error extracting text from PDF using PyMuPDF: {e}")
        return None # Indicate failure clearly


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
        logging.error("Gemini API key is missing.")
        # Return an error string that can be displayed in the UI
        return "Error: Gemini API key is missing."
    if not raw_text: # Don't call Gemini if there's no text
        logging.warning("Skipping Gemini call: No raw text provided.")
        return "" # Return empty string consistent with extract_text_from_pdf

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
        Return ONLY the processed text according to the instructions. Do not add any introductory phrases like "Here is the processed text:".
        """

        logging.info(f"Sending request to Gemini model: {model_name}")
        # Add safety settings to potentially allow more content if needed, adjust as necessary
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        response = model.generate_content(full_prompt, safety_settings=safety_settings)

        # Handle potential safety blocks or empty responses
        if not response.parts:
             # Check candidate details first for finish reason
             try:
                if response.candidates and response.candidates[0].finish_reason != 'STOP':
                    finish_reason = response.candidates[0].finish_reason
                    safety_ratings = response.candidates[0].safety_ratings if response.candidates[0].safety_ratings else "N/A"
                    logging.error(f"Gemini generation finished unexpectedly. Reason: {finish_reason}, Safety Ratings: {safety_ratings}")
                    # You might want to check safety_ratings here specifically
                    block_reason_detail = f"Reason: {finish_reason}"
                    if response.prompt_feedback.block_reason:
                         block_reason_detail += f" (Prompt Feedback Block: {response.prompt_feedback.block_reason})"
                    return f"Error: Content generation stopped. {block_reason_detail}"
             except (AttributeError, IndexError):
                 # Fallback if candidate structure is not as expected
                 pass # Continue to check prompt_feedback

             # Check prompt feedback if candidate check didn't yield a reason
             if response.prompt_feedback.block_reason:
                 logging.error(f"Gemini request blocked. Reason: {response.prompt_feedback.block_reason}")
                 return f"Error: Content blocked by Gemini. Reason: {response.prompt_feedback.block_reason}"
             else:
                 # No parts, no candidate finish reason, no prompt block reason -> likely empty response
                 logging.warning("Gemini returned an empty response with no specific block reason.")
                 return "" # Return empty if response is empty but not blocked


        # Accessing the text safely
        try:
            processed_text = response.text
            logging.info("Successfully received response from Gemini.")
            return processed_text
        except ValueError:
            # If response.text raises ValueError (e.g., function calling involved, though not expected here)
            logging.error("Gemini response did not contain valid text.")
            return "Error: Gemini response format issue (no text found)."
        except Exception as resp_err:
             logging.error(f"Error extracting text from Gemini response: {resp_err}")
             return f"Error: Failed to parse Gemini response. Details: {resp_err}"


    except Exception as e:
        logging.error(f"Error interacting with Gemini API: {e}")
        # Provide a user-friendly error string
        return f"Error: Failed to process text with Gemini. Details: {e}"


# --- Word Document Creation ---
def create_word_document(processed_text: str):
    """
    Creates a Word document (.docx) in memory containing the processed text.
    Sets text direction to RTL and uses Arial font.
    Args:
        processed_text (str): The text to put into the document.
    Returns:
        io.BytesIO: A BytesIO stream containing the Word document data, or None on error.
    """
    try:
        document = Document()
        # Add text.
        paragraph = document.add_paragraph()

        # Set paragraph alignment and direction BEFORE adding runs if possible,
        # or apply to the paragraph after adding text.
        paragraph_format = paragraph.paragraph_format
        # WD_ALIGN_PARAGRAPH.RIGHT is 2 (not 3 as previously) - Correction
        # However, python-docx constants are preferred if available.
        # from docx.enum.text import WD_ALIGN_PARAGRAPH
        # paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        paragraph_format.alignment = 2 # Using integer value 2 for RIGHT
        paragraph_format.right_to_left = True

        # Add the text as a run within the paragraph
        run = paragraph.add_run(processed_text)

        # Set font for the run (ensures Arabic characters render well)
        font = run.font
        font.name = 'Arial' # Or Times New Roman, Calibri - common fonts supporting Arabic
        # Optionally set font size
        # from docx.shared import Pt
        # font.size = Pt(12)

        # Save document to a BytesIO stream
        doc_stream = io.BytesIO()
        document.save(doc_stream)
        doc_stream.seek(0) # Rewind the stream to the beginning
        logging.info("Successfully created Word document in memory.")
        return doc_stream
    except Exception as e:
        logging.error(f"Error creating Word document: {e}")
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
        logging.warning("No files provided to create zip archive.")
        return None
    try:
        zip_stream = io.BytesIO()
        # Use ZIP_DEFLATED for compression
        with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename, file_stream in files_data:
                if not isinstance(filename, str) or not hasattr(file_stream, 'read'):
                    logging.warning(f"Skipping invalid data entry in files_data: ({filename}, {type(file_stream)})")
                    continue
                try:
                    # Ensure the stream is at the beginning before reading
                    file_stream.seek(0)
                    zipf.writestr(filename, file_stream.read())
                    logging.info(f"Added '{filename}' to zip archive.")
                except Exception as write_err:
                    logging.error(f"Error writing file '{filename}' to zip: {write_err}")
                    # Decide if you want to continue or fail the whole zip process
                    # For robustness, let's continue adding other files

        zip_stream.seek(0) # Rewind the zip stream
        logging.info("Successfully created zip archive in memory.")
        return zip_stream
    except Exception as e:
        logging.error(f"Error creating zip archive: {e}")
        return None
