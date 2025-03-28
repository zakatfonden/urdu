# app.py (Modified)

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
# Assuming process_page2 is still needed for the other option
from backend import pdf_to_images, extract_pdf_content, process_page , process_page2
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
    # --- MODIFICATION: Moved original prompt here to be editable ---
    default_pdf_extraction_prompt = """
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
- Additionally, if **any bold text** is found **inside the main content**, it should also be treated as a heading and enclose it in asterisks (`*`), like this:
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
    st.write("Upload a PDF, extract Arabic content based on the instructions below, and download the result in a Word document.")

    # Input fields
    user_api_key = st.text_input("Enter your Gemini API Key (optional):", type="password")
    pdf_file = st.file_uploader("Upload a PDF file", type=["pdf"])
    output_file_name = st.text_input("Enter output Word file name (with .docx extension):", "result.docx")
    start_page = st.number_input("Start Page (1-based index):", value=1, min_value=1)
    # --- MODIFICATION: Changed default end_page value ---
    end_page = st.number_input("End Page (inclusive):", value=10, min_value=1) # Default to 10

    # --- MODIFICATION: Added text area for editable prompt ---
    st.subheader("AI Extraction Instructions (Edit if needed)")
    user_edited_prompt = st.text_area(
        "Prompt for Gemini AI:",
        value=default_pdf_extraction_prompt,
        height=400
    )

    # --- MODIFICATION: Removed checkboxes and character removal input ---
    # footnotes = st.checkbox("Include Footnotes", value=False) # REMOVED
    # headers = st.checkbox("Include Headers and Footers", value=False) # REMOVED
    # extra_chars = st.text_area("Characters to Remove (comma-separated):", "").split(",") # REMOVED

    if st.button("Process PDF"):
        if not pdf_file:
            st.error("Please upload a PDF file.")
        elif not user_edited_prompt.strip():
            st.error("The AI Extraction Instructions cannot be empty.")
        else:
            try:
                # Step 1: Save the uploaded PDF
                temp_dir = "temp"
                pdf_path = os.path.join(temp_dir, "uploaded_pdf.pdf")
                os.makedirs(temp_dir, exist_ok=True)
                with open(pdf_path, "wb") as f:
                    f.write(pdf_file.read())

                # Step 2: Validate and enforce page limits
                try:
                    pdf_document = fitz.open(pdf_path)
                    total_pages = len(pdf_document)
                    pdf_document.close()
                except Exception as pdf_err:
                    st.error(f"Error opening PDF: {pdf_err}")
                    st.stop() # Stop execution if PDF is invalid

                # Adjust end_page if it exceeds total pages or is 0
                if end_page == 0 or end_page > total_pages:
                    end_page = total_pages
                    st.info(f"Adjusted end page to the last page of the PDF: {total_pages}")

                # Limit pages if no API key is provided (keep this check)
                if not user_api_key and (end_page - start_page + 1) > 10:
                    st.warning("API key not provided. Limiting processing to 10 pages.")
                    end_page = min(start_page + 9, total_pages)

                # Ensure start_page is not greater than end_page after adjustments
                if start_page > end_page:
                    st.error(f"Start page ({start_page}) cannot be greater than end page ({end_page}).")
                    st.stop()

                # Step 3: Convert PDF pages to images
                output_folder = "temp_images"
                st.write(f"Converting PDF pages {start_page} to {end_page} to images...")
                pdf_to_images(pdf_path, output_folder, start_page=start_page, end_page=end_page)
                st.write("Image conversion complete.")

                # Step 4: Initialize Word document
                doc = Document()

                # Step 5: Extract content and process pages
                st.write("Extracting content from the PDF using the provided instructions...")

                progress_bar = st.progress(0)
                status_text = st.empty()

                try:
                    # --- MODIFICATION: Pass the user_edited_prompt ---
                    page_content_generator = extract_pdf_content(
                        pdf_extraction_prompt=user_edited_prompt, # Use edited prompt
                        start_page=start_page,
                        end_page=end_page,
                        api_key=user_api_key if user_api_key else None
                    )

                    # Process the extracted content into the Word document
                    total_pages_to_process = end_page - start_page + 1
                    processed_pages = 0

                    for i, page_data in enumerate(page_content_generator):
                        current_page_num_actual = start_page + i
                        status_text.text(f"Processing page {current_page_num_actual}/{end_page}...")

                        if isinstance(page_data, dict) and "error" in page_data:
                             st.warning(f"Skipping page {page_data.get('page', current_page_num_actual)} due to error: {page_data['error']}")
                             continue # Skip processing this page

                        if not isinstance(page_data, dict):
                            st.warning(f"Skipping page {current_page_num_actual} due to unexpected data format: {type(page_data)}")
                            continue

                        st.write(f"Raw data received for page {current_page_num_actual}: {page_data}") # Debugging output

                        try:
                            # --- MODIFICATION: Simplified process_page call ---
                            process_page(
                                page_data=page_data,
                                doc=doc,
                                page_number=current_page_num_actual # Pass actual page number for context
                            )
                            processed_pages += 1
                            progress_bar.progress(processed_pages / total_pages_to_process)

                        except Exception as page_proc_e:
                            st.error(f"Error formatting page {current_page_num_actual} into Word: {page_proc_e}")
                            # Continue to the next page even if one fails formatting

                    status_text.text("Content extraction and formatting complete.")

                except Exception as extraction_e:
                    st.error(f"Error during content extraction: {extraction_e}")
                    st.stop() # Stop if extraction fails critically

                # Step 6: Save the Word document
                output_path = os.path.join(temp_dir, output_file_name)
                doc.save(output_path)
                st.success(f"Word document saved successfully: {output_file_name}")

                # Step 7: Provide a download link
                with open(output_path, "rb") as f:
                    st.download_button(
                        label="Download Word Document",
                        data=f,
                        file_name=output_file_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )

            except Exception as e:
                st.error(f"An overall error occurred: {e}")
            finally:
                 # Optional: Clean up temp files if desired
                 # import shutil
                 # if os.path.exists(temp_dir):
                 #     shutil.rmtree(temp_dir)
                 # if os.path.exists(output_folder):
                 #     shutil.rmtree(output_folder)
                 pass

# --- Keep other sections (Matn/Sharh/Hashiya, Find/Replace) as they were ---
elif choice == "Matn, Sharh, Hashiya Extraction":
    # ... (Keep the original code for this section) ...
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
    st.write("Upload a PDF, extract Arabic content, and download the result in a Word document.")

    # Input fields
    user_api_key = st.text_input("Enter your Gemini API Key (optional):", type="password")
    pdf_file = st.file_uploader("Upload a PDF file", type=["pdf"])
    output_file_name = st.text_input("Enter output Word file name (with .docx extension):", "result.docx")
    start_page = st.number_input("Start Page (1-based index):",value=1)
    end_page = st.number_input("End Page (inclusive):",value=1)

    # Processing options

    if st.button("Process PDF"):
        if not pdf_file:
            st.error("Please upload a PDF file.")
        else:
            try:
                # Step 1: Save the uploaded PDF
                pdf_path = os.path.join("temp", "uploaded_pdf.pdf")
                os.makedirs("temp", exist_ok=True)
                with open(pdf_path, "wb") as f:
                    f.write(pdf_file.read())

                # Step 2: Validate and enforce page limits
                pdf_document = fitz.open(pdf_path)
                total_pages = len(pdf_document)
                pdf_document.close()

                if end_page == 0 or end_page > total_pages:
                    end_page = total_pages

                if not user_api_key and (end_page - start_page + 1) > 10:
                    st.warning("API key not provided. Limiting processing to 10 pages.")
                    end_page = min(start_page + 9, total_pages)

                # Step 3: Convert PDF pages to images
                output_folder = "temp_images"
                pdf_to_images(pdf_path, output_folder, start_page=start_page, end_page=end_page)

                # Step 4: Initialize Word document
                doc = Document()

                # Step 5: Extract content and process pages
                st.write("Extracting content from the PDF...")


                try:
                    page_content = extract_pdf_content(
                        pdf_extraction_prompt,
                        start_page=start_page,
                        end_page=end_page,
                        api_key=user_api_key if user_api_key else None
                    )

                    # Process the extracted content into the Word document
                    i=1
                    for page_data in page_content:
                        st.write("Content extraction complete.",page_data)
                        try:
                                process_page2(
                                page_data=page_data,
                                doc=doc,
                                page_number=i
                                )

                        except Exception as e:
                            st.error(f"Error processing page {i}: {e}")
                            continue
                        i=i+1
                except Exception as e:
                    st.error(f"Error processing page {e}")

                # Step 6: Save the Word document
                output_path = os.path.join("temp", output_file_name)
                doc.save(output_path)

                # Step 7: Provide a download link
                with open(output_path, "rb") as f:
                    st.download_button("Download Word Document", f, file_name=output_file_name)

            except Exception as e:
                st.error(f"Error: {e}")


elif choice == "Find and Replace":
    # ... (Keep the original code for this section) ...
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
