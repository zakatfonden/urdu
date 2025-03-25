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
import streamlit as st

load_dotenv()

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
    Helper function to process and add a section to the document.  (No changes)
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
    """
    Convert a PDF into images (one per page).  (No changes)
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
    Removes all English alphabets (both uppercase and lowercase) from the input string. (No changes)

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

def process_page(page_data, doc, page_number, need_header_and_footer=True , need_footnotes=True,remove_characters=[">","<","«","»"]):
    """
    Processes OCR results and formats the content into a Word document. (Minor improvements)

    :param page_data: JSON-like dictionary containing OCR results for the page.
    :param doc: Word document object to append content.
    :param page_number: Current page number being processed.
    :param need_header_and_footer: Boolean indicating if header and footer are needed.
    :param need_footnotes: Boolean indicating if footnotes are needed.
    :param remove_characters: List of characters to remove.
    """
    header = page_data.get("header", "")
    heading = page_data.get("heading", "") #This was never used
    main_content = page_data.get("main_content", "")
    footer = page_data.get("footer", "")
    footnotes = page_data.get("footnotes", "")

    section = doc.sections[0]

    if need_header_and_footer and header:
        header_section = section.header
        header_paragraph = header_section.paragraphs[0]
        header_paragraph.text = header
        header_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        header_paragraph.runs[0].font.size = Pt(12)

    if page_number > 1:
        doc.add_page_break()

    if heading:
        if need_footnotes==False:
            heading = remove_small_number_brackets(heading)
        heading = heading.replace("\n", " ")
        heading = heading.strip()
        heading = remove_square_brackets(heading)
        heading = remove_given_characters(heading, remove_characters)
        heading = clean_arabic_text(heading)
        paragraph = doc.add_paragraph(heading)
        run = paragraph.runs[0]
        run.bold = True
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run.font.size = Pt(14)

    if main_content:
        main_content = main_content.replace("\n", " ")
        main_content = main_content.strip()

        if not need_footnotes:
            main_content = remove_small_number_brackets(main_content)

        main_content = remove_square_brackets(main_content)
        main_content = remove_given_characters(main_content, remove_characters)
        main_content = clean_arabic_text(main_content)
        main_content=convert_english_to_arabic_digits(main_content)
    # Define regex pattern to find text enclosed in '*'
        pattern = r'\*(.*?)\*'
        parts = re.split(pattern, main_content)

        for i, part in enumerate(parts):
            if i % 2 == 1:  # This is the bold text
                paragraph = doc.add_paragraph("")  # Create a new paragraph for bold text
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                run = paragraph.add_run(part.strip())  # Remove stars
                run.bold = True
            elif part.strip():  # This is normal text
                paragraph = doc.add_paragraph("")  # Create a new paragraph for normal text
                paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                run = paragraph.add_run(part.strip())

        # Set font properties
        run.font.size = Pt(12)
        run.font.name = "Times New Roman"
    if need_footnotes and footnotes:
        paragraph = doc.add_paragraph("------------------")
        paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

        last_paragraph = None
        i = 1
        for line in footnotes.split("\n"):
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

    if need_header_and_footer and footer:
        footer_section = section.footer
        for line in footer.split("\n"):
            line = line.strip()
            if line:
                footer_paragraph = footer_section.paragraphs[0]
                footer_paragraph.text = line
                footer_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if footer_paragraph.runs:
                    footer_paragraph.runs[0].font.size = Pt(10)


def process_page2(page_data, doc, page_number):
    """
    Processes a page's data and formats it into the Word document.  (No changes)
    """
    # Add a page break if it's not the first page
    if page_number > 1:
        doc.add_page_break()

    # Process each section
    if "section1" in page_data:
        process_section(doc, page_data["section1"])
    if "section2" in page_data:
        process_section(doc, page_data["section2"])
    if "section3" in page_data:
        process_section(doc, page_data["section3"])
    if "section4" in page_data:
        process_section(doc, page_data["section4"])



def extract_pdf_content(pdf_extraction_prompt, start_page, end_page, api_key=None):
    """
    Extract content from pages of a PDF in Arabic using a generative model. (Minor improvements)

    Args:
        pdf_extraction_prompt (str): The prompt for content extraction.
        start_page (int): Starting page number.
        end_page (int): Ending page number.
        api_key (str, optional): API key to enable faster processing.

    Returns:
        list: A list of JSON objects containing the extracted data for each page.
    """
    if api_key:
        genai.configure(api_key=api_key)  # No need to store in a variable
    else:
        genai.configure(api_key=os.getenv("API_KEY")) #Ensure the usage of the default key.

    model = genai.GenerativeModel("gemini-2.0-flash")
    #st.write(model) # Removed: Not necessary to display the model object in Streamlit
    results = []  # Store results for all pages

    for i in range(start_page, end_page + 1):
        image_path = f"temp_images/page_{i}.jpg"
        myfile = genai.upload_file(image_path)

        if myfile is None:
            print(f"File upload failed for page {i}!")
            results.append({"error": "File upload failed", "page": i})
            continue

        try:
            result = model.generate_content([myfile, pdf_extraction_prompt])
            #st.write(f"Processing page {i}: {image_path}") #Removed unnessecary debug

            print(f"Processing page {i}: {image_path}")

            result_text = result.text
            print(f"Result for page {i}: {result_text}")
            start_index = result_text.find("{")
            end_index = result_text.rfind("}") + 1

            # Attempt to parse JSON from the result
            result_json = json.loads(result_text[start_index:end_index])
            results.append(result_json)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON for page {i}: {e}")
            print(f"Problematic text: {result_text[start_index:end_index]}")
            results.append({"error": str(e), "page": i})  # Append error to results
            continue


        except Exception as e:
            print(f"Unexpected error for page {i}: {e}")
            results.append({"error": str(e), "page": i})  # Append error to results
            continue #Cont

        time.sleep(2)  # Consider moving this *outside* the try-except to avoid delaying on errors
    return results
