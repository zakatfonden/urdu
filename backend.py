# backend.py
import io
import zipfile
from PyPDF2 import PdfReader # Keep for standard extraction attempt
import google.generativeai as genai
from docx import Document
from docx.shared import Inches # Needed for potential future formatting
from docx.enum.text import WD_ALIGN_PARAGRAPH # For text alignment constants
from docx.shared import Pt # For setting font size if needed
import logging
from PIL import Image
import pytesseract
from pdf2image import convert_from_path, exceptions as pdf2image_exceptions

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PDF Processing ---
def extract_text_from_pdf(pdf_file_path: str):
    """
    Extracts text from a PDF file path, handling both text-based and image-based PDFs.
    Args:
        pdf_file_path (str): The path to the PDF file.
    Returns:
        str: The extracted text, or None if a critical error occurs. Returns "" if no text found.
    """
    text = ""
    logging.info(f"Attempting standard text extraction from: {pdf_file_path}")
    try:
        # --- Attempt standard text extraction first ---
        with open(pdf_file_path, 'rb') as f:
            pdf_reader = PdfReader(f)
            if pdf_reader.is_encrypted:
                logging.warning(f"PDF is encrypted, cannot extract text: {pdf_file_path}")
                # Depending on desired behavior, you might try to decrypt or just return "" or None
                # For now, we'll proceed to OCR attempt, which might also fail.
                pass # Let it fall through to OCR attempt, though it's unlikely to work.

            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except Exception as page_exc:
                     # Log error for specific page but continue trying others
                     logging.warning(f"Error extracting text from page {page_num + 1} in {pdf_file_path}: {page_exc}")
            logging.info(f"Finished standard text extraction attempt for: {pdf_file_path}")

        if text.strip():
            logging.info(f"Successfully extracted text using standard method for: {pdf_file_path}")
            return text  # Return if standard extraction was successful

        # If standard extraction yields no text, log and proceed to OCR
        logging.warning(f"Standard PDF extraction resulted in empty text for: {pdf_file_path}. Attempting OCR...")

    except FileNotFoundError:
        logging.error(f"PDF file not found at path: {pdf_file_path}")
        return None # Critical error
    except Exception as pypdf_exc:
        # Log PyPDF2 error but still attempt OCR as fallback
        logging.warning(f"PyPDF2 extraction failed for {pdf_file_path}: {pypdf_exc}. Attempting OCR...")
        text = "" # Ensure text is empty before OCR attempt

    # --- OCR Extraction (if standard extraction fails or yielded no text) ---
    logging.info(f"Starting OCR process for: {pdf_file_path}")
    extracted_text_ocr = ""
    try:
        images = convert_from_path(pdf_file_path, dpi=300) # Use a good DPI
        if not images:
             logging.warning(f"pdf2image returned no images for OCR from: {pdf_file_path}")
             return "" # No images to OCR

        for i, image in enumerate(images):
            page_num_ocr = i + 1
            try:
                # Use Page Segmentation Mode (psm) 6: Assume a single uniform block of text. Adjust if needed.
                # Use OEM 3: Default, based on what is available.
                page_text_ocr = pytesseract.image_to_string(image, lang='ara', config='--psm 6 --oem 3')
                extracted_text_ocr += page_text_ocr + "\n"
                logging.info(f"Successfully OCRed page {page_num_ocr} from: {pdf_file_path}")
            except pytesseract.TesseractNotFoundError:
                 logging.error("Tesseract is not installed or not in PATH. Cannot perform OCR.")
                 return None # Critical dependency missing
            except Exception as ocr_page_err:
                # Log error for specific page but continue trying others
                logging.error(f"OCR error on page {page_num_ocr} in {pdf_file_path}: {ocr_page_err}")

        if extracted_text_ocr.strip():
            logging.info(f"Successfully extracted text using OCR for: {pdf_file_path}")
            return extracted_text_ocr
        else:
            logging.warning(f"OCR process completed but found no text in: {pdf_file_path}")
            return "" # Return empty string if OCR finds nothing

    except pdf2image_exceptions.PDFInfoNotInstalledError:
         logging.error("Poppler is not installed or not in PATH. Cannot perform OCR.")
         return None # Critical dependency missing
    except pdf2image_exceptions.PDFPageCountError:
         logging.error("Unable to get page count (Poppler issue?). Cannot perform OCR.")
         return None # Critical dependency missing
    except Exception as ocr_conv_err:
        logging.error(f"Error during PDF to image conversion or OCR process for {pdf_file_path}: {ocr_conv_err}")
        # If standard text had something, maybe return that? Or indicate failure.
        # If text was empty before, definitely indicate failure.
        if not text.strip():
             return None # Return None if both standard and OCR failed critically
        else:
             logging.warning(f"OCR failed for {pdf_file_path}, but standard extraction had text. Returning standard text.")
             return text # Fallback to potentially empty standard text if OCR fails

# --- Gemini Processing ---
def process_text_with_gemini(api_key: str, raw_text: str, rules_prompt: str):
    """
    Processes raw text using the Gemini API based on provided rules.
    Args:
        api_key (str): The Gemini API key.
        raw_text (str): The raw text extracted from the PDF.
        rules_prompt (str): User-defined rules/instructions for Gemini.
    Returns:
        str: The processed text from Gemini, or a string starting with "Error:" if an error occurs.
    """
    if not api_key:
        logging.error("Gemini API key is missing.")
        return "Error: Gemini API key is missing." # Return error string
    if not raw_text or not raw_text.strip(): # Check if raw_text is None, empty or just whitespace
        logging.warning("Skipping Gemini call: No valid raw text provided.")
        return "" # Return empty string if no text to process

    try:
        genai.configure(api_key=api_key)
        model_name = "gemini-1.5-flash" # Using 1.5 flash as 2.0 is not a valid model name yet
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
        Return ONLY the processed Arabic text according to the instructions. Do not add any introductory phrases like "Here is the processed text:", explanations, or surrounding markdown formatting (like ```). Ensure the output is plain Arabic text formatted as requested.
        """

        logging.info(f"Sending request to Gemini model: {model_name}")
        # Add safety settings if needed, e.g., to be less strict
        # safety_settings = [
        #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        # ]
        # response = model.generate_content(full_prompt, safety_settings=safety_settings)

        response = model.generate_content(full_prompt)

        # More robust check for response content
        if response.parts:
            processed_text = response.text
            logging.info("Successfully received response from Gemini.")
            return processed_text
        elif response.prompt_feedback and response.prompt_feedback.block_reason:
             block_reason = response.prompt_feedback.block_reason
             logging.error(f"Gemini request blocked. Reason: {block_reason}")
             return f"Error: Content blocked by Gemini safety filters. Reason: {block_reason}"
        else:
             # Handle cases where the response might be empty but not explicitly blocked
             logging.warning("Gemini returned an empty response without parts or a specific block reason.")
             # Check candidates if available (sometimes content is there but not in response.text)
             try:
                 if response.candidates and response.candidates[0].content.parts:
                     logging.info("Found text in response.candidates.")
                     return response.candidates[0].content.parts[0].text
             except (AttributeError, IndexError):
                 pass # Ignore if candidates structure is not as expected
             return "" # Return empty if truly empty

    except Exception as e:
        logging.error(f"Error interacting with Gemini API: {e}")
        # Provide more context about the error type if possible
        return f"Error: Failed to process text with Gemini. Details: {type(e).__name__} - {e}"


# --- Word Document Creation ---
def create_word_document(processed_text: str):
    """
    Creates a Word document (.docx) in memory containing the processed text.
    Sets text direction to RTL and uses Arial font.
    Args:
        processed_text (str): The text to put into the document. Can be empty.
    Returns:
        io.BytesIO: A BytesIO stream containing the Word document data, or None if error.
    """
    try:
        document = Document()
        # Add text, even if it's empty (creates an empty paragraph)
        paragraph = document.add_paragraph()
        # Set paragraph formatting BEFORE adding text run if possible, or format run directly
        paragraph_format = paragraph.paragraph_format
        paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT # Use constant
        paragraph_format.right_to_left = True

        # Add text as a run to apply font settings
        run = paragraph.add_run(processed_text)
        font = run.font
        font.name = 'Arial' # Common font supporting Arabic
        # You could also set font.size = Pt(12) or other properties here

        # Save document to a BytesIO stream
        doc_stream = io.BytesIO()
        document.save(doc_stream)
        doc_stream.seek(0) # Rewind the stream to the beginning
        logging.info("Successfully created Word document in memory.")
        return doc_stream
    except Exception as e:
        logging.error(f"Error creating Word document: {e}")
        return None # Indicate failure

# --- Zipping Files ---
def create_zip_archive(files_data: list):
    """
    Creates a Zip archive in memory containing multiple files.
    Args:
        files_data (list): A list of tuples, where each tuple is
                           (filename_str, file_bytes_io_obj).
    Returns:
        io.BytesIO: A BytesIO stream containing the Zip archive data, or None if error.
    """
    if not files_data:
        logging.warning("No file data provided to create zip archive.")
        return None

    try:
        zip_stream = io.BytesIO()
        # Use ZIP_DEFLATED for compression
        with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename, file_stream in files_data:
                if not isinstance(file_stream, io.BytesIO):
                     logging.warning(f"Skipping item for zipping, not a BytesIO object: {filename}")
                     continue
                # Ensure the stream is at the beginning before reading
                file_stream.seek(0)
                zipf.writestr(filename, file_stream.read())
                logging.info(f"Added '{filename}' to zip archive.")

        zip_stream.seek(0) # Rewind the zip stream
        logging.info("Successfully created zip archive in memory.")
        return zip_stream
    except Exception as e:
        logging.error(f"Error creating zip archive: {e}")
        return None # Indicate failure
