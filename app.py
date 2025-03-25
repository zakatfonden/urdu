import os
import time
import fitz  # PyMuPDF for PDF handling
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import streamlit as st
import google.generativeai as genai
import re
from dotenv import load_dotenv
from backend import pdf_to_images, extract_pdf_content, process_page, process_page2
import zipfile
import io
import shutil  # Import shutil
load_dotenv()

# Default API Key
DEFAULT_API_KEY = os.getenv("API_KEY")


def find_and_replace_in_docx(doc, find_texts, replace_texts):
    """
    Replaces all occurrences of specified Arabic text in the document.
    """
    if len(find_texts) != len(replace_texts):
        raise ValueError("Find and Replace lists must have the same length.")

    for find_text, replace_text in zip(find_texts, replace_texts):
        for paragraph in doc.paragraphs:
            if find_text in paragraph.text:
                paragraph.text = paragraph.text.replace(find_text, replace_text)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if find_text in cell.text:
                        cell.text = cell.text.replace(find_text, replace_text)

# Streamlit Sidebar for Navigation
st.sidebar.header("Navigation")
options = ["Process PDF","Matn, Sharh, Hashiya Extraction", "Find and Replace"]
choice = st.sidebar.radio("Go to:", options)

# Process PDF Section
if choice == "Process PDF":
    pdf_extraction_prompt = """
    You will be given pages of a PDF file containing text in Arabic. Your task is to extract the content from each page and categorize it into the following sections in **JSON format**:

    1. **Headers**:
        - Extract all text from the very top section of the page, typically found in the margin above the main content.
        - This section may include information such as document titles, section names, or repetitive information present across multiple pages. It may be present on the page may be not
        - The header is distinct from the main heading of the page.
        - Header is mostly seprated by the actual line using the line below the header.

    2. Main Content (Body of the Page)
        - Extract all text from the **central body** of the page, excluding headers, footers, and footnotes.
        - **Identify the main heading of the page** and enclose it in asterisks (`*`), like this:
        - Example: *العنوان الرئيسي للصفحة*
        - Additionally, if **any bold text** is found **inside the main content**, it should also be treated as a heading and enclosed in asterisks (`*`), like this:
        - Example: *عنوان فرعي داخل المحتوى*
        - If the page is empty/blank give *blank*

    3. **Footnotes (Text Below the Black Line)**:
        - Carefully identify any black horizontal line present on the page.
        - If the line exists, categorize all text below it as "Footnotes".
        - The black line will typically cover about half the width of the page and is visually distinct.
        - If no black line is present, the "Footnotes" section should be empty for that page.

    4. **Footers**:
        - Extract all text from the footer section of the page, typically located at the very bottom.
        - Footers often include repetitive elements such as page numbers or document-specific references and should not overlap with footnotes.

    ### Formatting Guidelines:
        - **Maintain the original Arabic text formatting** as closely as possible.
        - Use the following formatting rules:
        - **Headings**: Represent the main headings in a larger, bold font.
        - Ensure all extracted text is **right-aligned** to match proper Arabic formatting.

    ### Output Format:
    For each page, provide the extracted data in the following JSON structure:
    {
    "header": "<Arabic text of the header>",
    "main_content": "<Arabic text of the main content>",
    "footer": "<Arabic text of the footer>",
    "footnotes": "<Arabic text of the footnotes>"
    }

    """

    st.title("Arabic PDF to Word Converter")
    st.write("Upload multiple PDFs, extract Arabic content, and download the results in separate Word documents (zipped).")

    # Input fields
    user_api_key = st.text_input("Enter your Gemini API Key (optional):", type="password")
    pdf_files = st.file_uploader("Upload multiple PDF files", type=["pdf"], accept_multiple_files=True)  # Accept multiple files

    # Processing options (apply to all files)
    footnotes = st.checkbox("Include Footnotes", value=False)
    headers = st.checkbox("Include Headers and Footers", value=False)
    extra_chars = st.text_area("Characters to Remove (comma-separated):", "").split(",")

    if st.button("Process PDFs"):
        if not pdf_files:
            st.error("Please upload at least one PDF file.")
        else:
            try:
                # Create temporary directory
                temp_dir = "temp"
                os.makedirs(temp_dir, exist_ok=True)

                # Initialize a list to store the paths of the generated Word files
                docx_files = []

                for pdf_file in pdf_files:  # Loop through each uploaded PDF
                    try: #Inner try for the loop
                        # ---  File-Specific Setup ---
                        pdf_name = os.path.splitext(pdf_file.name)[0]  # Filename without extension
                        pdf_path = os.path.join(temp_dir, pdf_file.name)  # Full path to the PDF

                        with open(pdf_path, "wb") as f:
                            f.write(pdf_file.read())

                        # Get Total Pages for PDF.
                        pdf_document = fitz.open(pdf_path)
                        total_pages = len(pdf_document)
                        pdf_document.close()

                        # --- Create Unique Image Directory ---
                        output_folder = os.path.join(temp_dir, f"temp_images_{pdf_name}") #Unique directory
                        os.makedirs(output_folder, exist_ok=True) #Creates that directory.

                        # ---  Per-File Processing ---
                        st.write(f"Processing: {pdf_file.name}")

                        # Convert PDF pages to images (all pages, for simplicity)
                        pdf_to_images(pdf_path, output_folder, start_page=1, end_page=total_pages)

                        # Initialize Word document for *this* PDF
                        doc = Document()

                        # Extract content and process *all* pages of the *current* PDF
                        st.write(f"Extracting content from {pdf_file.name}...")
                        # --- Pass the correct output_folder ---
                        page_content = extract_pdf_content(
                            pdf_extraction_prompt,
                            output_folder,  # Pass output_folder here
                            start_page=1,  # Start from page 1
                            end_page=total_pages, # to the total
                            api_key=user_api_key if user_api_key else None
                        )
                        # Process the extracted content.
                        for i, page_data in enumerate(page_content, start=1):  # Use enumerate for page numbers.
                            try:
                                if extra_chars == [""]:
                                        process_page(
                                        page_data=page_data,
                                        doc=doc,
                                        page_number=i,
                                        need_header_and_footer=headers,
                                        need_footnotes=footnotes,
                                        )
                                else:
                                        process_page(
                                        page_data=page_data,
                                        doc=doc,
                                        page_number=i,
                                        need_header_and_footer=headers,
                                        need_footnotes=footnotes,
                                        remove_characters=extra_chars
                                        )
                            except Exception as e:
                                st.error(f"Error processing page {i} of {pdf_file.name}: {e}")
                                continue # Continue if there is an error.
                                
                        # --- Save and Store ---
                        output_file_name = f"{pdf_name}_processed.docx"
                        output_path = os.path.join(temp_dir, output_file_name)
                        doc.save(output_path)
                        docx_files.append(output_path)

                    except Exception as e:
                        st.error(f"Error: {e} with file: {pdf_file.name}")
                        continue #Outer loop error.
                # --- Zip and Download ---
                if docx_files:  # Only proceed if DOCX files were created
                    zip_buffer = io.BytesIO()  # Create in-memory ZIP
                    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                        for docx_file in docx_files:
                            zip_file.write(docx_file, os.path.basename(docx_file))

                    st.download_button(
                        label="Download All Processed Documents as ZIP",
                        data=zip_buffer.getvalue(),
                        file_name="processed_documents.zip",
                        mime="application/zip"
                    )

            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")
            finally:
                # Cleanup: Delete the temp directory and its contents
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)  # Use shutil.rmtree for simplicity


elif choice == "Matn, Sharh, Hashiya Extraction":
    pdf_extraction_prompt = """
    You will be provided with images or scanned pages of a PDF file containing text in **Arabic**. Your task is to extract the content from each page and organize it into distinct sections. The division of sections must be based **strictly on the horizontal lines present on the page**, which act as section dividers. The output should be formatted in **JSON** according to the following structure:

    {
    "header": "text",
    "section1": "text",
    "section2": "text",
    "section3": "text",
    "footnotes": "text"
    }


    ### Key Instructions:

    1. **Horizontal Line as the Sole Section Divider**:
        - Use **only** the horizontal lines beneath the text to divide content into sections.
        - A horizontal line can:
        - Extend across the entire width of the page.
        - **Do not split text based on any other visual element** such as font size, paragraphs, or spacing.

    2. **Maximum Sections**:
        - A page can have up to **3 sections**,the **header**.the footnotes,.
        - If there are fewer than 4 sections based on the horizontal lines, only include the sections that exist.

    4. **Section Text**:
        - Each section begins **immediately after a horizontal line** and ends **just before the next horizontal line**.
        - **Do not include any text or symbols that appear on the horizontal line itself**.

    5. **Empty or Missing Sections**:
        - If a page lacks certain sections due to missing horizontal lines, exclude those sections from the JSON output.

    ### Formatting Notes:
        - Each page's JSON output must be **independent** of the others.
        - Maintain the **order of sections** as they appear on the page.
        - Handle Arabic text appropriately to ensure correct encoding and readability.


    """


    st.title("Matn, Sharh, Hashiya Extraction")
    st.write("Upload multiple PDFs, extract Arabic content, and download the results in separate Word documents (zipped).")

    # Input fields
    user_api_key = st.text_input("Enter your Gemini API Key (optional):", type="password")
    pdf_files = st.file_uploader("Upload multiple PDF files", type=["pdf"], accept_multiple_files=True)

    if st.button("Process PDFs"):
        if not pdf_files:
            st.error("Please upload at least one PDF file.")
        else:
            try:
                # Create temporary directories
                temp_dir = "temp"
                os.makedirs(temp_dir, exist_ok=True)
                # Initialize a list to store the paths of the generated Word files
                docx_files = []

                for pdf_file in pdf_files:
                    try: # Inner try block for file loop.
                        # ---  File-Specific Setup ---
                        pdf_name = os.path.splitext(pdf_file.name)[0]
                        pdf_path = os.path.join(temp_dir, pdf_file.name)
                        with open(pdf_path, "wb") as f:
                            f.write(pdf_file.read())

                        # Get total pages for each PDF
                        pdf_document = fitz.open(pdf_path)
                        total_pages = len(pdf_document)
                        pdf_document.close()

                        # --- Create Unique Image Directory ---
                        output_folder = os.path.join(temp_dir, f"temp_images_{pdf_name}")
                        os.makedirs(output_folder, exist_ok=True)

                        # ---  Per-File Processing ---
                        st.write(f"Processing: {pdf_file.name}")

                        # Convert PDF pages to images
                        pdf_to_images(pdf_path, output_folder, start_page=1, end_page=total_pages)

                        # Initialize Word document for *this* PDF
                        doc = Document()

                        # Extract content and process pages
                        st.write(f"Extracting content from {pdf_file.name}...")
                        # --- Pass correct out directory. ---
                        page_content = extract_pdf_content(
                            pdf_extraction_prompt,
                            output_folder, # Pass output folder
                            start_page=1,
                            end_page=total_pages,
                            api_key=user_api_key if user_api_key else None
                        )

                        #Process the extracted content into the Word document.
                        for i, page_data in enumerate(page_content,start=1):
                            try:
                                process_page2(
                                    page_data=page_data,
                                    doc=doc,
                                    page_number=i
                                )
                            except Exception as e:
                                st.error(f"Error processing page {i} of {pdf_file.name}: {e}")
                                continue

                        # --- Save and Store ---
                        output_file_name = f"{pdf_name}_processed.docx"
                        output_path = os.path.join(temp_dir, output_file_name)
                        doc.save(output_path)
                        docx_files.append(output_path)

                    except Exception as e:
                        st.error(f"Error processing file: {pdf_file.name} : {e}")
                        continue
            
                # --- Zip and Download ---
                if docx_files:
                    zip_buffer = io.BytesIO()
                    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                        for docx_file in docx_files:
                            zip_file.write(docx_file, os.path.basename(docx_file))

                    st.download_button(
                        label="Download All Processed Documents as ZIP",
                        data=zip_buffer.getvalue(),
                        file_name="processed_documents.zip",
                        mime="application/zip"
                    )

            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

            finally:
                # Cleanup: Delete the temp directory and its contents
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)  # Use shutil.rmtree for simplicity

# Find and Replace Section
elif choice == "Find and Replace":
    # Inject CSS to align text inputs to the right
    st.markdown(
        """
        <style>
        .right-align input {
            text-align: right !important;
        }
        .stTextInput input {
            text-align: right !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.title("Find and Replace in Arabic DOCX")
    st.write("Upload a DOCX file, specify text to find and replace, and download the updated document.")

    docx_file = st.file_uploader("Upload a DOCX file for Editing", type=["docx"])

    # Initialize session state for dynamic find-replace inputs
    if "find_replace_pairs" not in st.session_state:
        st.session_state.find_replace_pairs = [("", "")]

    st.subheader("Specify Text to Find and Replace (Use copy-paste for quick and better results)")

    # Dynamic inputs for find and replace pairs
    for i, (find_text, replace_text) in enumerate(st.session_state.find_replace_pairs):
        cols = st.columns(2)
        with cols[0]:
            st.session_state.find_replace_pairs[i] = (
                st.text_input(
                    f"Text to Find {i + 1} (Arabic):",
                    value=find_text,
                    key=f"find_{i}",
                    placeholder="Enter text to find",
                ),
                st.session_state.find_replace_pairs[i][1]
            )
        with cols[1]:
            st.session_state.find_replace_pairs[i] = (
                st.session_state.find_replace_pairs[i][0],
                st.text_input(
                    f"Replacement Text {i + 1} (Arabic):",
                    value=replace_text,
                    key=f"replace_{i}",
                    placeholder="Enter replacement text",
                )
            )

    # Button to add another pair of inputs
    if st.button("Add Another Find-Replace Pair"):
        st.session_state.find_replace_pairs.append(("", ""))

    output_file_name_edit = st.text_input("Enter output Word file name (without extension):", "مُتَجَدِّدة يَوْميًّا")
    output_file_name_edit +=".docx"
    if st.button("Perform Find and Replace"):
        if not docx_file:
            st.error("Please upload a DOCX file.")
        else:
            try:
                doc_path = os.path.join("temp", "uploaded_docx.docx")
                os.makedirs("temp", exist_ok=True)
                with open(doc_path, "wb") as f:
                    f.write(docx_file.read())

                doc = Document(doc_path)

                # Filter out empty find-replace pairs
                find_replace_pairs = [
                    (find_text.strip(), replace_text.strip())
                    for find_text, replace_text in st.session_state.find_replace_pairs
                    if find_text.strip()  # Include only valid "find" texts
                ]

                # Perform find and replace
                for paragraph in doc.paragraphs:
                    for find_text, replace_text in find_replace_pairs:
                        if find_text in paragraph.text:
                            paragraph.text = paragraph.text.replace(find_text, replace_text)

                # Save the updated document
                updated_path = os.path.join("temp", output_file_name_edit)
                doc.save(updated_path)

                # Provide download link
                with open(updated_path, "rb") as f:
                    st.download_button("Download Updated DOCX", f, file_name=output_file_name_edit)

            except Exception as e:
                st.error(f"Error processing the document: {e}")
