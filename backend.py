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
def extract_text_from_pdf(pdf_file_path):  # Changed: Now accepts a file path
    """
    Extracts text from a PDF file, handling both text-based and image-based PDFs.
    Args:
        pdf_file_path: The path to the PDF file (string).
    Returns:
        str: The extracted text, or None if extraction fails.
    """
    try:
        # --- Attempt standard text extraction first ---
        try:
            with open(pdf_file_path, 'rb') as f:  # Open the file in binary read mode
                pdf_reader = PdfReader(f)
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
        except Exception as e:
            logging.warning(f"PyPDF2 extraction failed: {e}.  Attempting OCR.")
            text = ""  # Reset text in case of PyPDF2 failure


        # --- OCR Extraction (if standard extraction fails) ---
        try:
            images = convert_from_path(pdf_file_path)  # pdf_file_path is already a path
            extracted_text = ""
            for i, image in enumerate(images):
                try:
                    page_text = pytesseract.image_to_string(image, lang='ara')  # Specify language if needed
                    extracted_text += page_text + "\n"
                    logging.info(f"Successfully OCRed page {i+1}")
                except Exception as ocr_err:
                    logging.error(f"OCR error on page {i+1}: {ocr_err}")

            if extracted_text.strip():
                logging.info("Successfully extracted text from PDF using OCR.")
                return extracted_text
            else:
                logging.warning("OCR also failed to extract any text.")
                return ""  # empty string
        except Exception as ocr_exception:
            logging.error(f"OCR processing failed: {ocr_exception}")
            return None


    except Exception as e:
        logging.error(f"Error extracting text from PDF: {e}")
        return None  # Indicate failure
