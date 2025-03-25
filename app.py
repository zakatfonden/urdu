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
from typing import List
import zipfile
import shutil

# --- Import your backend functions ---
from backend import pdf_to_images, extract_pdf_content, process_page, process_page2

# Load environment variables (for API key, if you're using one)
load_dotenv()

# --- Helper Functions ---

def process_single_file(input_filepath: str, output_filepath: str, choice: str, user_api_key: str = None, start_page: int = 1, end_page: int = 0, footnotes: bool = False, headers: bool = False, extra_chars: List[str] = None) -> None:
    """Processes a single PDF file based on the selected 'choice'."""

    # --- IMPORT BACKEND FUNCTIONS HERE (within function scope) ---
    from backend import pdf_to_images, extract_pdf_content, process_page, process_page2


    if extra_chars is None:
        extra_chars = []

    if choice == "Process PDF":
        pdf_extraction_prompt = """
           You will be given pages of a PDF file containing text in Arabic.  ...
           """  # Your Process PDF prompt
    elif choice == "Matn, Sharh, Hashiya Extraction":
        pdf_extraction_prompt = """
        You will be provided with images or scanned pages of a PDF file containing text in Arabic. ...
        """ # Your Matn, Sharh prompt.
    else:
        raise ValueError(f"Invalid choice: {choice}")


    try:
        # 1. Validate and enforce page limits
        pdf_document = fitz.open(input_filepath)
        total_pages = len(pdf_document)
        pdf_document.close()

        if end_page == 0 or end_page > total_pages:
            end_page = total_pages

        if not user_api_key and (end_page - start_page + 1) > 10:
            st.warning("API key not provided. Limiting processing to 10 pages.")
            end_page = min(start_page + 9, total_pages)

        # 2. Convert PDF pages to images (using the imported function)
        temp_images_folder = "temp_images"
        pdf_to_images(input_filepath, temp_images_folder, start_page=start_page, end_page=end_page)

        # 3. Initialize Word document
        doc = Document()

        # 4. Extract content and process pages
        st.write("Extracting content from the PDF...")

        page_content = extract_pdf_content(
            pdf_extraction_prompt,
            start_page=start_page,
            end_page=end_page,
            api_key=user_api_key if user_api_key else None
        )



        # Process the extracted content into the Word document
        i = start_page  # Keep track of the *original* page number
        for page_data in page_content:
            st.write(f"Content extraction complete for page {i}.", page_data)
            try:
                if choice == "Process PDF":
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
                elif choice == "Matn, Sharh, Hashiya Extraction":
                     process_page2(
                        page_data=page_data,
                        doc=doc,
                        page_number=i
                        )
            except Exception as e:
                st.error(f"Error processing page {i}: {e}")
                continue  # Continue to the next page even if one fails
            i += 1

        # 5. Save the Word document
        doc.save(output_filepath)
        shutil.rmtree(temp_images_folder)  # cleanup temp images

    except Exception as e:
        st.error(f"Error during processing: {e}")
        raise  # Re-raise the exception

def create_downloadable_zip(processed_files: List[str], zip_filename: str = "processed_files.zip") -> str:
    """Creates a ZIP file containing all processed files."""
    try:
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in processed_files:
                if os.path.exists(file):  # Check if file exists
                    zipf.write(file, os.path.basename(file))  # Add to ZIP, keep only filename
                else:
                    st.warning(f"Processed file not found: {file}")
        st.success(f"ZIP file created: {zip_filename}")
        return zip_filename
    except Exception as e:
        st.error(f"Error creating ZIP file: {e}")
        return ""

def find_and_replace_in_docx(doc: Document, find_texts: List[str], replace_texts: List[str]) -> None:
    """
    Replaces all occurrences of specified Arabic text in the document, handling potential errors.
    """
    if len(find_texts) != len(replace_texts):
        raise ValueError("Find and Replace lists must have the same length.")

    try:
        for find_text, replace_text in zip(find_texts, replace_texts):
            for paragraph in doc.paragraphs:
                if find_text in paragraph.text:
                    paragraph.text = paragraph.text.replace(find_text, replace_text)

            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if find_text in cell.text:
                            cell.text = cell.text.replace(find_text, replace_text)
    except Exception as e:
        st.error(f"An error occurred during find and replace: {e}")
        # Consider logging the error or taking other actions here.



# --- Streamlit App ---

st.sidebar.header("Navigation")
options = ["Process PDF", "Matn, Sharh, Hashiya Extraction", "Find and Replace"]
choice = st.sidebar.radio("Go to:", options)



# --- Main Processing Logic (Batch Upload) ---
if choice in ["Process PDF", "Matn, Sharh, Hashiya Extraction"]:
    st.title("Arabic PDF Batch Processing")
    st.write("Upload multiple PDF files, extract Arabic content, and download the results in a single ZIP file.")

    # API Key
    user_api_key = st.text_input("Enter your Gemini API Key (optional):", type="password")

    # Multiple File Upload
    uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)

    # Processing Options
    start_page = st.number_input("Start Page (1-based index):", value=1)
    end_page = st.number_input("End Page (inclusive):", value=1)

    if choice == "Process PDF":
        footnotes = st.checkbox("Include Footnotes", value=False)
        headers = st.checkbox("Include Headers and Footers", value=False)
        extra_chars_str = st.text_area("Characters to Remove (comma-separated):", "")
        extra_chars = [char.strip() for char in extra_chars_str.split(",") if char.strip()]
    else:  # For "Matn, Sharh..."
        footnotes = False  # No footnotes in this mode
        headers = False    # No headers in this mode
        extra_chars = []   # No extra chars to remove

    # Process Button
    if st.button("Process Files"):
        if not uploaded_files:
            st.error("Please upload at least one PDF file.")
        else:
            processed_files = []
            temp_dir = "temp_processing"  # Use a single temp dir
            os.makedirs(temp_dir, exist_ok=True)

            for uploaded_file in uploaded_files:
                try:
                    # Save uploaded file
                    input_filepath = os.path.join(temp_dir, uploaded_file.name)
                    with open(input_filepath, "wb") as f:
                        f.write(uploaded_file.read())

                    # Output file path
                    output_filename = "processed_" + os.path.splitext(uploaded_file.name)[0] + ".docx"
                    output_filepath = os.path.join(temp_dir, output_filename)

                    # Process the file
                    process_single_file(
                        input_filepath,
                        output_filepath,
                        choice,
                        user_api_key,
                        start_page,
                        end_page,
                        footnotes,
                        headers,
                        extra_chars
                    )
                    processed_files.append(output_filepath)  # Add to list

                except Exception as e:
                    st.error(f"Failed to process {uploaded_file.name}: {e}")
                    # Continue with the next file

            # Create ZIP file
            if processed_files:
                zip_file_path = create_downloadable_zip(processed_files)
                if zip_file_path:
                    with open(zip_file_path, "rb") as f:
                        st.download_button("Download All Processed Files (ZIP)", f, file_name="processed_files.zip")
                    os.remove(zip_file_path)  # Clean up zip file
                else:
                    st.error("Failed to create ZIP file.")
            else:
                st.warning("No files were successfully processed.")

            shutil.rmtree(temp_dir)  # Clean up temp dir
            st.success("Batch processing complete!")

# --- Find and Replace Section ---
elif choice == "Find and Replace":
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

    # Initialize session state for find/replace pairs
    if "find_replace_pairs" not in st.session_state:
        st.session_state.find_replace_pairs = [("", "")]

    st.subheader("Specify Text to Find and Replace (Use copy-paste for quick and better results)")

    # Dynamic inputs for find/replace
    for i, (find_text, replace_text) in enumerate(st.session_state.find_replace_pairs):
        cols = st.columns(2)
        with cols[0]:
            st.session_state.find_replace_pairs[i] = (
                st.text_input(f"Text to Find {i + 1} (Arabic):", value=find_text, key=f"find_{i}", placeholder="Enter text to find"),
                st.session_state.find_replace_pairs[i][1]  # Keep previous replace_text
            )
        with cols[1]:
            st.session_state.find_replace_pairs[i] = (
                st.session_state.find_replace_pairs[i][0],  # Keep previous find_text
                st.text_input(f"Replacement Text {i + 1} (Arabic):", value=replace_text, key=f"replace_{i}", placeholder="Enter replacement text")
            )

    # Button to add another pair
    if st.button("Add Another Find-Replace Pair"):
        st.session_state.find_replace_pairs.append(("", ""))

    output_file_name_edit = st.text_input("Enter output Word file name (without extension):", "مُتَجَدِّدة يَوْميًّا")
    output_file_name_edit += ".docx" #add extension

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

                find_replace_pairs = [
                    (find_text.strip(), replace_text.strip())
                    for find_text, replace_text in st.session_state.find_replace_pairs
                    if find_text.strip()  # Only process if find_text is not empty
                ]
                # Use the function
                find_and_replace_in_docx(doc, [x[0] for x in find_replace_pairs], [x[1] for x in find_replace_pairs])


                updated_path = os.path.join("temp", output_file_name_edit)
                doc.save(updated_path)

                with open(updated_path, "rb") as f:
                    st.download_button("Download Updated DOCX", f, file_name=output_file_name_edit)
                # Clean up
                os.remove(doc_path)
                os.remove(updated_path)

            except Exception as e:
                st.error(f"Error processing the document: {e}")
