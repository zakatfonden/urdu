import streamlit as st
import backend  # Assumes backend.py is in the same directory
import os
from io import BytesIO
import logging  # Optional: if you want frontend logging too
import pandas as pd # <-- ADDED IMPORT

# Configure basic logging if needed for debugging in terminal
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message.

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="ArabicPDF",
    page_icon="📄",
    layout="wide"
)

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

# --- Model Selection Update ---
# REMOVE MODEL SELECTOR
# st.sidebar.header("🤖 Gemini Model")
# available_models = ["gemini-1.5-flash-latest", "gemini-1.5-pro-latest", "gemini-pro"]
# model_name = st.sidebar.selectbox(
#     "Select Gemini Model:", options=available_models, index=0,
#     help="`gemini-1.5-flash-latest` is recommended."
# )
# st.sidebar.caption(f"Using: `{model_name}`")

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

# --- NEW: Display Uploaded Files List ---
if uploaded_files:
    st.markdown("---") # Optional separator
    st.subheader(f"Uploaded Files ({len(uploaded_files)}):")
    # Create a list of filenames
    filenames = [file.name for file in uploaded_files]
    # Create a Pandas DataFrame
    df_files = pd.DataFrame({'Filename': filenames})
    # Display the DataFrame as a table. Set a height to make it scrollable.
    # Adjust the height pixels as needed.
    st.dataframe(df_files, use_container_width=True, height=300) # Adjust height=XXX if needed
# --- END NEW SECTION ---


# --- UI Elements for Progress ---
# Placeholders need to be defined *before* the processing logic that might update them
progress_bar_placeholder = st.empty()
status_text_placeholder = st.empty()
results_container = st.container() # Container to show individual file results

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

    # Only proceed if files are uploaded AND API key is present AND processing started flag is set
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

            # Use the original PDF filename (without extension) as the base for the Word file
            file_name_base = os.path.splitext(original_filename)[0]
            docx_filename = f"{file_name_base}.docx"
            # logger.info(f"Target docx filename will be: '{docx_filename}'")

            with results_container:
                st.markdown(f"--- \n**Processing: {original_filename}**") # Separator and header

            # 1. Extract Text
            status_text_placeholder.info(f"📄 Extracting text from {current_file_status}...")
            file_clone_for_extraction = BytesIO(uploaded_file.getvalue())
            raw_text = backend.extract_text_from_pdf(file_clone_for_extraction) # Use the clone

            if raw_text is None: # Treat None as critical error from backend
                with results_container:
                    st.error(f"❌ Critical error during text extraction. Skipping '{original_filename}'.")
                progress_bar.progress((i + 1) / total_files, text=progress_text + " Error.")
                continue  # Skip to next file
            elif isinstance(raw_text, str) and raw_text.startswith("Error:"): # Backend signals specific error
                with results_container:
                    st.error(f"❌ Error extracting text from '{original_filename}': {raw_text}")
                progress_bar.progress((i + 1) / total_files, text=progress_text + " Error.")
                continue # Skip to next file

            # Initialize variables for this file iteration
            processed_text = ""
            gemini_error_occurred = False
            word_creation_error_occurred = False

            if not raw_text.strip():
                with results_container:
                    st.warning(f"⚠️ No text extracted (PDF might be image-only or extraction failed silently). Creating empty Word file '{docx_filename}'.")
                processed_text = "" # Ensure processed_text is empty string for empty doc creation
            else:
                # 2. Process with Gemini
                status_text_placeholder.info(f"🤖 Sending text from {current_file_status} to Gemini (gemini-1.5-flash)...")
                processed_text_result = backend.process_text_with_gemini(api_key, raw_text, rules_prompt)

                # Check if the result indicates an error (backend returns "Error: ..." strings or None)
                if processed_text_result is None or (isinstance(processed_text_result, str) and processed_text_result.startswith("Error:")):
                    with results_container:
                        st.error(f"❌ Gemini error for '{original_filename}': {processed_text_result or 'Unknown API error'}")
                    gemini_error_occurred = True
                else:
                    processed_text = processed_text_result
                    # logger.info(f"Gemini processing successful for {original_filename}.")

            # 3. Create Word Document (Only if Gemini didn't have a blocking error)
            if not gemini_error_occurred:
                status_text_placeholder.info(f"📝 Creating Word document '{docx_filename}'...")
                try:
                    word_doc_stream = backend.create_word_document(processed_text) # Use potentially empty processed_text
                    if word_doc_stream:
                        # Pass the correct docx_filename to be stored for zipping
                        processed_files_data.append((docx_filename, word_doc_stream))
                        files_successfully_processed_count += 1
                        with results_container:
                             # Add success message even for potentially empty docs if creation succeeded
                            st.success(f"✅ Created '{docx_filename}'" + (" (Note: Source text was empty)" if not raw_text.strip() else ""))
                        # logger.info(f"Successfully created and stored '{docx_filename}'.")
                    else: # backend.create_word_document returned None
                         word_creation_error_occurred = True
                         with results_container:
                            st.error(f"❌ Failed to create Word stream for '{docx_filename}' (backend returned None).")
                         # logger.error(f"backend.create_word_document returned None for {original_filename}")
                except Exception as doc_exc:
                    word_creation_error_occurred = True
                    with results_container:
                        st.error(f"❌ Error during Word document creation for '{original_filename}': {doc_exc}")
                    # logger.error(f"Exception during Word creation for {original_filename}: {doc_exc}")

            # Update progress bar after file completion or error
            status_msg_suffix = ""
            if gemini_error_occurred or word_creation_error_occurred or (isinstance(raw_text, str) and raw_text.startswith("Error:")):
                 status_msg_suffix = " Error."
            progress_bar.progress((i + 1) / total_files, text=f"Processed {current_file_status}{status_msg_suffix}")

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
                    rerun_needed = True  # Set flag to rerun to show download button
                else:
                    final_status_message = "❌ Failed to create zip archive (backend returned None)."
                    results_container.error(final_status_message)
                    # logger.error(final_status_message)

            except Exception as zip_exc:
                final_status_message = f"❌ Error during zipping: {zip_exc}"
                results_container.error(final_status_message)
                # logger.error(final_status_message)

        else:  # No files were successfully processed to zip
            final_status_message = "⚠️ No files were successfully processed to include in a zip archive."
            results_container.warning(final_status_message)
            # logger.warning(final_status_message)
            # Check if there were uploads but no successful processing
            if uploaded_files:
                 results_container.info("Please check the individual file statuses above for errors.")


        # Update final state variables AFTER the loop and zipping attempt
        st.session_state.processing_complete = True
        st.session_state.processing_started = False  # Processing has finished

        # logger.info("Processing marked complete. Rerun needed: %s", rerun_needed)

        # Rerun ONLY if zip was created successfully to update the download button display
        if rerun_needed:
            st.rerun()
        # If no rerun happens, the script finishes here, and the UI reflects the final state

    else:
        # Case where processing didn't start due to initial checks failing (e.g., no API key, no files)
        # Ensure processing_started is False if it wasn't already reset by the checks
        if not uploaded_files or not api_key:
             st.session_state.processing_started = False

# --- Fallback info message ---
# Display only if no files are uploaded AND processing isn't active or just completed
if not uploaded_files and not st.session_state.processing_started and not st.session_state.processing_complete:
    st.info("Upload PDF files, configure settings, and click 'Process PDFs'.")

# --- Footer ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
