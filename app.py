# app.py
import streamlit as st
import backend # Assumes backend.py is in the same directory
import os
from io import BytesIO
import logging # Optional: if you want frontend logging too
import re # Import regular expressions module

# Configure logging (optional for app.py, more useful in backend)
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="ArabicPDF",
    page_icon="📄",
    layout="wide"
)

# --- Initialize Session State ---
# We need this to store the zip buffer for the download button
if 'zip_buffer' not in st.session_state:
    st.session_state.zip_buffer = None
if 'files_processed_count' not in st.session_state:
    st.session_state.files_processed_count = 0
if 'processing_complete' not in st.session_state:
    st.session_state.processing_complete = False


# --- Page Title ---
st.title("📄 ArabicPDF - PDF to Word Extractor")
st.markdown("Upload Arabic PDF files, apply rules via Gemini, and download as Word documents.")

# --- Sidebar for Configuration ---
st.sidebar.header("⚙️ Configuration")

# Try to get API key from secrets (for deployment) otherwise use text input (for local)
# Use st.secrets which is the documented way for Streamlit >= 1.1 secrets management
api_key_from_secrets = ""
if "GEMINI_API_KEY" in st.secrets:
    api_key_from_secrets = st.secrets["GEMINI_API_KEY"]

api_key = st.sidebar.text_input(
    "Enter your Google Gemini API Key",
    type="password",
    help="Required. Get your key from Google AI Studio.",
    value=api_key_from_secrets or "" # Pre-fill if found in secrets, else empty
)
# Add feedback about API key source
if api_key_from_secrets and not api_key:
    # If key is ONLY in secrets and user clears the box, we should still use the secret
    api_key = api_key_from_secrets # Ensure the secret key is used internally
    st.sidebar.success("API Key loaded from Secrets.", icon="✅")
elif api_key_from_secrets and api_key == api_key_from_secrets:
    # Key is from secrets and hasn't been changed by user
     st.sidebar.success("API Key loaded from Secrets.", icon="✅")
elif not api_key_from_secrets and not api_key:
    st.sidebar.warning("API Key not found in Streamlit Secrets or entered manually.", icon="🔑")
elif api_key and not api_key_from_secrets:
     st.sidebar.info("Using manually entered API Key.", icon="⌨️")
elif api_key and api_key_from_secrets and api_key != api_key_from_secrets:
     st.sidebar.info("Using manually entered API Key (overrides secret).", icon="⌨️")


# --- Model Selection Update ---
st.sidebar.header("🤖 Gemini Model")
# Define available models, putting 1.5 Flash first
available_models = [
    "gemini-1.5-flash-latest", # This is the latest Flash model
    "gemini-1.5-pro-latest",
    "gemini-pro", # Older generation
]
model_name = st.sidebar.selectbox(
    "Select Gemini Model:",
    options=available_models,
    index=0, # Default to gemini-1.5-flash-latest
    help="`gemini-1.5-flash-latest` is recommended for speed and cost-effectiveness."
)
st.sidebar.caption(f"Using: `{model_name}`") # Show the selected model

# --- Extraction Rules ---
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
    label_visibility="collapsed", # Hides the default label above the uploader
    # When files change, reset the processing state and hide the old download button
    on_change=lambda: (
        st.session_state.update({
            'zip_buffer': None,
            'files_processed_count': 0,
            'processing_complete': False
            })
    )
)

# --- Buttons Area ---
col1, col2 = st.columns([3, 2]) # Adjust ratio as needed for button size/spacing

with col1:
    process_button_clicked = st.button(
        "✨ Process PDFs and Generate Word Files",
        key="process_button",
        use_container_width=True # Make button fill column width
    )

with col2:
    # Show download button only if zip_buffer exists in session state
    if st.session_state.zip_buffer:
        st.download_button(
            label=f"📥 Download All ({st.session_state.files_processed_count}) Word Files (.zip)",
            data=st.session_state.zip_buffer,
            file_name="arabic_pdf_word_files.zip",
            mime="application/zip",
            key="download_zip_button_main", # Use a unique key
            use_container_width=True # Make button fill column width
        )
    # Optional: add a placeholder if you want the space to be reserved even when button isn't shown
    # else:
    #     st.write("") # Or st.empty()

# --- Processing Logic ---
if process_button_clicked:
    # Reset state before starting a new processing job
    st.session_state.zip_buffer = None
    st.session_state.files_processed_count = 0
    st.session_state.processing_complete = False

    if uploaded_files:
        st.info(f"{len(uploaded_files)} PDF file(s) selected.")

        # Explicitly check for API key right before processing
        if not api_key:
            st.error("❌ Please enter or configure your Gemini API Key in the sidebar.")
        elif not rules_prompt:
            st.warning("⚠️ The 'Extraction Rules' field is empty. Processing will continue without specific instructions for Gemini.")
        else:
            processed_files_data = [] # List to hold (filename, BytesIO) tuples for zipping
            # Initialize UI elements for progress reporting
            progress_bar = st.progress(0)
            status_text = st.empty() # Placeholder for detailed status updates
            results_container = st.container() # Container to show success/error messages per file

            total_files = len(uploaded_files)
            files_processed_count = 0

            for i, uploaded_file in enumerate(uploaded_files):
                original_filename = uploaded_file.name
                current_file_status = f"'{original_filename}' ({i+1}/{total_files})"

                # --- Change 2: Modify Output Filename ---
                file_name_base = ""
                # Try to find 'part' followed by digits (case-insensitive)
                match = re.search(r'part(\d+)', original_filename, re.IGNORECASE)
                if match:
                    file_name_base = match.group(1) # Extract the number
                    logging.info(f"Extracted number '{file_name_base}' from filename '{original_filename}'.")
                else:
                    # Fallback: use original filename without extension if pattern not found
                    file_name_base = os.path.splitext(original_filename)[0]
                    logging.warning(f"Filename pattern 'part<number>' not found in '{original_filename}'. Using base name '{file_name_base}'.")
                    with results_container: # Show warning in UI as well
                         st.warning(f"Filename pattern 'part<number>' not found in '{original_filename}'. Using base name '{file_name_base}'.")

                docx_filename = f"{file_name_base}.docx"
                # --- End Change 2 ---


                # Update overall status
                status_text.info(f"🔄 Processing {current_file_status}...")

                # 1. Extract Text
                with results_container:
                    st.markdown(f"--- \n**Processing: {original_filename}**")
                # logging.info(f"Extracting text from {current_file_status}...") # Optional frontend log
                raw_text = backend.extract_text_from_pdf(uploaded_file)

                # Check extraction result (backend should return "" for empty/error)
                if raw_text is None: # Defensive check, should not happen if backend is correct
                     with results_container:
                         st.error(f"❌ Unexpected error extracting text from {original_filename}. Skipping.")
                     progress_bar.progress((i + 1) / total_files)
                     continue

                processed_text = "" # Initialize processed_text for this file
                gemini_error_occurred = False # Flag for Gemini specific errors

                if not raw_text.strip():
                     with results_container:
                         st.warning(f"⚠️ No text extracted from {original_filename}. Creating empty Word file '{docx_filename}'.")
                     # Proceed to create an empty Word file
                else:
                    # 2. Process with Gemini (only if text was extracted)
                    # logging.info(f"Sending text from {current_file_status} to Gemini ({model_name})...") # Optional
                    status_text.info(f"🤖 Sending text from {current_file_status} to Gemini ({model_name})...")
                    processed_text_result = backend.process_text_with_gemini(api_key, model_name, raw_text, rules_prompt)

                    # Check Gemini result
                    if processed_text_result is None or (isinstance(processed_text_result, str) and processed_text_result.startswith("Error:")):
                         with results_container:
                             st.error(f"❌ Gemini error for {original_filename}: {processed_text_result or 'Unknown API error'}")
                         gemini_error_occurred = True
                         # Option: Fallback to raw text if desired? (Keep commented out unless needed)
                         # processed_text = raw_text
                         # with results_container:
                         #     st.warning(f"⚠️ Using raw extracted text for {original_filename} due to Gemini error.")
                    else:
                         processed_text = processed_text_result
                         # logging.info(f"Successfully processed text for {current_file_status} with Gemini.") # Optional


                # 3. Create Word Document (Skip only if a Gemini error occurred AND no fallback is used)
                if not gemini_error_occurred: # If Gemini worked OR if no text was extracted (create empty) OR if fallback is enabled
                    # logging.info(f"Creating Word document for '{docx_filename}'...") # Optional
                    status_text.info(f"📝 Creating Word document '{docx_filename}'...")
                    word_doc_stream = backend.create_word_document(processed_text) # Handles empty string correctly

                    if word_doc_stream:
                        # Use the potentially modified docx_filename here
                        processed_files_data.append((docx_filename, word_doc_stream))
                        files_processed_count += 1
                        with results_container:
                            st.success(f"✅ Successfully created '{docx_filename}'")
                    else:
                        with results_container:
                            st.error(f"❌ Failed to create Word document for {original_filename}.")
                # else: # If gemini_error_occurred is True (and no fallback), we skip Word creation

                # Update progress bar after processing each file
                progress_bar.progress((i + 1) / total_files)

            # Clear transient status messages after the loop
            status_text.empty()
            progress_bar.empty() # Or set to 1.0 if preferred: progress_bar.progress(1.0)

            # 4. Zip Files and Update Session State (No download button here anymore)
            if processed_files_data:
                results_container.info(f"💾 Zipping {files_processed_count} processed Word document(s)...")
                zip_buffer = backend.create_zip_archive(processed_files_data)

                if zip_buffer:
                    # Store the buffer and count in session state
                    st.session_state.zip_buffer = zip_buffer
                    st.session_state.files_processed_count = files_processed_count
                    st.session_state.processing_complete = True
                    # No download button needed here, it's handled above
                    results_container.success(f"✅ Processing complete. Click the 'Download All' button above to get the zip file.")
                    # We need to rerun the script for the download button to update/appear
                    st.rerun()
                else:
                    st.error("❌ Failed to create zip archive.")
                    st.session_state.processing_complete = True # Mark as complete even on error
            elif not uploaded_files: # If button was clicked but files list became empty
                 pass # No message needed here, handled by initial check
            else: # If files were uploaded but none processed successfully
                 st.warning("⚠️ No files were successfully processed to include in a zip archive.")
                 st.session_state.processing_complete = True # Mark as complete

    else: # No files uploaded when process button clicked
        st.warning("⚠️ Please upload PDF files first.")
        # Ensure download button is hidden if no files were ever processed
        st.session_state.zip_buffer = None
        st.session_state.files_processed_count = 0
        st.session_state.processing_complete = False


# Display initial message if no files are uploaded and processing hasn't happened
if not uploaded_files and not st.session_state.processing_complete:
    st.info("Upload one or more PDF files using the uploader above, configure settings in the sidebar, and click 'Process PDFs'.")

# --- Footer or additional info ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
