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
import pyarabic.trans  # You might not actually need this
import streamlit as st

load_dotenv()

def convert_english_to_arabic_digits(text):
    """Converts English digits in a string to Arabic digits."""
    digit_mapping = {
        '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
        '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'
    }
    return ''.join(digit_mapping.get(char, char) for char in text)

def process_section(doc, main_content):
    """
    Helper function to process and add a section to the document.
    """
    if main_content:
        paragraph = doc.add_paragraph("------------------")  # Separator, if needed
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        main_content = main_content.replace("\n", " ")
        main_content = main_content.strip()
        main_content = remove_square_brackets(main_content)
        main_content = remove_given_characters(main_content, ["*", ">", "<", "«", "»"])
        main_content = clean_arabic_text(main_content)

        paragraph = doc.add_paragraph(main_content)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if paragraph.runs:  # Check if runs exist before accessing
            paragraph.runs[0].font.size = Pt(12)  # Consistent font size
            paragraph.runs[0].font.name = "Times New Roman"


def pdf_to_images(pdf_path, output_folder, start_page=1, end_page=None):
    """
    Convert a PDF into images (one per page).
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    pdf_document = fitz.open(pdf_path)
    total_pages = len(pdf_document)
    print(f"Number of pages in the PDF: {total_pages}")

    if end_page is None or end_page > total_pages:
        end_page = total_pages

    for page_number in range(start_page - 1, end_page):
        page = pdf_document.load_page(page_number)
        pix = page.get_pixmap()
        image_path = os.path.join(output_folder, f"page_{page_number + 1}.jpg")
        pix.save(image_path)
    pdf_document.close() # Close the document after use

def remove_small_number_brackets(input_string):
    """Removes brackets containing one or two digits."""
    # Use pyarabic.trans.normalize_digits for consistent digit handling
    normalized_string = pyarabic.trans.normalize_digits(input_string, source='all', out='west')
    cleaned_string = re.sub(r"\(\s*\d{1,2}\s*\)", "", normalized_string)  # Handle spaces
    return cleaned_string



def remove_square_brackets(input_string):
    """Removes square brackets and their content (Arabic)."""
    cleaned_text = re.sub(r"\[[\u0600-\u06FF\s\d/]+\]", "", input_string)
    return cleaned_text

def clean_arabic_text(text):
    """Cleans Arabic text by handling spaces around punctuation."""
    text = re.sub(r'\s+([،؛:.؟!])', r'\1', text)  # No space before punctuation
    text = re.sub(r'([،؛:.؟!])([^\s])', r'\1 \2', text)  # One space after
    text = re.sub(r'\s+', ' ', text).strip()  # Remove extra spaces
    return text

def remove_given_characters(input_string, characters_to_remove):
    """Removes specified characters, but not inside parentheses."""
    # Build the regex pattern dynamically and correctly handle special regex chars
    pattern = "[" + "".join(re.escape(char) for char in characters_to_remove) + "](?![^()]*\))"
    cleaned_string = re.sub(pattern, '', input_string)
    return cleaned_string


def remove_english_alphabets(input_string):
    """Removes all English alphabets (both uppercase and lowercase)."""
    cleaned_string = re.sub(r'[A-Za-z]', '', input_string)
    return cleaned_string


def to_arabic_number(n):
    """Converts an integer to Arabic digit representation."""
    arabic_digits = {
        '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
        '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'
    }
    return ''.join(arabic_digits[d] for d in str(n))

def extract_number_and_line(line):
    """Extracts a leading number (if present) and the rest of the line."""
    match = re.match(r"^\((\d+)\)\s*(.*)", line)  # Use regex for reliable extraction
    if match:
        return True, match.group(2).strip()  # Return the rest of the line
    return False, line.strip()

def process_page(page_data, doc, page_number, need_header_and_footer=True, need_footnotes=True, remove_characters=None):
    """Processes and formats a single page's content into the Word document."""

    if remove_characters is None:
        remove_characters = [">", "<", "«", "»"] # Default characters

    header = page_data.get("header", "")
    heading = page_data.get("heading", "")  # This might not be used consistently
    main_content = page_data.get("main_content", "")
    footer = page_data.get("footer", "")
    footnotes = page_data.get("footnotes", "")

    section = doc.sections[0]

    if need_header_and_footer and header:
        header_section = section.header
        # Check if the header already has paragraphs
        if header_section.paragraphs:
            header_paragraph = header_section.paragraphs[0]
            header_paragraph.text = header
        else:
            header_paragraph = header_section.add_paragraph(header) # Add if not exists

        header_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if header_paragraph.runs:  # Check before accessing runs
            header_paragraph.runs[0].font.size = Pt(12)

    if page_number > 1:
        doc.add_page_break()


    # --- Heading ---
    if heading:
        heading = heading.replace("\n", " ").strip()
        if not need_footnotes:
             heading = remove_small_number_brackets(heading)
        heading = remove_square_brackets(heading)
        heading = remove_given_characters(heading, remove_characters)
        heading = clean_arabic_text(heading)
        paragraph = doc.add_paragraph(heading)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if paragraph.runs: # Check before accessing
            run = paragraph.runs[0]
            run.bold = True
            run.font.size = Pt(14)



    # --- Main Content ---
    if main_content:
        main_content = main_content.replace("\n", " ").strip()
        if not need_footnotes:
            main_content = remove_small_number_brackets(main_content)
        main_content = remove_square_brackets(main_content)
        main_content = remove_given_characters(main_content, remove_characters)
        main_content = clean_arabic_text(main_content)
        main_content = convert_english_to_arabic_digits(main_content)  # Convert digits

        # Handle bold text marked with asterisks
        pattern = r'\*(.*?)\*'
        parts = re.split(pattern, main_content)

        for i, part in enumerate(parts):
            if i % 2 == 1:  # Bold text
                paragraph = doc.add_paragraph()  # New paragraph for bold
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                run = paragraph.add_run(part.strip())
                run.bold = True
                run.font.size = Pt(12)  # Consistent font size
                run.font.name = "Times New Roman" # Consistent font
            elif part.strip():  # Normal text
                paragraph = doc.add_paragraph()  # New paragraph for normal
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                run = paragraph.add_run(part.strip())
                run.font.size = Pt(12)  # Consistent font size
                run.font.name = "Times New Roman" # Consistent font


    # --- Footnotes ---
    if need_footnotes and footnotes:
        paragraph = doc.add_paragraph("------------------") # Separator
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        last_paragraph = None
        i = 1
        for line in footnotes.split("\n"):
            line = line.strip()
            if not line:
                continue
            line = clean_arabic_text(line) # Clean each line
            is_new_point, text = extract_number_and_line(line)


            if is_new_point:
                number = to_arabic_number(i)
                last_paragraph = doc.add_paragraph() # New paragraph each time
                last_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                run = last_paragraph.add_run(f"{number}. {text}")
                run.font.size = Pt(10)
                run.font.name = "Times New Roman"
                i += 1
            elif last_paragraph is not None:
                run = last_paragraph.add_run(f" {text}")
                run.font.size = Pt(10)
                run.font.name = "Times New Roman"


    # --- Footer ---
    if need_header_and_footer and footer:
        footer_section = section.footer
         # Check if the footer already has paragraphs
        if footer_section.paragraphs:
            footer_paragraph = footer_section.paragraphs[0]
            footer_paragraph.text = footer # Set, don't add multiple
        else:
            footer_paragraph = footer_section.add_paragraph(footer) # Add if not exists

        footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if footer_paragraph.runs: # Check before accessing
            footer_paragraph.runs[0].font.size = Pt(10)


def process_page2(page_data, doc, page_number):
    """Processes a page with sections (Matn, Sharh, Hashiya)."""
    if page_number > 1:
        doc.add_page_break()

    # Process each section, handling missing sections gracefully
    for section_key in ["section1", "section2", "section3", "section4", "header", "footnotes"]: #Include header and footnotes, if any
        if section_key in page_data:
            process_section(doc, page_data[section_key])



def extract_pdf_content(pdf_extraction_prompt, start_page, end_page, api_key=None):
    """Extracts content from a PDF using the Gemini API."""
    if api_key:
        genai.configure(api_key=api_key)
    else:
        genai.configure(api_key=os.getenv("API_KEY"))  # Fallback to env variable

    model = genai.GenerativeModel("gemini-pro-vision")  # Use gemini-pro-vision
    results = []

    for i in range(start_page, end_page + 1):
        image_path = f"temp_images/page_{i}.jpg"
        try:
            # Load the image file
            img = fitz.open(image_path)  # Open with fitz (PyMuPDF)
            rect = img[0].rect  # Get the page rectangle
            clip = fitz.Rect(0, 0, rect.width, rect.height)  # Create a clip rectangle
            pix = img[0].get_pixmap(matrix=fitz.Identity, clip=clip)  # Get pixmap
            img_bytes = pix.tobytes("png")  # Convert to PNG bytes
            img.close()

            image_part = {"mime_type": "image/png", "data": img_bytes}


            # Generate content using the model
            response = model.generate_content([pdf_extraction_prompt, image_part])
            response.resolve() # Ensure full response

            st.write(f"Processing page {i}: {image_path}") # Streamlit output
            print(f"Processing page {i}: {image_path}") # Console output

            result_text = response.text
            print(f"Result for page {i}: {result_text}")

            # Find JSON within the result (robust handling)
            start_index = result_text.find("{")
            end_index = result_text.rfind("}") + 1

            if start_index != -1 and end_index != -1:
                result_json = json.loads(result_text[start_index:end_index])
                results.append(result_json)
            else:
                st.error(f"No valid JSON found for page {i}")
                print(f"Error: No valid JSON found for page {i}")
                results.append({"error": "No valid JSON found", "page": i}) # Add error to results


        except FileNotFoundError:
            st.error(f"Image file not found: {image_path}")
            print(f"Error: Image file not found: {image_path}")
            results.append({"error": "Image file not found", "page": i})
        except json.JSONDecodeError as e:
            st.error(f"JSON decoding error on page {i}: {e}")
            print(f"Error decoding JSON for page {i}: {e}")
            print(f"Problematic text: {result_text}")
            results.append({"error": str(e), "page": i})
        except Exception as e:
            st.error(f"An unexpected error occurred on page {i}: {e}")
            print(f"Unexpected error for page {i}: {e}")
            results.append({"error": str(e), "page": i})

        time.sleep(2)  # Add a delay

    return results
