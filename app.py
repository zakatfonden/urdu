# 1. All import statements first
import streamlit as st
import backend  # Assumes backend.py is in the same directory
import os
from io import BytesIO
import logging
import tempfile

# 2. IMMEDIATELY after imports, call st.set_page_config() ONCE
st.set_page_config(
    page_title="ArabicPDF",
    page_icon="📄",
    layout="wide"
)

# Configure basic logging if needed for debugging in terminal
# You can uncomment this if you want detailed logs in your terminal
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logger = logging.getLogger(__name__)


# 3. NOW you can have other code, including other Streamlit commands
# --- Initialize Session State ---
# Ensure keys exist when the app first loads or reloads
default_state = {
    'zip_buffer': None,
    'files_processed_count': 0,
    'processing_complete': False,
    'processing_started': False,  # Flag to know if processing loop is active
    'last_uploaded_files_count': 0  # To help detect file changes reliably
}
for key, value in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = value


def reset_processing_state():
    """Resets state related to processing results and status."""
    st.session_state.zip_buffer = None
    st.session_state.files_processed_count = 0
    st.session_state.processing_complete = False
    st.session_state.processing_started = False
    # logger.info("Processing state reset.")


# --- Page Title ---
st.title("📄 ArabicPDF - PDF to Word Extractor")
st.markdown("Upload Arabic PDF files, apply rules via Gemini, and download as Word documents.")

# --- Sidebar for Configuration ---
st.sidebar.header("⚙️ Configuration")

# --- API Key Input ---
# Use st.secrets AFTER set_page_config
api_key_from_secrets = st.secrets.get("GEMINI_API_KEY", "")
api_key = st.sidebar.text_input(
    "Enter your Google Gemini API Key",
    type="password",
    help="Required. Get your key from Google AI Studio.",
    value=api_key_from_secrets or ""
)
# --- API Key Feedback ---
if api_key_from_secrets and api_key == api_key_from_secrets:
    st.sidebar.success("API Key loaded from Secrets.", icon="✅")
elif not api_key_from_secrets and not api_key:
    st.sidebar.warning("API Key not found or entered.", icon="🔑")
elif api_key and not api_key_from_secrets:
    st.sidebar.info("Using manually entered API Key.", icon="⌨️")
elif api_key and api_key_from_secrets and api_key != api_key_from_secrets:
    st.sidebar.info("Using manually entered API Key (overrides secret).", icon="⌨️")

# --- Model Info (Hardcoded) ---
# Since the model is hardcoded in backend.py, we just display info here
st.sidebar.header("🤖 Gemini Model")
st.sidebar.info("Using model: `gemini-2.0-flash` (Hardcoded)")

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
    "Enter the rules Gemini should follow:", value=default_rules, height=250,
    help="Provide clear instructions for how Gemini should process the extracted text."
)

# --- Main Area for File Upload and Processing ---
st.header("📁 Upload PDFs")
uploaded_files = st.file_uploader(
    "Choose PDF files",
    type="pdf",
    accept_multiple_files=True,
    label_visibility="collapsed",
    key="pdf_uploader"
)

# Detect if files have changed since last run to reset state
current_file_count = len(uploaded_files) if uploaded_files else 0
if current_file_count != st.session_state.last_uploaded_files_count:
    # logger.info(f"File count changed from {st.session_state.last_uploaded_files_count} to {current_file_count}. Resetting state.")
    reset_processing_state()
    st.session_state.last_uploaded_files_count = current_file_count
    # Force a rerun NOW if files changed, before buttons are rendered with old state
    st.rerun()

# --- Buttons Area ---
col1, col2 = st.columns([3, 2])

with col1:
    # Disable process button if processing is already running
    process_button_clicked = st.button(
        "✨ Process PDFs and Generate Word Files",
        key="process_button",
        use_container_width=True,
        disabled=st.session_state.processing_started  # Disable while processing
    )

with col2:
    # Download button visibility depends on zip_buffer existence AND processing not running
    if st.session_state.zip_buffer and not st.session_state.processing_started:
        st.download_button(
            label=f"📥 Download All ({st.session_state.files_processed_count}) Word Files (.zip)",
            data=st.session_state.zip_buffer,
            file_name="arabic_pdf_word_files.zip",
            mime="application/zip",
            key="download_zip_button_main",
            use_container_width=True
        )
        # logger.info("Download button rendered.")

# --- UI Elements for Progress ---
# Placeholders need to be defined *before* the processing logic that might update them
progress_bar_placeholder = st.empty()
status_text_placeholder = st.empty()
results_container = st.container()

# --- Processing Logic ---
if process_button_clicked:
    # logger.info("Process button clicked.")
    # Immediately reset relevant state parts and set processing flag
    reset_processing_state()  # Clear previous results
    st.session_state.processing_started = True  # Signal that processing is starting

    # Checks before starting loop
    if not uploaded_files:
        st.warning("⚠️ Please upload PDF files first.")
        st.session_state.processing_started = False  # Reset flag as we didn't start
    elif not api_key:
        st.error("❌ Please enter or configure your Gemini API Key in the sidebar.")
        st.session_state.processing_started = False  # Reset flag
    elif not rules_prompt:
        st.warning("⚠️ The 'Extraction Rules' field is empty. Processing without specific instructions.")
        # Proceed even if rules are empty, so don't reset flag here

    # Only proceed if files are uploaded AND API key is present
    if uploaded_files and api_key and st.session_state.processing_started:
        # logger.info(f"Starting processing loop for {len(uploaded_files)} files.")
        st.info(f"Processing {len(uploaded_files)} PDF file(s)...")  # General start message

        processed_files_data = []
        total_files = len(uploaded_files)
        files_successfully_processed_count = 0

        # Show progress bar instance
        progress_bar = progress_bar_placeholder.progress(0, text="Starting processing...")

        for i, uploaded_file in enumerate(uploaded_files):
            original_filename = uploaded_file.name
            current_file_status = f"'{original_filename}' ({i + 1}/{total_files})"
            progress_text = f"Processing {current_file_status}..."
            progress_bar.progress(i / total_files, text=progress_text)  # Update progress before starting file
            status_text_placeholder.info(f"🔄 Starting {current_file_status}")
            # logger.info(f"Processing file: {original_filename}")

            # --- START: Original Filename Logic (Renaming Removed) ---
            file_name_base = os.path.splitext(original_filename)[0]
            docx_filename = f"{file_name_base}.docx"
            # logger.info(f"Target docx filename will be: '{docx_filename}'")
            # --- END: Original Filename Logic ---

            with results_container:
                st.markdown(f"--- \n**Processing: {original_filename}**")  # Separator and header

            # 1. Extract Text using Temporary File Path
            status_text_placeholder.info(f"📄 Extracting text from {current_file_status}...")
            raw_text = None # Initialize raw_text
            temp_file_path = None # Initialize path variable
            try:
                # Create a temporary file to get a path
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                    temp_file.write(uploaded_file.getvalue()) # Use getvalue() for BytesIO-like object
                    temp_file_path = temp_file.name
                # logger.info(f"Created temporary file: {temp_file_path}")

                # Pass the file path to the backend function
                raw_text = backend.extract_text_from_pdf(temp_file_path)

            except Exception as extract_exc:
                 with results_container:
                    st.error(f"❌ Unexpected error during text extraction setup or call for '{original_filename}': {extract_exc}")
                 # logger.error(f"Extraction setup/call error for {original_filename}: {extract_exc}")
                 progress_bar.progress((i + 1) / total_files, text=progress_text + " Error.")
                 # Skip to next file if extraction setup failed
                 continue
            finally:
                # Clean up the temporary file if it was created
                if temp_file_path and os.path.exists(temp_file_path):
                    try:
                        os.remove(temp_file_path)
                        # logger.info(f"Removed temporary file: {temp_file_path}")
                    except Exception as remove_exc:
                        # logger.error(f"Error removing temporary file {temp_file_path}: {remove_exc}")
                        st.warning(f"Could not remove temporary file: {temp_file_path}") # Non-critical, inform user

            # --- Check extraction result ---
            if raw_text is None:
                # This means backend.extract_text_from_pdf returned None (logged error there)
                with results_container:
                    st.error(f"❌ Failed to extract text from '{original_filename}'. Check logs for details. Skipping.")
                progress_bar.progress((i + 1) / total_files, text=progress_text + " Error.")
                continue  # Skip to next file

            processed_text = ""
            gemini_error_occurred = False

            if not raw_text.strip():
                # This means extraction (incl. OCR) resulted in empty text
                with results_container:
                    st.warning(f"⚠️ No text could be extracted from '{original_filename}' (possibly image-only or empty). Creating empty Word file '{docx_filename}'.")
                # Proceed to create an empty Word file
                processed_text = "" # Ensure it's an empty string for doc creation
            else:
                # 2. Process with Gemini (only if text was extracted)
                status_text_placeholder.info(
                    f"🤖 Sending text from {current_file_status} to Gemini (gemini-2.0-flash)...")
                try:
                    processed_text_result = backend.process_text_with_gemini(api_key, raw_text, rules_prompt)

                    if processed_text_result is None or (
                            isinstance(processed_text_result, str) and processed_text_result.startswith("Error:")):
                        with results_container:
                            st.error(f"❌ Gemini error for '{original_filename}': {processed_text_result or 'Unknown API error'}")
                        gemini_error_occurred = True
                    else:
                        processed_text = processed_text_result
                        # logger.info(f"Gemini processing successful for {original_filename}.")

                except Exception as gemini_exc:
                     with results_container:
                         st.error(f"❌ Unexpected error during Gemini processing for '{original_filename}': {gemini_exc}")
                     # logger.error(f"Gemini call unexpected error for {original_filename}: {gemini_exc}")
                     gemini_error_occurred = True


            # 3. Create Word Document (if no Gemini error OR if text was empty)
            if not gemini_error_occurred:
                status_text_placeholder.info(f"📝 Creating Word document '{docx_filename}'...")
                try:
                    word_doc_stream = backend.create_word_document(processed_text) # Pass potentially empty text
                    if word_doc_stream:
                        processed_files_data.append((docx_filename, word_doc_stream))
                        files_successfully_processed_count += 1
                        with results_container:
                            st.success(f"✅ Created '{docx_filename}'")
                        # logger.info(f"Successfully created and stored '{docx_filename}'.")
                    else:
                        # This means backend.create_word_document returned None
                        with results_container:
                            st.error(f"❌ Failed to create Word stream for '{docx_filename}' (backend function failed).")
                        # logger.error(f"backend.create_word_document returned None for {original_filename}")

                except Exception as doc_exc:
                     with results_container:
                         st.error(f"❌ Error during Word document creation for '{original_filename}': {doc_exc}")
                     # logger.error(f"Exception during Word creation for {original_filename}: {doc_exc}")

            # Update progress bar after file completion or error
            progress_bar.progress((i + 1) / total_files, text=f"Processed {current_file_status}")


        # --- End of file loop ---
        # logger.info("Processing loop finished.")

        # Clear progress bar and transient status text
        progress_bar_placeholder.empty()
        status_text_placeholder.empty()

        # 4. Zip Files and Update State
        final_status_message = ""
        rerun_needed = False
        if processed_files_data:
            # logger.info(f"Zipping {files_successfully_processed_count} documents.")
            results_container.info(f"💾 Zipping {files_successfully_processed_count} document(s)...")
            try:
                zip_buffer = backend.create_zip_archive(processed_files_data)
                if zip_buffer:
                    st.session_state.zip_buffer = zip_buffer
                    st.session_state.files_processed_count = files_successfully_processed_count
                    final_status_message = f"✅ Processing complete! {files_successfully_processed_count} file(s) ready. Click 'Download All' above."
                    results_container.success(final_status_message)
                    # logger.info("Zip created successfully, state updated.")
                    rerun_needed = True  # Set flag to rerun
                else:
                    final_status_message = "❌ Failed to create zip archive (backend function failed)."
                    results_container.error(final_status_message)
                    # logger.error("backend.create_zip_archive returned None")

            except Exception as zip_exc:
                 final_status_message = f"❌ Error during zipping: {zip_exc}"
                 results_container.error(final_status_message)
                 # logger.error(f"Error during zipping: {zip_exc}")

        else:  # No files were successfully processed to include in zip
             final_status_message = "⚠️ No files were successfully processed to include in a zip archive."
             if total_files > 0: # Only show warning if files were uploaded but none succeeded
                 results_container.warning(final_status_message)
             # logger.warning(final_status_message)

        # Update final state variables AFTER the loop and zipping attempt
        st.session_state.processing_complete = True
        st.session_state.processing_started = False  # Processing has finished

        # logger.info("Processing marked complete. Rerun needed: %s", rerun_needed)

        # Rerun ONLY if zip was created successfully to update the download button display
        if rerun_needed:
            st.rerun()
        # If no rerun happens, the script finishes here, and the UI reflects the final state

    else:
        # Case where processing didn't start due to initial checks failing
        # Ensure processing_started is False if it wasn't already reset
        st.session_state.processing_started = False


# --- Fallback info message ---
if not uploaded_files and not st.session_state.processing_started and not st.session_state.processing_complete:
    st.info("Upload PDF files, configure settings, and click 'Process PDFs'.")


# --- Footer ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
