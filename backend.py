# backend.py

import io
import zipfile
# import fitz # No longer needed for extraction if fully replacing
import google.generativeai as genai
from docx import Document
import logging
import os # Needed for environment variable check

# Import the Google Cloud Vision client library
from google.cloud import vision

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PDF/Image Processing with Google Cloud Vision ---
def extract_text_from_pdf(pdf_file_obj):
    """
    Extracts text from a PDF file object using Google Cloud Vision API OCR.
    Handles both text-based and image-based PDFs.
    Args:
        pdf_file_obj: A file-like object representing the PDF.
    Returns:
        str: The extracted text, or None if extraction fails critically.
             Returns an error string starting with "Error:" for API-specific issues.
    """
    # Check if credentials environment variable is set
    if "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ:
        logging.error("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")
        return "Error: Vision API authentication not configured (GOOGLE_APPLICATION_CREDENTIALS missing)."

    try:
        logging.info("Initializing Google Cloud Vision client...")
        client = vision.ImageAnnotatorClient()
        logging.info("Client initialized.")

        # Ensure stream is at the beginning and read content
        pdf_file_obj.seek(0)
        content = pdf_file_obj.read()
        logging.info(f"Read {len(content)} bytes from PDF stream.")

        if not content:
            logging.error("PDF content is empty.")
            return "" # Return empty string if the file itself was empty

        # Prepare the input config for PDF
        # Vision API handles PDF directly for document text detection
        mime_type = "application/pdf"
        input_config = vision.InputConfig(content=content, mime_type=mime_type)

        # Specify the feature type: DOCUMENT_TEXT_DETECTION for dense text/OCR
        features = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]

        # Set context hints if needed (e.g., language) - useful for Arabic
        image_context = vision.ImageContext(language_hints=["ar"]) # Hint that the language is Arabic

        # Construct the request
        request = vision.AnnotateFileRequest(
            input_config=input_config,
            features=features,
            image_context=image_context # Add language hint context
        )

        logging.info("Sending request to Google Cloud Vision API (batch_annotate_files)...")
        # Use batch_annotate_files for document types like PDF
        response = client.batch_annotate_files(requests=[request])
        logging.info("Received response from Vision API.")

        # Process the first (and only) response in the batch
        if response.responses:
            first_response = response.responses[0]
            # Check for errors reported by the API for this specific file
            if first_response.error.message:
                error_message = f"Vision API Error for file: {first_response.error.message}"
                logging.error(error_message)
                return f"Error: {error_message}" # Return specific API error

            # Check if full text annotation exists
            if first_response.full_text_annotation:
                extracted_text = first_response.full_text_annotation.text
                logging.info(f"Successfully extracted text using Vision API. Length: {len(extracted_text)}")
                # Log first 100 chars for verification
                logging.info(f"  > Extracted text (first 100 chars): '{extracted_text[:100]}...'")
                if not extracted_text.strip():
                     logging.warning("Vision API returned annotation, but extracted text is empty/whitespace.")
                     return ""
                return extracted_text
            else:
                logging.warning("Vision API response received, but no full_text_annotation found. PDF might have no text content.")
                return "" # No text found, return empty string
        else:
             logging.error("Vision API returned an empty response list.")
             return "Error: Vision API returned no response."


    except Exception as e:
        # Log the specific error
        logging.error(f"CRITICAL Error during Vision API interaction: {e}", exc_info=True) # Log traceback
        return f"Error: Failed to process PDF with Vision API. Details: {e}" # Return specific exception


# --- Gemini Processing ---
# Keep this function as it was, it uses the Gemini API key from the UI
def process_text_with_gemini(api_key: str, raw_text: str, rules_prompt: str):
    """
    Processes raw text using the Gemini API based on provided rules.
    Args:
        api_key (str): The Gemini API key (from Streamlit input).
        raw_text (str): The raw text extracted from the PDF (by Vision API now).
        rules_prompt (str): User-defined rules/instructions for Gemini.
    Returns:
        str: The processed text from Gemini, or an error string if an error occurs.
             Returns "" if raw_text is empty.
    """
    if not api_key:
        logging.error("Gemini API key is missing.")
        return "Error: Gemini API key is missing."
    if not raw_text:
        logging.warning("Skipping Gemini call: No raw text provided (likely from Vision API).")
        return ""

    try:
        genai.configure(api_key=api_key)
        # Hardcoded model name (or make this configurable again if desired)
        model_name = "gemini-1.5-flash-latest"
        model = genai.GenerativeModel(model_name)

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

        if not response.parts:
            if response.prompt_feedback.block_reason:
                block_reason_msg = f"Content blocked by Gemini safety filters. Reason: {response.prompt_feedback.block_reason}"
                logging.error(f"Gemini request blocked. Reason: {response.prompt_feedback.block_reason}")
                return f"Error: {block_reason_msg}"
            else:
                logging.warning("Gemini returned an empty response with no specific block reason.")
                return ""

        processed_text = response.text
        logging.info("Successfully received response from Gemini.")
        return processed_text

    except Exception as e:
        logging.error(f"Error interacting with Gemini API: {e}")
        return f"Error: Failed to process text with Gemini. Details: {e}"


# --- Word Document Creation ---
# No changes needed here
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
        paragraph = document.add_paragraph(processed_text)
        paragraph_format = paragraph.paragraph_format
        paragraph_format.alignment = 3  # WD_ALIGN_PARAGRAPH.RIGHT
        paragraph_format.right_to_left = True

        for run in paragraph.runs:
            font = run.font
            font.name = 'Arial'
            font.rtl = True

        doc_stream = io.BytesIO()
        document.save(doc_stream)
        doc_stream.seek(0)
        logging.info("Successfully created Word document in memory.")
        return doc_stream
    except Exception as e:
        logging.error(f"Error creating Word document: {e}")
        return None


# --- Zipping Files ---
# No changes needed here
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
        with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename, file_stream in files_data:
                file_stream.seek(0)
                zipf.writestr(filename, file_stream.read())
                logging.info(f"Added '{filename}' to zip archive.")

        zip_stream.seek(0)
        logging.info("Successfully created zip archive in memory.")
        return zip_stream
    except Exception as e:
        logging.error(f"Error creating zip archive: {e}")
        return None
