# backend.py (Modified)

import google.generativeai as genai
import os
import fitz
import time
import json
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
import re
from dotenv import load_dotenv
import pyarabic.trans
import streamlit as st # Keep for st.write in extract_pdf_content
load_dotenv()

def convert_english_to_arabic_digits(text):
    # Mapping of English digits to Arabic digits
    digit_mapping = {
        '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
        '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'
    }
    # Replace each English digit with its corresponding Arabic digit
    for eng, arb in digit_mapping.items():
        text = text.replace(eng, arb)
    return text

def process_section(doc, main_content):
    """
    Helper function to process and add a section to the document.
    (Used by process_page2 - Keep as is unless Matn/Sharh section needs changes)
    """
    if main_content:
        # Add visual separator
        separator_para = doc.add_paragraph("------------------")
        separator_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        # Add an empty paragraph for spacing before content
        doc.add_paragraph("")

        # Basic cleaning
        main_content = main_content.replace("\n", " ") # Consolidate lines
        main_content = main_content.strip()
        main_content = remove_square_brackets(main_content)
        # Keep removing specific unwanted chars for this section type if needed
        main_content = remove_given_characters(main_content, ["*",">","<","«","»"])
        main_content = clean_arabic_text(main_content)
        main_content = convert_english_to_arabic_digits(main_content) # Convert digits

        # Add the processed content
        content_para = doc.add_paragraph(main_content)
        content_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        # Apply font style to the first run (usually the whole paragraph if added at once)
        if content_para.runs:
            run = content_para.runs[0]
            run.font.size = Pt(12) # Changed from 10 to 12 for consistency
            run.font.name = "Times New Roman"

def pdf_to_images(pdf_path, output_folder, start_page=1, end_page=None):
    """
    Convert a PDF into images (one per page).
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as e:
        st.error(f"Failed to open PDF for image conversion: {e}")
        raise # Re-raise the exception to stop processing

    total_pages = len(pdf_document)
    print(f"Number of pages in the PDF: {total_pages}")

    if end_page is None or end_page > total_pages:
        end_page = total_pages

    # Ensure page numbers are within valid range
    start_page_idx = max(0, start_page - 1)
    end_page_idx = min(total_pages, end_page) # fitz uses 0-based index up to (not including) end

    print(f"Converting pages from index {start_page_idx} to {end_page_idx-1}")

    for page_number in range(start_page_idx, end_page_idx):
        try:
            page = pdf_document.load_page(page_number)
            pix = page.get_pixmap()
            image_path = os.path.join(output_folder, f"page_{page_number + 1}.jpg")
            pix.save(image_path)
            print(f"Saved image: {image_path}")
        except Exception as e:
            st.warning(f"Could not process page {page_number + 1} for image conversion: {e}")
            # Continue trying other pages

    pdf_document.close()


def remove_small_number_brackets(input_string):
    # Removes brackets containing numbers e.g., (1), (12), (١), (١٢)
    # Convert Arabic/Persian digits to Western digits for easier regex
    digit_text = pyarabic.trans.normalize_digits(input_string, source='all', out='west')
    # Remove brackets containing 1 or 2 digits, allowing for potential spaces
    cleaned_string = re.sub(r"\(\s*\d{1,2}\s*\)", "", digit_text)
    # Convert remaining digits back to Arabic if needed (or handle later)
    return cleaned_string


def remove_square_brackets(input_string):
    # Removes square brackets and their content (Arabic text, spaces, digits, slashes)
    cleaned_text = re.sub(r"\[[\u0600-\u06FF\s\d/]+\]", "", input_string)
    return cleaned_text

def clean_arabic_text(text):
    # Basic cleaning for Arabic punctuation and spacing
    if not isinstance(text, str): # Handle potential non-string input
        return ""
    # Ensure no space before punctuation
    text = re.sub(r'\s+([،؛:.؟!])', r'\1', text)
    # Ensure one space after punctuation (if not followed by another punctuation or end of string)
    text = re.sub(r'([،؛:.؟!])(?=[^\s،؛:.؟!])', r'\1 ', text)
     # Remove leading/trailing whitespace and multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    # Remove isolated English letters (might be OCR noise)
    text = remove_english_alphabets(text)
    return text

def remove_given_characters(input_string, characters_to_remove):
    # Removes specified characters from the string
    # Create a regex pattern from the list of characters to remove
    pattern = f"[{''.join(re.escape(char) for char in characters_to_remove)}]"
    # Remove characters that are *not* inside parentheses (to preserve e.g. footnote markers)
    # This regex is complex; consider simplifying if markers aren't handled this way
    # A simpler version: cleaned_string = re.sub(pattern, '', input_string)
    cleaned_string = re.sub(f"{pattern}(?![^(]*\))", '', input_string) # Original logic kept
    return cleaned_string

def remove_english_alphabets(input_string):
    """
    Removes all English alphabets (both uppercase and lowercase) from the input string.
    """
    if not isinstance(input_string, str):
        return ""
    cleaned_string = re.sub(r'[A-Za-z]', '', input_string)
    return cleaned_string

def to_arabic_number(n):
    # Converts Western numerals (0-9) in a string to Arabic-Indic numerals
    try:
        n_str = str(n)
        arabic_digits = {'0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
                       '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'}
        return ''.join(arabic_digits[d] for d in n_str if d in arabic_digits)
    except Exception:
        return str(n) # Return original if conversion fails

def extract_footnote_number_and_line(line):
    # Tries to identify lines starting with (digit) or (digit-digit) like (1) or (12)
    # Returns (is_new_footnote_point, cleaned_text, extracted_number_str)
    line = line.strip()
    # Match (1), (12), ( ١ ), ( ١٢ ), etc. with optional spaces
    match = re.match(r"^\(\s*([\d\u0660-\u0669]{1,3})\s*\)\s*(.*)", line)
    if match:
        number_str = match.group(1)
        text = match.group(2).strip()
        # Normalize detected number to Western digits for comparison/potential sorting
        normalized_number = pyarabic.trans.normalize_digits(number_str, source='all', out='west')
        return True, text, normalized_number
    return False, line, None # Return original line if no pattern match

# --- MODIFICATION: Simplified process_page signature and logic ---
def process_page(page_data, doc, page_number):
    """
    Processes AI results (based on user's prompt) and formats content into a Word document.

    :param page_data: JSON-like dictionary containing AI results for the page.
                       Expected keys depend on the user's prompt, but typically
                       "header", "main_content", "footer", "footnotes".
    :param doc: Word document object to append content.
    :param page_number: Current page number (used mainly for page breaks).
    """
    # Extract data safely using .get()
    header = page_data.get("header", "")
    # Check for main heading *within* main_content if prompt doesn't separate it
    main_content = page_data.get("main_content", "")
    footer = page_data.get("footer", "")
    footnotes = page_data.get("footnotes", "")

    section = doc.sections[0] # Use the first section for headers/footers

    # --- Process Header (Always attempt if present in data) ---
    if header:
        # Clean header text
        header = clean_arabic_text(header)
        header = convert_english_to_arabic_digits(header)
        if header: # Proceed only if header is not empty after cleaning
            header_section = section.header
            # Clear existing header content (important for subsequent pages)
            for para in header_section.paragraphs:
                 para.clear() # Or delete and add new paragraph
            # Add the new header content
            header_paragraph = header_section.paragraphs[0] if header_section.paragraphs else header_section.add_paragraph()
            header_paragraph.text = header
            header_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if header_paragraph.runs:
                header_paragraph.runs[0].font.size = Pt(10) # Smaller font for header
                header_paragraph.runs[0].font.name = "Times New Roman"
            else: # Add run if paragraph was empty
                 run = header_paragraph.add_run(header)
                 run.font.size = Pt(10)
                 run.font.name = "Times New Roman"

    # Add page break before content (except for the very first page processed)
    # We need a reliable way to know if this is the first call for *this document*.
    # Checking `len(doc.paragraphs)` might work if headers/footers don't add paragraphs initially.
    # A safer approach might be to pass a flag or check if `page_number == start_page` (if start_page is available here).
    # For simplicity, let's assume page_number from app.py is the *actual* page number.
    if page_number > 1: # Simple check, assumes page_number starts at 1
         # Check if it's the very *first* page added to *this specific doc object*
         # A bit heuristic: check if the document only contains maybe an empty paragraph
         is_first_content_page = len(doc.paragraphs) <= 1 and doc.paragraphs[0].text == ""
         if not is_first_content_page:
              doc.add_page_break()


    # --- Process Main Content ---
    if main_content:
        # Apply general cleaning first
        main_content = main_content.replace("\n", " ") # Consolidate newlines
        main_content = main_content.strip()

        # --- MODIFICATION: Always remove small number brackets from main content ---
        main_content = remove_small_number_brackets(main_content)
        main_content = remove_square_brackets(main_content) # Remove [text] citations
        # --- MODIFICATION: Removed call to remove_given_characters with user list ---
        # main_content = remove_given_characters(main_content, remove_characters) # REMOVED
        main_content = clean_arabic_text(main_content)
        main_content = convert_english_to_arabic_digits(main_content) # Convert digits

        # Handle potential headings/bold text within main_content based on '*' marker
        # (This assumes the user's prompt still instructs the AI to use '*' for emphasis)
        pattern = r'\*(.*?)\*' # Find text enclosed in asterisks
        parts = re.split(pattern, main_content)

        first_paragraph_added = False
        for i, part in enumerate(parts):
            part = part.strip()
            if not part: # Skip empty parts resulting from split
                continue

            # Add paragraph, right-aligned
            # Add spacing paragraph *before* content unless it's the very first piece
            if first_paragraph_added:
                 doc.add_paragraph("") # Add empty paragraph for spacing
            else:
                 # Check if a heading was already added, if so, add space
                 # This logic is tricky without a dedicated heading field.
                 # Let's add space before the first part if it's not bold.
                 if i == 0 and len(parts) > 1 and parts[0].strip(): # Check if first part exists and isn't bold
                      doc.add_paragraph("")
                 first_paragraph_added = True


            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            run = paragraph.add_run(part)

            if i % 2 == 1:  # This part was between asterisks - make it bold
                run.bold = True
                run.font.size = Pt(14) # Treat as heading/subheading
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER # Center align bold parts
            else: # Normal text
                run.bold = False
                run.font.size = Pt(12) # Standard text size

            # Apply font name consistently
            run.font.name = "Times New Roman"

    # --- Process Footnotes (Always attempt if present in data) ---
    if footnotes:
        # Add a visual separator line before footnotes
        separator_para = doc.add_paragraph("------------------")
        separator_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        # Process footnote text (assuming newline separation and numbered points)
        current_footnote_paragraph = None
        footnote_counter = 1 # Simple counter if AI doesn't provide numbers

        footnote_lines = footnotes.split("\n")
        for line in footnote_lines:
            line = line.strip()
            if not line:
                continue # Skip empty lines

            # Try to detect if line starts with a number like (1)
            is_new_point, text, num_str = extract_footnote_number_and_line(line)
            text = clean_arabic_text(text) # Clean the text part
            text = convert_english_to_arabic_digits(text) # Convert digits in text

            if is_new_point:
                # Use the number detected if available, otherwise use counter
                number_display = f"({to_arabic_number(num_str)})" if num_str else f"({to_arabic_number(footnote_counter)})"
                footnote_counter += 1 # Increment counter even if number found, for next fallback

                current_footnote_paragraph = doc.add_paragraph(f"{number_display} {text}")
                current_footnote_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                if current_footnote_paragraph.runs:
                    run = current_footnote_paragraph.runs[0]
                    run.font.size = Pt(10)
                    run.font.name = "Times New Roman"
            elif current_footnote_paragraph:
                # Append text to the last footnote paragraph if it's continuation
                run = current_footnote_paragraph.add_run(f" {text}") # Add space before appending
                run.font.size = Pt(10)
                run.font.name = "Times New Roman"
            else:
                 # If first line doesn't start with number, add it as is
                 current_footnote_paragraph = doc.add_paragraph(text)
                 current_footnote_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                 if current_footnote_paragraph.runs:
                    run = current_footnote_paragraph.runs[0]
                    run.font.size = Pt(10)
                    run.font.name = "Times New Roman"


    # --- Process Footer (Always attempt if present in data) ---
    if footer:
        # Clean footer text
        footer = clean_arabic_text(footer)
        # Special case: often footers are just page numbers. Try to format nicely.
        # Try converting footer text to number, then to Arabic number
        try:
            page_num_int = int(re.sub(r'\D', '', footer)) # Extract digits
            footer_text = to_arabic_number(page_num_int)
        except ValueError:
            footer_text = convert_english_to_arabic_digits(footer) # Fallback to general digit conversion

        if footer_text: # Proceed only if footer is not empty
            footer_section = section.footer
            # Clear existing footer content
            for para in footer_section.paragraphs:
                para.clear()
            # Add new footer content
            footer_paragraph = footer_section.paragraphs[0] if footer_section.paragraphs else footer_section.add_paragraph()
            footer_paragraph.text = footer_text
            footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if footer_paragraph.runs:
                 footer_paragraph.runs[0].font.size = Pt(10)
                 footer_paragraph.runs[0].font.name = "Times New Roman"
            else:
                 run = footer_paragraph.add_run(footer_text)
                 run.font.size = Pt(10)
                 run.font.name = "Times New Roman"


# --- Keep process_page2 as is, assuming it's used by the other section ---
def process_page2(page_data, doc, page_number):
    """
    Processes a page's data (likely Matn/Sharh) and formats it into the Word document.
    """
    # Add a page break if it's not the first page
    # (Use same logic as process_page or simpler if always breaking)
    is_first_content_page = len(doc.paragraphs) <= 1 and doc.paragraphs[0].text == ""
    if not is_first_content_page:
         doc.add_page_break()

    # Process each section if present in the data
    if "header" in page_data: # Check if header exists for this type too
         # Simple header processing for this type
         header_content = clean_arabic_text(page_data["header"])
         if header_content:
              para = doc.add_paragraph(header_content)
              para.alignment = WD_ALIGN_PARAGRAPH.CENTER
              if para.runs:
                   para.runs[0].font.size = Pt(10)

    # Process numbered sections
    # (Using the 'process_section' helper function)
    if "section1" in page_data:
        process_section(doc, page_data["section1"])
    if "section2" in page_data:
        process_section(doc, page_data["section2"])
    if "section3" in page_data:
        process_section(doc, page_data["section3"])
    # Add section4 if your prompt/data might include it
    if "section4" in page_data:
        process_section(doc, page_data["section4"])

    # Process footnotes if they exist for this type
    if "footnotes" in page_data:
        footnotes_content = page_data["footnotes"]
        if footnotes_content:
            # Add separator
            separator_para = doc.add_paragraph("------------------")
            separator_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            # Basic footnote processing
            cleaned_footnotes = clean_arabic_text(footnotes_content)
            cleaned_footnotes = convert_english_to_arabic_digits(cleaned_footnotes)
            fn_para = doc.add_paragraph(cleaned_footnotes)
            fn_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            if fn_para.runs:
                fn_para.runs[0].font.size = Pt(10)
                fn_para.runs[0].font.name = "Times New Roman"



# --- Modified extract_pdf_content to return a generator ---
def extract_pdf_content(pdf_extraction_prompt, start_page, end_page, api_key=None):
    """
    Extract content from pages of a PDF using Gemini, yielding results per page.

    Args:
        pdf_extraction_prompt (str): The prompt for content extraction.
        start_page (int): Starting page number (1-based).
        end_page (int): Ending page number (inclusive).
        api_key (str, optional): API key.

    Yields:
        dict: JSON object with extracted data for a page, or an error dict.
    """
    try:
        if api_key:
            genai.configure(api_key=api_key)
            print("Using user-provided API key.")
        else:
            genai.configure(api_key=os.getenv("API_KEY"))
            print("Using default API key from .env.")
    except Exception as config_err:
        st.error(f"Failed to configure Google Generative AI: {config_err}")
        raise # Stop execution if configuration fails

    # --- MODIFICATION: Select a model compatible with image input ---
    # Recommend using gemini-1.5-flash or gemini-1.5-pro if available and needed for complex prompts
    # gemini-pro-vision might also work, but newer models are generally better.
    # Sticking with flash for now as it was in the original code. Ensure your key supports it.
    try:
        model = genai.GenerativeModel('gemini-1.5-flash') # Or 'gemini-1.5-pro' or 'gemini-pro-vision'
        print(f"Using Generative Model: {model.model_name}")
    except Exception as model_err:
        st.error(f"Failed to initialize Generative Model: {model_err}. Check API key permissions and model availability.")
        raise

    generation_config = genai.types.GenerationConfig(
         # Explicitly set response mime type if needed, though JSON often default with instructions
         # response_mime_type="application/json",
         temperature=0.2 # Lower temperature for more predictable JSON structure
    )

    safety_settings = [ # Adjust safety settings if needed
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]


    image_folder = "temp_images" # Ensure this matches where images are saved

    for i in range(start_page, end_page + 1):
        image_path = os.path.join(image_folder, f"page_{i}.jpg")
        if not os.path.exists(image_path):
            st.warning(f"Image file not found for page {i}: {image_path}. Skipping.")
            yield {"error": "Image file not found", "page": i}
            continue

        st.write(f"Processing page {i}: Uploading {image_path}...")
        print(f"Processing page {i}: Uploading {image_path}...")
        try:
            # Consider using File API for potentially better handling / caching
            # image_file = genai.upload_file(path=image_path, display_name=f"Page {i}")
            # Using direct image loading for simplicity here
            img_part = {"mime_type": "image/jpeg", "data": open(image_path, "rb").read()}

        except Exception as upload_err:
            st.error(f"File upload/read failed for page {i}: {upload_err}")
            yield {"error": f"File upload/read failed: {upload_err}", "page": i}
            # Optional: Clean up uploaded file if using File API and it fails
            # if 'image_file' in locals() and image_file:
            #     genai.delete_file(image_file.name)
            continue # Skip to next page

        st.write(f"Page {i}: Sending request to Gemini...")
        print(f"Page {i}: Sending request to Gemini...")
        try:
            # Construct the request content
            # Ensure the prompt comes *after* the image for some models
            request_content = [img_part, pdf_extraction_prompt]

            # Make the API call
            response = model.generate_content(
                request_content,
                generation_config=generation_config,
                safety_settings=safety_settings,
                stream=False # Process response fully before proceeding
            )

            # --- Robust JSON Extraction ---
            result_text = response.text
            print(f"Raw response for page {i}: {result_text}") # Log raw response

            # Try finding the JSON block using ```json ... ``` or just { ... }
            json_match = re.search(r"```json\s*(\{.*?\})\s*```|(\{.*?\})", result_text, re.DOTALL | re.IGNORECASE)

            if json_match:
                 # Prioritize the block within ```json ``` if found
                 json_str = json_match.group(1) if json_match.group(1) else json_match.group(2)
                 try:
                     result_json = json.loads(json_str)
                     print(f"Successfully parsed JSON for page {i}")
                     yield result_json
                 except json.JSONDecodeError as json_e:
                     st.warning(f"JSON Decode Error for page {i}: {json_e}. Raw text part: {json_str}")
                     yield {"error": f"JSON Decode Error: {json_e}", "page": i, "raw_text": json_str}
            else:
                 st.warning(f"Could not find JSON block in response for page {i}. Raw text: {result_text}")
                 yield {"error": "No JSON block found in response", "page": i, "raw_text": result_text}


        except Exception as e:
            st.error(f"Error during Gemini API call or processing for page {i}: {e}")
            # Log the full error, potentially including response parts if available
            error_details = f"Unexpected error: {e}"
            if 'response' in locals() and hasattr(response, 'prompt_feedback'):
                 error_details += f" | Prompt Feedback: {response.prompt_feedback}"
            print(error_details) # Log detailed error
            yield {"error": error_details, "page": i}

        finally:
            # Optional: Clean up uploaded file if using File API
            # if 'image_file' in locals() and image_file:
            #     try:
            #         genai.delete_file(image_file.name)
            #     except Exception as delete_err:
            #         st.warning(f"Could not delete uploaded file {image_file.name}: {delete_err}")
            # Rate limiting: crucial for free tier or high volume
            time.sleep(2) # Keep a delay between requests
