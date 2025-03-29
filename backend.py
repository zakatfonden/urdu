# backend.py

import io
import zipfile
import google.generativeai as genai
from docx import Document
import logging
import os  # Required for environment variables
import streamlit as st # Required for accessing secrets
import json # Required for manual JSON parsing test and potential cleaning

# Import the Google Cloud Vision client library
from google.cloud import vision

# --- Configure Logging ---
# Basic configuration, adjust level and format as needed
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# --- START: Runtime Credentials Setup for Streamlit Cloud ---
# This block should run once when the module is loaded.

# Define the path for the temporary credentials file within the container's filesystem
CREDENTIALS_FILENAME = "google_credentials.json"
_credentials_configured = False # Flag to track if setup was attempted

if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
    logging.info("Found GOOGLE_CREDENTIALS_JSON in Streamlit Secrets. Setting up credentials file.")
    try:
        # 1. Read from secrets and log its representation
        credentials_json_content_from_secrets = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        logging.info(f"Read {len(credentials_json_content_from_secrets)} characters from secret.")
        # Log first 500 chars using repr() to see hidden characters like \n explicitly
        logging.info(f"REPR of secret content (first 500 chars):\n>>>\n{repr(credentials_json_content_from_secrets[:500])}\n<<<")

        if not credentials_json_content_from_secrets.strip():
             logging.error("GOOGLE_CREDENTIALS_JSON secret is empty.")
             _credentials_configured = False
        else:
            # 2. Write the file with potential cleaning
            file_written_successfully = False
            try:
                # --- START CLEANING ATTEMPT ---
                cleaned_content = credentials_json_content_from_secrets
                try:
                    # Attempt to parse to find the private key and clean it specifically
                    # Use loads first to work with the python object
                    temp_data = json.loads(credentials_json_content_from_secrets)
                    if 'private_key' in temp_data and isinstance(temp_data['private_key'], str):
                        original_pk = temp_data['private_key']
                        # Replace standalone \r and \r\n with just \n inside the key
                        cleaned_pk = original_pk.replace('\r\n', '\n').replace('\r', '\n')
                        if cleaned_pk != original_pk:
                           logging.warning("Attempted to clean '\\r' characters from private_key string.")
                           temp_data['private_key'] = cleaned_pk
                           # Re-serialize the whole structure with the cleaned key using dumps
                           cleaned_content = json.dumps(temp_data, indent=2) # Use dumps for proper formatting
                        else:
                           # If no cleaning needed, keep original content (avoids re-serializing if unnecessary)
                            cleaned_content = credentials_json_content_from_secrets
                    else:
                         logging.warning("Could not find 'private_key' field (or it's not a string) in parsed secret data for cleaning.")
                         # Keep original content if key not found or not string
                         cleaned_content = credentials_json_content_from_secrets
                except json.JSONDecodeError:
                    # If initial parse fails, try a more general replace on the raw string (less safe)
                    logging.warning("Initial parse for targeted cleaning failed. Trying global replace on raw string (less safe).")
                    cleaned_content = credentials_json_content_from_secrets.replace('\r\n', '\n').replace('\r', '\n')
                # --- END CLEANING ATTEMPT ---

                with open(CREDENTIALS_FILENAME, "w", encoding='utf-8') as f:
                    # Write the potentially cleaned content
                    f.write(cleaned_content)
                logging.info(f"Successfully wrote potentially cleaned credentials to {CREDENTIALS_FILENAME} using UTF-8 encoding.")
                file_written_successfully = True
            except Exception as write_err:
                 logging.error(f"CRITICAL Error during file writing (with cleaning attempt): {write_err}", exc_info=True)
                 _credentials_configured = False # Ensure flag is false on write error

            # 3. If written, read back immediately and verify/parse
            if file_written_successfully:
                credentials_content_read_back = None
                try:
                    with open(CREDENTIALS_FILENAME, "r", encoding='utf-8') as f:
                        credentials_content_read_back = f.read()
                    logging.info(f"Successfully read back {len(credentials_content_read_back)} characters from {CREDENTIALS_FILENAME}.")
                    # Log first 500 chars of read-back content using repr()
                    logging.info(f"REPR of read-back content (first 500 chars):\n>>>\n{repr(credentials_content_read_back[:500])}\n<<<")

                    # 4. Try parsing the read-back content manually using standard json library
                    try:
                        json.loads(credentials_content_read_back)
                        # If manual parsing works, the file content IS valid JSON.
                        logging.info("Manual JSON parsing of read-back content SUCCEEDED.")
                        # Set the environment variable and flag ONLY if parsing succeeds
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIALS_FILENAME
                        logging.info(f"GOOGLE_APPLICATION_CREDENTIALS set to point to: {CREDENTIALS_FILENAME}")
                        _credentials_configured = True # Mark configuration as successful ONLY here
                    except json.JSONDecodeError as parse_err:
                        # If this fails, the file content IS invalid JSON.
                        logging.error(f"Manual JSON parsing of read-back content FAILED: {parse_err}", exc_info=True)
                        _credentials_configured = False # Parsing failed
                    except Exception as manual_parse_generic_err:
                        logging.error(f"Unexpected error during manual JSON parsing: {manual_parse_generic_err}", exc_info=True)
                        _credentials_configured = False # Other error during manual parse

                except Exception as read_err:
                    logging.error(f"CRITICAL Error reading back credentials file {CREDENTIALS_FILENAME}: {read_err}", exc_info=True)
                    _credentials_configured = False # Failed to read back

    except Exception as e:
        # This catches errors reading from st.secrets itself
        logging.error(f"CRITICAL Error reading secret: {e}", exc_info=True)
        _credentials_configured = False # Ensure flag is false on general errors here

elif "GOOGLE_APPLICATION_CREDENTIALS" in os.environ:
    # If running locally or elsewhere where the env var is set directly
    logging.info("Using GOOGLE_APPLICATION_CREDENTIALS environment variable set externally.")
    # We assume it's configured correctly if the env var exists
    # Check if the path actually exists for better local debugging
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and os.path.exists(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]):
        logging.info(f"External credentials file found at: {os.environ['GOOGLE_APPLICATION_CREDENTIALS']}")
        _credentials_configured = True
    else:
        logging.error(f"External GOOGLE_APPLICATION_CREDENTIALS path not found or not set: {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
        _credentials_configured = False

else:
    # Neither Streamlit secret nor external env var found
    logging.warning("Vision API Credentials NOT found: Neither GOOGLE_CREDENTIALS_JSON secret nor GOOGLE_APPLICATION_CREDENTIALS env var is set.")
    _credentials_configured = False

# --- END: Runtime Credentials Setup ---


# --- PDF/Image Processing with Google Cloud Vision ---
def extract_text_from_pdf(pdf_file_obj):
    """
    Extracts text from a PDF file object using Google Cloud Vision API OCR.
    Handles both text-based and image-based PDFs.
    Args:
        pdf_file_obj: A file-like object representing the PDF.
    Returns:
        str: The extracted text. Returns an empty string "" if no text is found.
             Returns an error string starting with "Error:" if a critical failure occurs.
    """
    global _credentials_configured # Access the flag set during module load

    # Check if credentials setup failed earlier
    if not _credentials_configured:
        # This message will appear if the manual JSON parsing in the setup block failed
        logging.error("Vision API credentials were not configured successfully during startup (likely due to JSON parsing failure of credentials file).")
        return "Error: Vision API authentication failed (Credentials setup failed)."

    # Double-check the environment variable just before client initialization
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path or not os.path.exists(credentials_path):
         # Log the specific path being checked
         logging.error(f"Credentials check failed just before client init: GOOGLE_APPLICATION_CREDENTIALS path '{credentials_path}' not valid or file doesn't exist.")
         return "Error: Vision API credentials file missing or inaccessible at runtime."

    try:
        logging.info(f"Initializing Google Cloud Vision client using credentials file: {credentials_path}")
        # The client automatically uses the GOOGLE_APPLICATION_CREDENTIALS environment variable
        client = vision.ImageAnnotatorClient()
        logging.info("Vision client initialized successfully.")

        # Ensure stream is at the beginning and read content
        pdf_file_obj.seek(0)
        content = pdf_file_obj.read()
        file_size = len(content)
        logging.info(f"Read {file_size} bytes from PDF stream.")

        if not content:
            logging.warning("PDF content is empty.")
            return "" # Return empty string if the file itself was empty

        # Prepare the input config for PDF
        mime_type = "application/pdf"
        input_config = vision.InputConfig(content=content, mime_type=mime_type)

        # Specify the feature type: DOCUMENT_TEXT_DETECTION for dense text/OCR
        features = [vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)]

        # Add language hints for better accuracy with Arabic text
        image_context = vision.ImageContext(language_hints=["ar"])

        # Construct the request
        request = vision.AnnotateFileRequest(
            input_config=input_config,
            features=features,
            image_context=image_context
        )

        logging.info("Sending request to Google Cloud Vision API (batch_annotate_files)...")
        # Use batch_annotate_files for document types like PDF
        # Note: This handles multi-page PDFs automatically.
        response = client.batch_annotate_files(requests=[request])
        logging.info("Received response from Vision API.")

        # Process the first (and only) response in the batch for this single file request
        if not response.responses:
            logging.error("Vision API returned an empty response list.")
            return "Error: Vision API returned no response."

        first_response = response.responses[0]

        # Check for errors reported by the API for this specific file
        if first_response.error.message:
            error_message = f"Vision API Error for file: {first_response.error.message}"
            logging.error(error_message)
            return f"Error: {error_message}" # Return specific API error

        # Extract text from all pages concatenated by the API
        extracted_text = ""
        if first_response.full_text_annotation:
            extracted_text = first_response.full_text_annotation.text
            logging.info(f"Successfully extracted text using Vision API. Total Length: {len(extracted_text)}")
            # Log first ~100 chars for verification
            logging.info(f"  > Extracted text snippet: '{extracted_text[:100].replace(chr(10), ' ')}...'") # Replace newlines for cleaner log
            if not extracted_text.strip():
                 logging.warning("Vision API returned annotation, but extracted text is empty/whitespace.")
                 return "" # Treat as no text found
            return extracted_text
        else:
            logging.warning("Vision API response received, but no full_text_annotation found. PDF might have no text content or be corrupted.")
            return "" # No text found, return empty string

    except Exception as e:
        # Log the specific error, including traceback
        # This will catch the google.auth.exceptions.DefaultCredentialsError if the Google library *still* fails to parse
        logging.error(f"CRITICAL Error during Vision API interaction: {e}", exc_info=True)
        # Provide a user-friendly error message that includes the exception text
        return f"Error: Failed to process PDF with Vision API. Exception: {e}"


# --- Gemini Processing ---
def process_text_with_gemini(api_key: str, raw_text: str, rules_prompt: str):
    """
    Processes raw text using the Gemini API based on provided rules.
    Args:
        api_key (str): The Gemini API key (from Streamlit input).
        raw_text (str): The raw text extracted from the PDF (by Vision API).
        rules_prompt (str): User-defined rules/instructions for Gemini.
    Returns:
        str: The processed text from Gemini. Returns an empty string "" if raw_text is empty.
             Returns an error string starting with "Error:" if a failure occurs.
    """
    if not api_key:
        logging.error("Gemini API key is missing.")
        return "Error: Gemini API key is missing."

    # Skip API call if extraction yielded no text (or only whitespace)
    if not raw_text or not raw_text.strip():
        logging.warning("Skipping Gemini call: No raw text provided (likely from Vision API or empty source).")
        return "" # Return empty string consistent with extraction results

    try:
        genai.configure(api_key=api_key)
        # Hardcoded model name - make this dynamic if needed by passing from app.py
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
        Return ONLY the processed text according to the instructions. Do not add any introductory phrases like "Here is the processed text:". Ensure proper Arabic formatting and right-to-left presentation.
        """

        logging.info(f"Sending request to Gemini model: {model_name}. Text length: {len(raw_text)}")
        # Consider adding safety settings if needed
        # safety_settings=[...]
        response = model.generate_content(
            full_prompt,
            # safety_settings=safety_settings
            )

        # More robust check for valid response content
        if not response.parts:
            block_reason = getattr(response.prompt_feedback, 'block_reason', None)
            if block_reason:
                block_reason_msg = f"Content blocked by Gemini safety filters. Reason: {block_reason}"
                logging.error(f"Gemini request blocked. Reason: {block_reason}")
                return f"Error: {block_reason_msg}"
            else:
                # Check finish reason if available (e.g., 'STOP', 'MAX_TOKENS', 'SAFETY', 'RECITATION', 'OTHER')
                finish_reason_obj = getattr(response, 'prompt_feedback', None)
                finish_reason = getattr(finish_reason_obj, 'finish_reason', 'UNKNOWN') if finish_reason_obj else 'UNKNOWN'
                logging.warning(f"Gemini returned no parts (empty response). Finish Reason: {finish_reason}")
                # Decide how to handle non-safety empty responses. Returning empty string for now.
                return ""

        processed_text = response.text
        logging.info(f"Successfully received response from Gemini. Processed text length: {len(processed_text)}")
        return processed_text

    except Exception as e:
        logging.error(f"Error interacting with Gemini API: {e}", exc_info=True)
        return f"Error: Failed to process text with Gemini. Details: {e}"


# --- Word Document Creation ---
def create_word_document(processed_text: str):
    """
    Creates a Word document (.docx) in memory containing the processed text.
    Args:
        processed_text (str): The text to put into the document.
    Returns:
        io.BytesIO: A BytesIO stream containing the Word document data, or None on critical error.
    """
    try:
        document = Document()
        # Add the entire processed text as one paragraph initially.
        # Further refinement could split text based on newlines from Gemini.
        paragraph = document.add_paragraph(processed_text)

        # Set paragraph alignment to right and direction to RTL for Arabic
        paragraph_format = paragraph.paragraph_format
        # WD_ALIGN_PARAGRAPH.RIGHT is 2
        paragraph_format.alignment = 2
        paragraph_format.right_to_left = True

        # Apply font settings to all runs within the paragraph
        # This helps ensure consistent font application even if docx splits the text
        for run in paragraph.runs:
            font = run.font
            font.name = 'Arial'  # Choose a font known to support Arabic well (Arial, Times New Roman, Calibri)
            font.rtl = True # Explicitly set run font direction

        # Save document to a BytesIO stream
        doc_stream = io.BytesIO()
        document.save(doc_stream)
        doc_stream.seek(0)  # Rewind the stream to the beginning for reading
        logging.info("Successfully created Word document in memory.")
        return doc_stream

    except Exception as e:
        logging.error(f"Error creating Word document: {e}", exc_info=True)
        return None # Indicate failure to create the document stream


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
        logging.warning("Attempted to create zip archive with no files.")
        return None

    try:
        zip_stream = io.BytesIO()
        # Use context manager for robust handling of the zip file object
        with zipfile.ZipFile(zip_stream, 'w', zipfile.ZIP_DEFLATED) as zipf:
            logging.info(f"Creating zip archive with {len(files_data)} file(s)...")
            for filename, file_stream in files_data:
                # Ensure the stream is valid and at the beginning before reading
                if not isinstance(file_stream, io.BytesIO):
                     logging.error(f"Invalid file stream type for '{filename}': {type(file_stream)}. Skipping.")
                     continue # Skip this file
                file_stream.seek(0)
                zipf.writestr(filename, file_stream.read())
                logging.info(f"Added '{filename}' to zip archive.")

        zip_stream.seek(0)  # Rewind the zip stream to the beginning for reading
        logging.info("Successfully created zip archive in memory.")
        return zip_stream

    except Exception as e:
        logging.error(f"Error creating zip archive: {e}", exc_info=True)
        return None # Indicate failure
