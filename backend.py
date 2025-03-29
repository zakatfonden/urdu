# backend.py

import io
import zipfile
# from PyPDF2 import PdfReader # REMOVE THIS LINE
import fitz  # PyMuPDF # ADD THIS LINE
import google.generativeai as genai
from docx import Document
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PDF Processing ---
def extract_text_from_pdf(pdf_file_obj):
    """
    Extracts text from a PDF file object using PyMuPDF (fitz).
    Args:
        pdf_file_obj: A file-like object representing the PDF.
    Returns:
        str: The extracted text, or None if extraction fails.
    """
    try:
        # PyMuPDF needs bytes, so read the file object's content
        pdf_bytes = pdf_file_obj.read()
        text = ""
        # Open the PDF from bytes
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            logging.info(f"Opened PDF with PyMuPDF. Pages: {doc.page_count}")
            for page_num in range(len(doc)): # Iterate through pages
                page = doc.load_page(page_num)
                page_text = page.get_text("text") # Extract text from page
                if page_text:
                    text += page_text + "\n" # Add newline between pages

        logging.info(f"Successfully extracted text using PyMuPDF.")
        # Basic check if extraction yielded *any* text
        if not text.strip():
            logging.warning("PyMuPDF extraction resulted in empty text. PDF might be image-based or corrupted.")
            # Return empty string instead of None to avoid downstream errors expecting a string
            return ""
        return text
    except Exception as e:
        # Log the specific error using fitz details if possible
        logging.error(f"Error extracting text from PDF using PyMuPDF: {e}")
        return None # Indicate failure clearly


# --- Gemini Processing ---
def process_text_with_gemini(api_key: str, raw_text: str, rules_prompt: str):
    """
    Processes raw text using the Gemini API based on provided rules.
    Args:
        api_key (str): The Gemini API key.
        raw_text (str): The raw text extracted from the PDF.
        rules_prompt (str): User-defined rules/instructions for Gemini.
    Returns:
        str: The processed text from Gemini, or an error string if an error occurs.
             Returns "" if raw_text is empty.
    """
    if not api_key:
        logging.error("Gemini API key is missing.")
        # Return an error message consistent with other potential errors
        return "Error: Gemini API key is missing."
    if not raw_text:  # Don't call Gemini if there's no text
        logging.warning("Skipping Gemini call: No raw text provided.")
        return ""  # Return empty string consistent with extract_text_from_pdf

    try:
        genai.configure(api_key=api_key)
        # Hardcoded model name remains as per previous code
        model_name = "gemini-1.5-flash-latest"
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
        response = model.generate_content(full_prompt)

        # Handle potential safety blocks or empty responses
        if not response.parts:
            if response.prompt_feedback.block_reason:
                block_reason_msg = f"Content blocked by Gemini safety filters. Reason: {response.prompt_feedback.block_reason}"
                logging.error(f"Gemini request blocked. Reason: {response.prompt_feedback.block_reason}")
                return f"Error: {block_reason_msg}" # Return specific block reason
            else:
                logging.warning("Gemini returned an empty response with no specific block reason.")
                return ""  # Return empty if response is empty but not blocked

        processed_text = response.text
        logging.info("Successfully received response from Gemini.")
        return processed_text

    except Exception as e:
        logging.error(f"Error interacting with Gemini API: {e}")
        # Return a user-friendly error string
        return f"Error: Failed to process text with Gemini. Details: {e}"


# --- Word Document Creation ---
def create_word_document(processed_text: str):
    """
    Creates a Word document (.docx) in memory containing the processed text.
    Args:
        processed_text (str): The text to put into the document.
    Returns:
        io.BytesIO: A BytesIO stream containing the Word document data, or None on error.
    """
    try:
        document = Document()
        # Add text.
        # Set text direction to RTL for Arabic
        paragraph = document.add_paragraph(processed_text)
        paragraph_format = paragraph.paragraph_format
        # Use integer value 3 for WD_ALIGN_PARAGRAPH.RIGHT to avoid importing docx.enum.text
        paragraph_format.alignment = 3
        paragraph_format.right_to_left = True

        # Set font for the run(s) within the paragraph
        # Iterate through runs in case the text properties were split
        for run in paragraph.runs:
            font = run.font
            font.name = 'Arial'  # Or Times New Roman, Calibri - common fonts supporting Arabic
            # Ensure RTL setting is applied to the run font as well (sometimes needed)
            font.rtl = True

        # Save document to a BytesIO stream
        doc_stream = io.BytesIO()
        document.save(doc_stream)
        doc_stream.seek(0)  # Rewind the stream to the beginning
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
    try:
        zip_stream = io.BytesIO()
        # Use context manager for ZipFile
        with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename, file_stream in files_data:
                # Ensure the stream is at the beginning before reading
                file_stream.seek(0)
                zipf.writestr(filename, file_stream.read())
                logging.info(f"Added '{filename}' to zip archive.")

        zip_stream.seek(0)  # Rewind the zip stream
        logging.info("Successfully created zip archive in memory.")
        return zip_stream
    except Exception as e:
        logging.error(f"Error creating zip archive: {e}")
        return None
