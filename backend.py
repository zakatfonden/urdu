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
import streamlit as st  # Import streamlit
from docx.text.paragraph import Paragraph
from docx.text.run import Run
load_dotenv()

DEFAULT_API_KEY = os.getenv("API_KEY")


def convert_english_to_arabic_digits(text):
    # Mapping of English digits to Arabic digits
    digit_mapping = {
        '0': '٠',
        '1': '١',
        '2': '٢',
        '3': '٣',
        '4': '٤',
        '5': '٥',
        '6': '٦',
        '7': '٧',
        '8': '٨',
        '9': '٩'
    }

    # Replace each English digit with its corresponding Arabic digit
    for eng, arb in digit_mapping.items():
        text = text.replace(eng, arb)

    return text

def process_section(doc, main_content):
    """
    Helper function to process and add a section to the document.
    """
    if main_content:
        paragraph = doc.add_paragraph("------------------")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        main_content = main_content.replace("\n", " ")
        paragraph = doc.add_paragraph("")
      # Remove leading and trailing whitespace
        main_content = main_content.strip()
        main_content = remove_square_brackets(main_content)
        main_content = remove_given_characters(main_content, ["*",">","<","«","»"])
        main_content = clean_arabic_text(main_content)
        paragraph = doc.add_paragraph(main_content)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if paragraph.runs:
            paragraph.runs[0].font.size = Pt(10)
            paragraph.runs[0].font.name = "Times New Roman"

def pdf_to_images(pdf_path, output_folder, start_page=1, end_page=None):
    """Converts PDF pages to PNG images."""
    pdf_document = fitz.open(pdf_path)

    # Validate and adjust page range
    total_pages = len(pdf_document)
    if end_page is None or end_page > total_pages:
        end_page = total_pages
    if start_page < 1:
        start_page = 1
    start_page_zero = start_page -1
    # Iterate through the specified page range
    for page_num in range(start_page_zero, end_page):  # Adjust for 0-based index
        page = pdf_document.load_page(page_num)
        pix = page.get_pixmap()
        output_path = os.path.join(output_folder, f"page_{page_num + 1}.png")  # 1-based naming
        pix.save(output_path)

    pdf_document.close()

def remove_small_number_brackets(input_string):
    # Regular expression to match brackets containing one or two digits (English or Arabic) with optional spaces
    digit_text=pyarabic.trans.normalize_digits(input_string, source='all', out='west')

    cleaned_string = re.sub(r"\(\d+\)", "", digit_text)
    return cleaned_string


def remove_square_brackets(input_string):
    cleaned_text = re.sub(r"\[[\u0600-\u06FF\s\d/]+\]", "", input_string)
    return cleaned_text

def clean_arabic_text(text):
    # Ensure no space before punctuation
    text = re.sub(r'\s+([،؛:.؟!])', r'\1', text)
    # Ensure one space after punctuation
    text = re.sub(r'([،؛:.؟!])([^\s])', r'\1 \2', text)
    # Remove extra spaces around text
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def remove_given_characters(input_string, characters_to_remove):
    # Removes characters outside of brackets
    pattern = f"[{''.join(re.escape(char) for char in characters_to_remove)}]"
    cleaned_string = re.sub(f"{pattern}(?![^(]*\))", '', input_string)
    return cleaned_string

def remove_english_alphabets(input_string):
    """
    Removes all English alphabets (both uppercase and lowercase) from the input string.

    :param input_string: The string from which English alphabets should be removed.
    :return: The cleaned string with no English alphabets.
    """
    cleaned_string = re.sub(r'[A-Za-z]', '', input_string)
    return cleaned_string
def to_arabic_number(n):
    arabic_digits = {
        '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
        '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'
    }
    return ''.join(arabic_digits[d] for d in str(n))

def extract_number_and_line(line):
    if line[0] == "(" and (line[2] == ")" or line[3] == ")"):
        if line[2] == ")":
            return True, line[3:]
        else:
            return True, line[4:]
    return False, line

def process_page(page_data, doc, page_number, need_header_and_footer=True, need_footnotes=True, remove_characters=None):
    """Processes a single page's extracted content and adds it to the Word document."""

    try:
        data = json.loads(page_data)  # Parse the JSON string
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")  # Log the error
        print(f"Problematic JSON data: {page_data}")  # Log the data
        return  # Exit the function if JSON parsing fails.  Don't add bad data

    # Optional character removal
    if remove_characters:
      for section in data:
        if isinstance(data[section], str): #Check if the value is not None.
            for char in remove_characters:
                data[section] = data[section].replace(char, "")

    # Add Page Number as Header (if needed)
    if need_header_and_footer:
        section = doc.sections[0]  # Assuming you want page numbers on all sections
        header = section.header
        paragraph = header.paragraphs[0]
        paragraph.text = f"Page {page_number}"
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT


    # Add Extracted Content to the Document
    if need_header_and_footer and data.get("header") and data["header"].strip() != "": #Check if it exists and isnt blank
        header_para = doc.add_paragraph(data["header"])
        header_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT


    if  data.get("main_content") and data["main_content"].strip() != "":
        # Regular expression to find text enclosed in asterisks
        matches = re.findall(r'\*(.*?)\*', data["main_content"])

        # Replace all occurrences of text enclosed in asterisks for processing
        processed_text = re.sub(r'\*(.*?)\*', r'\1', data["main_content"])

        # Add the processed text to the document first
        main_content_para = doc.add_paragraph(processed_text)
        main_content_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        set_font_size(main_content_para,12)

        # Loop through the matches and set font size to 24 and bold for the specific ranges
        for match in matches:
            for run in main_content_para.runs:
                if match in run.text:
                    # Split the run into three parts: before, match, and after
                    before, _, after = run.text.partition(match)
                    
                    # Set the text for the 'before' part and restore other settings
                    run.text = before
                    
                    # Create a new run for the matched text
                    bold_run = main_content_para.add_run(match)
                    set_font_size(bold_run, 24)  # Use the helper function
                    bold_run.bold = True
                    
                    # Add a new run for the 'after' part
                    after_run = main_content_para.add_run(after)
                    # Apply necessary font settings if 'after' is not empty
                    if after:
                        set_font_size(after_run,12)

    if need_footnotes and data.get("footnotes") and data["footnotes"].strip() != "":  # Check for footnotes
        paragraph = doc.add_paragraph("------------------")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        last_paragraph = None
        i = 1
        for line in data.get("footnotes").split("\n"):
            line = line.strip()
            is_new_point, text = extract_number_and_line(line)
            line = clean_arabic_text(line)
            if not line:
              continue

            if is_new_point:
              # Create a new paragraph for a new point
              number = to_arabic_number(i)
              last_paragraph = doc.add_paragraph(f"{number}. {text}")
              last_paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
              if last_paragraph.runs:
                  last_paragraph.runs[0].font.size = Pt(10)
                  last_paragraph.runs[0].font.name = "Times New Roman"
              i += 1
            else:
              # Append text to the last paragraph
              if last_paragraph is not None:
                  run = last_paragraph.add_run(f" {text}")
                  run.font.size = Pt(10)
                  run.font.name = "Times New Roman"
        


    if need_header_and_footer and data.get("footer") and data["footer"].strip() != "": #check if footer exists and is not blank
        footer_para = doc.add_paragraph(data["footer"])
        footer_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    doc.add_page_break()  # Add a page break after each page.

    
def process_page2(page_data, doc, page_number):
    """Processes a single page's extracted content (Matn, Sharh, Hashiya) and adds it to the Word document."""

    try:
        data = json.loads(page_data)  # Parse the JSON string
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError: {e}")  # Log the error
        print(f"Problematic JSON data: {page_data}")  # Log the data
        return

    # Add Page Number as Header (if needed)

    section = doc.sections[0]  # Assuming you want page numbers on all sections
    header = section.header
    paragraph = header.paragraphs[0]
    paragraph.text = f"Page {page_number}"
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT



    if data.get("header") and data["header"].strip() != "": #Check if it exists and isnt blank
        header_para = doc.add_paragraph(data["header"])
        header_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # Add Extracted Content to the Document

    for section_key in ["section1", "section2", "section3", "footnotes"]: # Loop through all keys
        if data.get(section_key) and data[section_key].strip() != "": # Check for existence and not empty
            section_para = doc.add_paragraph(data[section_key])
            section_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT


    doc.add_page_break()  # Add a page break after each processed page

def set_font_size(element, size):
    """Helper function to set font size for paragraphs and runs."""
    if isinstance(element, Paragraph):
        for run in element.runs:
            run.font.size = Pt(size)
    elif isinstance(element, Run):
        element.font.size = Pt(size)


def extract_pdf_content(prompt, output_folder, start_page=1, end_page=1, api_key=None):
    """Extracts content from PDF images using Gemini API."""
    genai.configure(api_key= api_key or DEFAULT_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash-preview-0829')

    all_pages_content = []
    for page_num in range(start_page , end_page+1):
        image_path = os.path.join(output_folder, f"page_{page_num}.png")
        #Check if file exists.
        if not os.path.exists(image_path):
            print(f"Error: Image file not found: {image_path}")  # Debugging print
            continue #Skip if it doesnt exist
        try:
            image_part = {"mime_type": "image/png", "data": open(image_path, "rb").read()}
            prompt_parts = [prompt, image_part]
            response = model.generate_content(prompt_parts)
            response.resolve()
            all_pages_content.append(response.text)
        except Exception as e:
            print(f"Error processing image {image_path}: {e}") #Error if failed
            continue #Continue

    return all_pages_content
