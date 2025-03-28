import io
import zipfile
from PyPDF2 import PdfReader
import google.generativeai as genai
from docx import Document
import logging
from PIL import Image  # Pillow for image handling
import pytesseract
from pdf2image import convert_from_path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PDF Processing ---
def extract_text_from_pdf(pdf_file_obj):
    """
    Extracts text from a PDF file object, handling both text-based and image-based PDFs.
    Args:
        pdf_file_obj: A file-like object representing the PDF.
    Returns:
        str: The extracted text, or None if extraction fails.
    """
    try:
        # --- Attempt standard text extraction first ---
        pdf_reader = PdfReader(pdf_file_obj)
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"  # Add newline between pages
        logging.info(f"Successfully extracted text from PDF using standard method.")

        if text.strip():
            return text  # Return if standard extraction was successful
        else:
            logging.warning("Standard PDF extraction resulted in empty text. Attempting OCR...")

        # --- OCR Extraction (if standard extraction fails) ---
        #pdf_file_obj.seek(0)  # Reset file pointer to the beginning
        images = convert_from_path(pdf_file_obj) #pdf_file_obj.name for streamlit object
        extracted_text = ""
        for i, image in enumerate(images):
            try:
                page_text = pytesseract.image_to_string(image, lang='ara')  # Specify language if needed, e.g., 'ara' for Arabic, 'eng' for English
                extracted_text += page_text + "\n"
                logging.info(f"Successfully OCRed page {i+1}")
            except Exception as ocr_err:
                logging.error(f"OCR error on page {i+1}: {ocr_err}")

        if extracted_text.strip():
            logging.info("Successfully extracted text from PDF using OCR.")
            return extracted_text
        else:
            logging.warning("OCR also failed to extract any text.")
            return "" #empty string
    except Exception as e:
        logging.error(f"Error extracting text from PDF: {e}")
        return None  # Indicate failure
