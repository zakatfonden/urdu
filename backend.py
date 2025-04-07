# backend.py (Modified for DOCX Input, Translation, and Merging)

import io
import google.generativeai as genai
from docx import Document # For reading/writing .docx
# --- NEW: Import docxcompose for merging ---
from docxcompose.composer import Composer
# ---
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import logging
import os
# import streamlit as st # No longer needed in backend if Vision credentials removed
# import json # No longer needed if Vision credentials removed
# from google.cloud import vision # REMOVED

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')

# --- REMOVED: Runtime Credentials Setup for Vision API ---
# No longer needed if only using Gemini API Key

# --- NEW: Function to extract text from DOCX, skipping headers/footers ---
def extract_text_from_docx(docx_file_obj):
    """
    Extracts text from the main body of a DOCX file object,
    attempting to skip headers and footers.

    Args:
        docx_file_obj: A file-like object representing the DOCX file.

    Returns:
        str: The extracted text, joined by newlines.
             Returns an error string starting with "Error:" if a failure occurs.
    """
    try:
        docx_file_obj.seek(0)
        document = Document(docx_file_obj)
        full_text = []

        # Iterate through paragraphs in the main document body
        # This implicitly skips headers/footers which are in different parts
        for para in document.paragraphs:
            full_text.append(para.text)

        # Note: This simple approach doesn't explicitly handle footnotes,
        # text boxes, or complex table content. Further refinement might be needed.
        extracted_content = "\n".join(full_text)
        logging.info(f"Extracted {len(extracted_content)} characters from DOCX main body.")
        return extracted_content

    except Exception as e:
        logging.error(f"Error extracting text from DOCX: {e}", exc_info=True)
        # Provide a more informative error message if possible
        return f"Error: Failed to process DOCX file. Check if it's a valid .docx format. Details: {e}"


# --- Gemini Processing (Simplified Prompt Focus - Translation Only) ---
def process_text_with_gemini(api_key: str, raw_text: str, rules_prompt: str, model_name: str):
    """
    Sends text (extracted from DOCX) to Gemini for translation based on rules.

    Args:
        api_key (str): The Gemini API key.
        raw_text (str): The text extracted from the DOCX (Urdu, Farsi, English).
        rules_prompt (str): User-defined rules (should focus on translation).
        model_name (str): The specific Gemini model ID.

    Returns:
        str: The translated Arabic text from Gemini or an error string.
    """
    if not api_key:
        logging.error("Gemini API key is missing.")
        return "Error: Gemini API key is missing."

    if not raw_text or not raw_text.strip():
        logging.warning("Skipping Gemini call: No text extracted from DOCX.")
        return "" # Return empty string if nothing to translate

    if not model_name:
        logging.error("Gemini model name is missing.")
        return "Error: Gemini model name not specified."

    try:
        genai.configure(api_key=api_key)
        logging.info(f"Initializing Gemini model: {model_name}")
        model = genai.GenerativeModel(model_name)

        # Construct the prompt using the rules provided (should focus on translation)
        full_prompt = f"""
        **Instructions:**
        {rules_prompt}

        **Text to Process:**
        ---
        {raw_text}
        ---

        **Output:**
        Return ONLY the processed text (Arabic translation) according to the instructions.
        """

        logging.info(f"Sending request to Gemini model: {model_name} for translation. Text length: {len(raw_text)}")
        response = model.generate_content(full_prompt)

        # Error handling for response remains similar
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
                return "" # Return empty if no translation but not blocked

        processed_text = response.text # Expected Arabic translation
        logging.info(f"Successfully received translation from Gemini ({model_name}). Length: {len(processed_text)}")
        return processed_text

    except Exception as e:
        logging.error(f"Error interacting with Gemini API ({model_name}): {e}", exc_info=True)
        return f"Error: Failed to process text with Gemini ({model_name}). Details: {e}"


# --- NEW: Create SINGLE Word Document with Arabic Text ---
def create_arabic_word_doc_from_text(arabic_text: str, filename: str):
    """
    Creates a single Word document (.docx) in memory containing the translated Arabic text.
    Sets paragraph alignment to right and text direction to RTL.

    Args:
        arabic_text (str): The translated Arabic text.
        filename (str): Original filename for context in placeholders/logs.

    Returns:
        io.BytesIO: A BytesIO stream containing the Word document data, or None on critical error.
    """
    try:
        document = Document()
        # Set default styles for Arabic (RTL, Font)
        style = document.styles['Normal']
        font = style.font
        font.name = 'Arial'
        font.rtl = True

        # Set complex script font using oxml
        style_element = style.element
        rpr_elements = style_element.xpath('.//w:rPr')
        rpr = rpr_elements[0] if rpr_elements else OxmlElement('w:rPr')
        if not rpr_elements: style_element.append(rpr)

        font_name_element = rpr.find(qn('w:rFonts'))
        if font_name_element is None:
            font_name_element = OxmlElement('w:rFonts')
            rpr.append(font_name_element)
        font_name_element.set(qn('w:cs'), 'Arial') # Complex Script font

        paragraph_format = style.paragraph_format
        paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        paragraph_format.right_to_left = True

        if arabic_text and arabic_text.strip():
            lines = arabic_text.strip().split('\n')
            for line in lines:
                if line.strip():
                    paragraph = document.add_paragraph(line.strip())
                    # Explicit settings (redundant but safe)
                    paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    paragraph.paragraph_format.right_to_left = True
                    for run in paragraph.runs:
                        run.font.name = 'Arial'
                        run.font.rtl = True
                        run.font.complex_script = True
        else:
            # Handle empty translation
            empty_msg = f"[No translation generated for '{filename}']"
            paragraph = document.add_paragraph(empty_msg)
            paragraph.italic = True
            paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            paragraph.paragraph_format.right_to_left = True
            for run in paragraph.runs:
                run.font.name = 'Arial'
                run.font.rtl = True
                run.font.complex_script = True

        # Save document to a BytesIO stream
        doc_stream = io.BytesIO()
        document.save(doc_stream)
        doc_stream.seek(0)
        logging.info(f"Successfully created intermediate Word doc stream for '{filename}'.")
        return doc_stream

    except Exception as e:
        logging.error(f"Error creating intermediate Word document for '{filename}': {e}", exc_info=True)
        return None # Indicate failure


# --- RE-INTRODUCED: Merging Function using docxcompose ---
def merge_word_documents(doc_streams_data: list[tuple[str, io.BytesIO]]):
    """
    Merges multiple Word documents (provided as BytesIO streams) into one single document.

    Args:
        doc_streams_data: A list of tuples (original_filename_str, word_doc_bytes_io_obj).

    Returns:
        io.BytesIO: A BytesIO stream containing the final merged Word document, or None on error.
    """
    if not doc_streams_data:
        logging.warning("No document streams provided for merging.")
        return None

    try:
        # Initialize Composer with the first document
        first_filename, first_stream = doc_streams_data[0]
        first_stream.seek(0)
        # Ensure the first document is loaded correctly
        master_doc = Document(first_stream)
        composer = Composer(master_doc)
        logging.info(f"Initialized merger with base document from '{first_filename}'.")

        # Append remaining documents
        if len(doc_streams_data) > 1:
            for i in range(1, len(doc_streams_data)):
                filename, stream = doc_streams_data[i]
                stream.seek(0)
                logging.info(f"Appending content from '{filename}'...")
                # Load subsequent documents before appending
                sub_doc = Document(stream)
                # Add a page break before appending the next document's content
                composer.master.add_page_break()
                composer.append(sub_doc)
                logging.info(f"Successfully appended content from '{filename}'.")

        # Save the final merged document
        merged_stream = io.BytesIO()
        composer.save(merged_stream)
        merged_stream.seek(0)
        logging.info(f"Successfully merged {len(doc_streams_data)} documents.")
        return merged_stream

    except Exception as e:
        # Log the specific error during merging
        logging.error(f"Error merging Word documents using docxcompose: {e}", exc_info=True)
        return None

# --- REMOVED: append_text_to_document function ---
# Not needed for the merge strategy
