# app.py
import streamlit as st
import backend
import os
from io import BytesIO

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="ArabicPDF",
    page_icon="📄",
    layout="wide"
)

# --- Page Title ---
st.title("📄 ArabicPDF - PDF to Word Extractor")
st.markdown("Upload Arabic PDF files, apply rules via Gemini, and download as Word documents.")

# --- Sidebar for Configuration ---
st.sidebar.header("⚙️ Configuration")
api_key = st.sidebar.text_input("Enter your Google Gemini API Key", type="password", help="Get your key from Google AI Studio.")
# Use Gemini 1.5 Flash - clarify if user really meant 2.0
# model_name = "gemini-1.5-flash-latest" # Standard name
# Let's make it configurable just in case
model_name = st.sidebar.selectbox(
    "Select Gemini Model",
    ["gemini-1.5-flash-latest", "gemini-1.5-pro-latest", "gemini-pro"], # Add more if needed
    index=0, # Default to flash
    help="Ensure the selected model supports the required input/output capabilities."
)


st.sidebar.header("📜 Extraction Rules")
default_rules = """
1. Correct any OCR errors or misinterpretations in the Arabic text.
2. Ensure proper Arabic script formatting, including ligatures and character forms.
3. Remove any headers, footers, or page numbers that are not part of the main content.
4. Structure the text into logical paragraphs based on the original document.
5. Maintain the original meaning and intent of the text.
6. If tables are present, try to format them clearly using tab separation or simple markdown.
"""
rules_prompt = st.sidebar.text_area(
    "Enter the rules Gemini should follow:",
    value=default_rules,
    height=250,
    help="Provide clear instructions for how Gemini should process the extracted text."
)

# --- Main Area for File Upload and Processing ---
st.header("📁 Upload PDFs")
uploaded_files = st.file_uploader(
    "Choose PDF files",
    type="pdf",
    accept_multiple_files=True,
    label_visibility="collapsed" # Hides the default label above the uploader
)

# --- Processing Logic ---
if uploaded_files:
    st.info(f"{len(uploaded_files)} PDF file(s) selected.")

    if st.button("✨ Process PDFs and Generate Word Files"):
        if not api_key:
            st.error("❌ Please enter your Gemini API Key in the sidebar.")
        elif not rules_prompt:
            st.warning("⚠️ The 'Extraction Rules' field is empty. Processing will continue without specific instructions for Gemini.")
        else:
            processed_files_data = [] # List to hold (filename, BytesIO) tuples for zipping

            # Progress bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            total_files = len(uploaded_files)

            for i, uploaded_file in enumerate(uploaded_files):
                file_name_base = os.path.splitext(uploaded_file.name)[0]
                status_text.info(f"Processing '{uploaded_file.name}' ({i+1}/{total_files})...")

                # 1. Extract Text
                status_text.info(f"[{i+1}/{total_files}] Extracting text from '{uploaded_file.name}'...")
                raw_text = backend.extract_text_from_pdf(uploaded_file)

                if raw_text is None:
                    st.error(f"Failed to extract text from '{uploaded_file.name}'. Skipping this file.")
                    progress_bar.progress((i + 1) / total_files)
                    continue # Skip to the next file

                if not raw_text.strip():
                    st.warning(f"⚠️ No text could be extracted from '{uploaded_file.name}'. It might be image-based or empty. Skipping Gemini processing for this file, an empty Word file will be created.")
                    processed_text = "" # Use empty string
                else:
                    # 2. Process with Gemini
                    status_text.info(f"[{i+1}/{total_files}] Sending text from '{uploaded_file.name}' to Gemini ({model_name})...")
                    processed_text = backend.process_text_with_gemini(api_key, model_name, raw_text, rules_prompt)

                    if processed_text is None or processed_text.startswith("Error:"):
                         st.error(f"Failed to process text from '{uploaded_file.name}' using Gemini. {processed_text or ''}")
                         # Option: Fallback to raw text? Or skip? Let's skip creating doc for this file on error.
                         progress_bar.progress((i + 1) / total_files)
                         continue # Skip to next file if Gemini fails


                # 3. Create Word Document
                status_text.info(f"[{i+1}/{total_files}] Creating Word document for '{file_name_base}.docx'...")
                word_doc_stream = backend.create_word_document(processed_text) # Pass potentially empty processed_text

                if word_doc_stream:
                    docx_filename = f"{file_name_base}.docx"
                    processed_files_data.append((docx_filename, word_doc_stream))
                    st.success(f"✓ Successfully processed '{uploaded_file.name}' -> '{docx_filename}'")
                else:
                    st.error(f"Failed to create Word document for '{uploaded_file.name}'.")

                # Update progress bar
                progress_bar.progress((i + 1) / total_files)

            status_text.empty() # Clear status text
            progress_bar.empty() # Clear progress bar

            # 4. Zip Files and Provide Download Button
            if processed_files_data:
                st.info("Zipping processed Word documents...")
                zip_buffer = backend.create_zip_archive(processed_files_data)

                if zip_buffer:
                    st.download_button(
                        label="📥 Download All Word Files (.zip)",
                        data=zip_buffer,
                        file_name="arabic_pdf_word_files.zip",
                        mime="application/zip",
                        key="download_zip_button" # Add a key
                    )
                else:
                    st.error("❌ Failed to create zip archive.")
            else:
                st.warning("⚠️ No files were successfully processed to include in a zip archive.")

else:
    st.info("Upload one or more PDF files to begin.")

# --- Footer or additional info ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
