# backend.py

import io
import google.generativeai as genai
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import logging
import os
import streamlit as st
import json
from google.cloud import vision
from docxcompose.composer import Composer

# --- NEW: Import PyPDF2 ---
try:
    import PyPDF2
    from PyPDF2.errors import PdfReadError
    PYPDF2_AVAILABLE = True
    logging.info("PyPDF2 library found and imported.")
except ImportError:
    PYPDF2_AVAILABLE = False
    logging.warning("PyPDF2 library not found. PDF text extraction will rely solely on Google Vision API.")


# --- Configure Logging ---
# (Keep existing logging configuration)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# --- Runtime Credentials Setup for Streamlit Cloud (Unchanged) ---
# (Keep the existing credentials setup block exactly as it was)
# ... (rest of the credentials setup code) ...
CREDENTIALS_FILENAME = "google_credentials.json"
_credentials_configured = False # Flag to track if setup was attempted
# ... (rest of the credentials setup code) ...


# --- UPDATED: PDF Text Extraction with PyPDF2 Fallback ---
def extract_text_from_pdf(pdf_file_obj):
    """
    Extracts text from a PDF file object.
    First attempts extraction using PyPDF2 for text-based PDFs.
    If PyPDF2 fails or extracts no text, falls back to Google Cloud Vision API OCR.

    Args:
        pdf_file_obj: A file-like object representing the PDF.

    Returns:
        str: The extracted text.
             Returns an empty string "" if no text is found by either method.
             Returns an error string starting with "Error:" if a critical failure occurs
             (primarily from Vision API if it's used).
    """
    global _credentials_configured, PYPDF2_AVAILABLE

    extracted_text = ""
    extraction_method = "None" # Track which method succeeded

    pdf_file_obj.seek(0)
    content = pdf_file_obj.read()
    pdf_file_obj.seek(0) # Reset seek position in case the original object is needed later
    file_size = len(content)
    logging.info(f"Read {file_size} bytes from PDF stream for extraction.")

    if not content:
        logging.warning("PDF content is empty.")
        return ""

    # --- Attempt 1: PyPDF2 ---
    pypdf2_failed = False
    if PYPDF2_AVAILABLE:
        logging.info("Attempting text extraction using PyPDF2...")
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            num_pages = len(pdf_reader.pages)
            logging.info(f"PyPDF2: PDF has {num_pages} pages.")
            pypdf2_texts = []
            for i, page in enumerate(pdf_reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        pypdf2_texts.append(page_text)
                    # else: # Optional: Log empty pages
                    #     logging.debug(f"PyPDF2: Page {i+1} extracted no text.")
                except Exception as page_exc:
                     # Sometimes specific pages cause issues, log but continue
                     logging.warning(f"PyPDF2: Error extracting text from page {i+1}: {page_exc}", exc_info=True)
                     continue # Try next page

            extracted_text = "\n\n".join(pypdf2_texts) # Use double newline like Vision does

            if extracted_text and extracted_text.strip():
                logging.info(f"PyPDF2: Successfully extracted {len(extracted_text)} characters.")
                extraction_method = "PyPDF2"
            else:
                logging.warning("PyPDF2: Extraction completed, but no text content found. PDF might be image-based or scanned.")
                # Don't set extraction_method, proceed to Vision

        except PdfReadError as e:
            logging.warning(f"PyPDF2: Failed to read PDF (possibly encrypted or corrupted): {e}. Falling back to Vision API.")
            pypdf2_failed = True # Mark as failed, proceed to Vision
        except Exception as e:
            logging.error(f"PyPDF2: An unexpected error occurred during extraction: {e}. Falling back to Vision API.", exc_info=True)
            pypdf2_failed = True # Mark as failed, proceed to Vision
    else:
        logging.info("PyPDF2 not available, proceeding directly to Vision API.")
        pypdf2_failed = True # Treat as failed if library not present


    # --- Attempt 2: Google Cloud Vision (Fallback) ---
    # Only run Vision if PyPDF2 was not available, failed, or found no text
    if extraction_method == "None":
        logging.info("Proceeding with Google Cloud Vision API for OCR.")

        # --- Vision Credentials Check (Moved here) ---
        if not _credentials_configured:
            logging.error("Vision API credentials were not configured successfully during startup.")
            return "Error: Vision API authentication failed (Credentials setup failed)."

        credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not credentials_path or not os.path.exists(credentials_path):
            logging.error(f"Credentials check failed just before client init: GOOGLE_APPLICATION_CREDENTIALS path '{credentials_path}' not valid or file doesn't exist.")
            return "Error: Vision API credentials file missing or inaccessible at runtime."
        # --- End Credentials Check ---

        try:
            logging.info(f"Initializing Google Cloud Vision client using credentials file: {credentials_path}")
            client = vision.ImageAnnotatorClient()
            logging.info("Vision client initialized successfully.")

            # Content is already read
            mime_type = "application/pdf"
            input_config = vision.InputConfig(content=content, mime_type=mime_type)
            features = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]
            # Add context options if needed, e.g., language hints
            image_context = vision.ImageContext(language_hints=["ar"]) # Keep Arabic hint
            request = vision.AnnotateFileRequest(
                input_config=input_config, features=features, image_context=image_context
            )

            logging.info("Sending request to Google Cloud Vision API (batch_annotate_files)...")
            response = client.batch_annotate_files(requests=[request])
            logging.info("Received response from Vision API.")

            if not response.responses:
                logging.error("Vision API returned an empty response list.")
                # If PyPDF2 also failed, return error. If PyPDF2 just found nothing, return empty.
                return "Error: Vision API returned no response." if pypdf2_failed else ""

            first_file_response = response.responses[0]

            if first_file_response.error.message:
                error_message = f"Vision API Error for file: {first_file_response.error.message}"
                logging.error(error_message)
                 # If PyPDF2 also failed, return error. If PyPDF2 just found nothing, return empty.
                return f"Error: {error_message}" if pypdf2_failed else ""

            all_extracted_text_vision = []
            if not first_file_response.responses:
                logging.warning("Vision API's AnnotateFileResponse contained an empty inner 'responses' list. No pages processed?")
                # If PyPDF2 also failed or found nothing, return empty.
                return ""

            for page_index, page_response in enumerate(first_file_response.responses):
                if page_response.error.message:
                    logging.warning(f"  > Vision API Error for page {page_index + 1}: {page_response.error.message}")
                    continue # Skip this page if errored
                if page_response.full_text_annotation:
                    page_text = page_response.full_text_annotation.text
                    all_extracted_text_vision.append(page_text)

            extracted_text = "\n\n".join(all_extracted_text_vision)

            if extracted_text and extracted_text.strip():
                logging.info(f"Vision API: Successfully extracted text from {len(all_extracted_text_vision)} page(s). Total Length: {len(extracted_text)}")
                extraction_method = "Vision"
            else:
                logging.warning("Vision API response received, but no usable full_text_annotation found on any page.")
                # Ensure extracted_text is empty if nothing found
                extracted_text = ""
                # extraction_method remains "None" if nothing found by either method

        except Exception as e:
            logging.error(f"CRITICAL Error during Vision API interaction: {e}", exc_info=True)
            # If PyPDF2 also failed, return error. If PyPDF2 just found nothing, return empty.
            return f"Error: Failed to process PDF with Vision API. Exception: {e}" if pypdf2_failed else ""

    # --- Final Return ---
    if extraction_method != "None":
        logging.info(f"Final extracted text length: {len(extracted_text)} (Method: {extraction_method})")
    else:
         logging.info("No text extracted by either PyPDF2 or Vision API.")

    # Return the text (could be empty if neither method found anything)
    # Errors should have been returned earlier if they were critical
    return extracted_text.strip() # Strip leading/trailing whitespace from final result


# --- Gemini Processing (MODIFIED - Unchanged from your version) ---
# (Keep the existing process_text_with_gemini function exactly as you provided it)
def process_text_with_gemini(api_key: str, raw_text: str, rules_prompt: str, model_name: str):
    # ... (rest of the function) ...
    pass # Placeholder to indicate the rest of the function remains

# --- Create SINGLE Word Document (Unchanged) ---
# (Keep the existing create_word_document function exactly as you provided it)
def create_word_document(processed_text: str):
     # ... (rest of the function) ...
     pass # Placeholder

# --- Merging Function using docxcompose (Unchanged) ---
# (Keep the existing merge_word_documents function exactly as you provided it)
def merge_word_documents(doc_streams_data: list[tuple[str, io.BytesIO]]):
     # ... (rest of the function) ...
     pass # Placeholder
