# backend.py (Modified for Urdu hints)

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

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# --- Runtime Credentials Setup for Streamlit Cloud (Unchanged) ---
CREDENTIALS_FILENAME = "google_credentials.json"
_credentials_configured = False

if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
    logging.info("Found GOOGLE_CREDENTIALS_JSON in Streamlit Secrets. Setting up credentials file.")
    try:
        credentials_json_content_from_secrets = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        logging.info(f"Read {len(credentials_json_content_from_secrets)} characters from secret.")
        logging.info(f"REPR of secret content (first 500 chars):\n>>>\n{repr(credentials_json_content_from_secrets[:500])}\n<<<")

        if not credentials_json_content_from_secrets.strip():
                logging.error("GOOGLE_CREDENTIALS_JSON secret is empty.")
                _credentials_configured = False
        else:
            file_written_successfully = False
            try:
                cleaned_content = credentials_json_content_from_secrets
                try:
                    temp_data = json.loads(credentials_json_content_from_secrets)
                    if 'private_key' in temp_data and isinstance(temp_data['private_key'], str):
                        original_pk = temp_data['private_key']
                        cleaned_pk = original_pk.replace('\r\n', '\n').replace('\r', '\n').replace('\\n', '\n')
                        if cleaned_pk != original_pk:
                            logging.warning("Attempted to clean '\\r' or incorrectly escaped '\\n' characters from private_key string.")
                            temp_data['private_key'] = cleaned_pk
                            cleaned_content = json.dumps(temp_data, indent=2)
                        else:
                            cleaned_content = credentials_json_content_from_secrets
                    else:
                        logging.warning("Could not find 'private_key' field (or it's not a string) in parsed secret data for cleaning.")
                        cleaned_content = credentials_json_content_from_secrets
                except json.JSONDecodeError:
                    logging.warning("Initial parse for targeted cleaning failed. Trying global replace on raw string (less safe).")
                    cleaned_content = credentials_json_content_from_secrets.replace('\r\n', '\n').replace('\r', '\n').replace('\\n', '\n')

                with open(CREDENTIALS_FILENAME, "w", encoding='utf-8') as f:
                    f.write(cleaned_content)
                logging.info(f"Successfully wrote potentially cleaned credentials to {CREDENTIALS_FILENAME} using UTF-8 encoding.")
                file_written_successfully = True
            except Exception as write_err:
                logging.error(f"CRITICAL Error during file writing (with cleaning attempt): {write_err}", exc_info=True)
                _credentials_configured = False

            if file_written_successfully:
                credentials_content_read_back = None
                try:
                    with open(CREDENTIALS_FILENAME, "r", encoding='utf-8') as f:
                        credentials_content_read_back = f.read()
                    logging.info(f"Successfully read back {len(credentials_content_read_back)} characters from {CREDENTIALS_FILENAME}.")
                    logging.info(f"REPR of read-back content (first 500 chars):\n>>>\n{repr(credentials_content_read_back[:500])}\n<<<")

                    try:
                        json.loads(credentials_content_read_back)
                        logging.info("Manual JSON parsing of read-back content SUCCEEDED.")
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_FILENAME
                        logging.info(f"GOOGLE_APPLICATION_CREDENTIALS set to point to: {CREDENTIALS_FILENAME}")
                        _credentials_configured = True
                    except json.JSONDecodeError as parse_err:
                        logging.error(f"Manual JSON parsing of read-back content FAILED: {parse_err}", exc_info=True)
                        _credentials_configured = False
                    except Exception as manual_parse_generic_err:
                        logging.error(f"Unexpected error during manual JSON parsing: {manual_parse_generic_err}", exc_info=True)
                        _credentials_configured = False

                except Exception as read_err:
                    logging.error(f"CRITICAL Error reading back credentials file {CREDENTIALS_FILENAME}: {read_err}", exc_info=True)
                    _credentials_configured = False

    except Exception as e:
        logging.error(f"CRITICAL Error reading secret: {e}", exc_info=True)
        _credentials_configured = False

elif "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    logging.info("Using GOOGLE_APPLICATION_CREDENTIALS environment variable set externally.")
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and os.path.exists(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]):
        logging.info(f"External credentials file found at: {os.environ['GOOGLE_APPLICATION_CREDENTIALS']}")
        _credentials_configured = True
    else:
        logging.error(f"External GOOGLE_APPLICATION_CREDENTIALS path not found or not set: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
        _credentials_configured = False

else:
    logging.warning("Vision API Credentials NOT found: Neither GOOGLE_CREDENTIALS_JSON secret nor GOOGLE_APPLICATION_CREDENTIALS env var is set.")
    _credentials_configured = False
# --- END: Runtime Credentials Setup ---


# --- PDF/Image Processing with Google Cloud Vision ---
def extract_text_from_pdf(pdf_file_obj):
    """
    Extracts text from a PDF file object using Google Cloud Vision API OCR.
    Args:
        pdf_file_obj: A file-like object representing the PDF.
    Returns:
        str: The extracted text, or an error string.
    """
    global _credentials_configured

    if not _credentials_configured:
        logging.error("Vision API credentials were not configured successfully during startup.")
        return "Error: Vision API authentication failed (Credentials setup failed)."

    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path or not os.path.exists(credentials_path):
        logging.error(f"Credentials check failed just before client init: GOOGLE_APPLICATION_CREDENTIALS path '{credentials_path}' not valid or file doesn't exist.")
        return "Error: Vision API credentials file missing or inaccessible at runtime."

    try:
        logging.info(f"Initializing Google Cloud Vision client using credentials file: {credentials_path}")
        client = vision.ImageAnnotatorClient()
        logging.info("Vision client initialized successfully.")

        pdf_file_obj.seek(0)
        content = pdf_file_obj.read()
        file_size = len(content)
        logging.info(f"Read {file_size} bytes from PDF stream.")

        if not content:
            logging.warning("PDF content is empty.")
            return ""

        mime_type = "application/pdf"
        input_config = vision.InputConfig(content=content, mime_type=mime_type)
        features = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]

        # --- CHANGED: Updated language hints for Urdu focus ---
        # Prioritize Urdu, but include others likely to appear.
        # Vision API might auto-detect well, but hints can help guide it.
        language_hints = ["ur", "ar", "fa", "en"]
        image_context = vision.ImageContext(language_hints=language_hints)
        logging.info(f"Using language hints for Vision API: {language_hints}")
        # ---

        request = vision.AnnotateFileRequest(
            input_config=input_config, features=features, image_context=image_context
        )

        logging.info("Sending request to Google Cloud Vision API (batch_annotate_files)...")
        response = client.batch_annotate_files(requests=[request])
        logging.info("Received response from Vision API.")

        if not response.responses:
            logging.error("Vision API returned an empty response list.")
            return "Error: Vision API returned no response."

        first_file_response = response.responses[0]

        if first_file_response.error.message:
            error_message = f"Vision API Error for file: {first_file_response.error.message}"
            logging.error(error_message)
            return f"Error: {error_message}"

        all_extracted_text = []
        if not first_file_response.responses:
            logging.warning("Vision API's AnnotateFileResponse contained an empty inner 'responses' list. No pages processed?")
            return ""

        for page_index, page_response in enumerate(first_file_response.responses):
            if page_response.error.message:
                logging.warning(f"  > Vision API Error for page {page_index + 1}: {page_response.error.message}")
                continue
            if page_response.full_text_annotation:
                page_text = page_response.full_text_annotation.text
                all_extracted_text.append(page_text)

        extracted_text = "\n\n".join(all_extracted_text)

        if extracted_text:
            logging.info(f"Successfully extracted text from {len(all_extracted_text)} page(s) using Vision API. Total Length: {len(extracted_text)}")
            if not extracted_text.strip():
                logging.warning("Vision API processed pages, but extracted text is empty/whitespace after combining.")
                return ""
            return extracted_text
        else:
            logging.warning("Vision API response received, but no usable full_text_annotation found on any page.")
            return ""

    except Exception as e:
        logging.error(f"CRITICAL Error during Vision API interaction: {e}", exc_info=True)
        return f"Error: Failed to process PDF with Vision API. Exception: {e}"


# --- Gemini Processing (Unchanged - relies on prompt from app.py) ---
def process_text_with_gemini(api_key: str, raw_text: str, rules_prompt: str, model_name: str):
    """
    Processes raw text using the specified Gemini API model based on provided rules
    (which now include translation instructions from app.py).

    Args:
        api_key (str): The Gemini API key.
        raw_text (str): The raw text extracted from the PDF (e.g., Urdu).
        rules_prompt (str): User-defined rules/instructions for Gemini (e.g., clean & translate).
        model_name (str): The specific Gemini model ID to use.

    Returns:
        str: The processed text from Gemini (expected to be Arabic translation).
             Returns empty string "" if raw_text is empty.
             Returns an error string starting with "Error:" if a failure occurs.
    """
    if not api_key:
        logging.error("Gemini API key is missing.")
        return "Error: Gemini API key is missing."

    if not raw_text or not raw_text.strip():
        logging.warning("Skipping Gemini call: No raw text provided.")
        return ""

    if not model_name:
        logging.error("Gemini model name is missing.")
        return "Error: Gemini model name not specified."

    try:
        genai.configure(api_key=api_key)
        logging.info(f"Initializing Gemini model: {model_name}")
        model = genai.GenerativeModel(model_name)

        # The prompt now contains translation instructions from app.py
        full_prompt = f"""
        **Instructions:**
        {rules_prompt}

        **Text to Process:**
        ---
        {raw_text}
        ---

        **Output:**
        Return ONLY the processed and formatted text according to the instructions.
        """

        logging.info(f"Sending request to Gemini model: {model_name} for processing/translation. Text length: {len(raw_text)}")
        response = model.generate_content(full_prompt)

        if not response.parts:
            block_reason = None
            safety_ratings = None
            if hasattr(response, 'prompt_feedback'):
                block_reason = getattr(response.prompt_feedback, 'block_reason', None)
                safety_ratings = getattr(response.prompt_feedback, 'safety_ratings', None)

            if block_reason:
                block_reason_msg = f"Content blocked by Gemini safety filters. Reason: {block_reason}"
                logging.error(f"Gemini request ({model_name}) blocked. Reason: {block_reason}. Ratings: {safety_ratings}")
                return f"Error: {block_reason_msg}"
            else:
                finish_reason_obj = getattr(response, 'prompt_feedback', None)
                finish_reason = getattr(finish_reason_obj, 'finish_reason', 'UNKNOWN') if finish_reason_obj else 'UNKNOWN'
                logging.warning(f"Gemini ({model_name}) returned no parts (empty response). Finish Reason: {finish_reason}")
                return "" # Return empty string if no content but not blocked

        processed_text = response.text # This should be the Arabic translation
        logging.info(f"Successfully received response from Gemini ({model_name}). Processed text length: {len(processed_text)}")
        return processed_text

    except Exception as e:
        logging.error(f"Error interacting with Gemini API ({model_name}): {e}", exc_info=True)
        return f"Error: Failed to process text with Gemini ({model_name}). Details: {e}"


# --- Appends text to an existing Document object (Unchanged) ---
# This function correctly handles appending Arabic text passed to it.
def append_text_to_document(document: Document, processed_text: str, filename: str, is_first_file: bool):
    """
    Appends processed text (expected to be Arabic translation) to an existing
    python-docx Document object. Sets paragraph alignment to right and text
    direction to RTL for Arabic.

    Args:
        document (Document): The existing document object.
        processed_text (str): The Arabic text to append.
        filename (str): Original filename for logging/placeholders.
        is_first_file (bool): Flag indicating if this is the first file.

    Returns:
        bool: True if successful, False on critical error.
    """
    try:
        if processed_text and processed_text.strip():
            logging.info(f"Appending translated content from '{filename}' to the document.")
            lines = processed_text.strip().split('\n')
            for line in lines:
                if line.strip():
                    paragraph = document.add_paragraph(line.strip())
                    paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    paragraph.paragraph_format.right_to_left = True
                    for run in paragraph.runs:
                        run.font.name = 'Arial'
                        run.font.rtl = True
                        run.font.complex_script = True
        else:
            logging.warning(f"No translated text to append for '{filename}'. Adding placeholder.")
            empty_msg = f"[No text extracted, processed, or translated for '{filename}']" # Updated placeholder
            paragraph = document.add_paragraph(empty_msg)
            paragraph.italic = True
            paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            paragraph.paragraph_format.right_to_left = True
            for run in paragraph.runs:
                run.font.name = 'Arial'
                run.font.rtl = True
                run.font.complex_script = True

        return True

    except Exception as e:
        logging.error(f"Error appending text for '{filename}' to Word document: {e}", exc_info=True)
        try:
            error_para = document.add_paragraph(f"[Error appending content for '{filename}': {e}]")
            error_para.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
            error_para.paragraph_format.right_to_left = False
            for run in error_para.runs:
                run.font.name = 'Calibri'
                run.font.rtl = False
                run.font.complex_script = False
                run.font.size = Pt(9)
                run.italic = True
        except Exception:
            pass
        return False
