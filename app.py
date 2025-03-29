# app.py

import streamlit as st
import backend  # Assumes backend.py is in the same directory
import os
from io import BytesIO
import logging
import pandas as pd

# Configure basic logging if needed
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="ArabicPDF",
    page_icon="📄",
    layout="wide"
)

# --- Initialize Session State ---
# Uses merged_doc_buffer, same key as before, but the content generation is different
default_state = {
    'merged_doc_buffer': None,
    'files_processed_count': 0, # Represents source files successfully creating individual docs
    'processing_complete': False,
    'processing_started': False,
    'last_uploaded_files_count': 0
}
for key, value in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

def reset_processing_state():
    """Resets state related to processing results and status."""
    st.session_state.merged_doc_buffer = None
    st.session_state.files_processed_count = 0
    st.session_state.processing_complete = False
    st.session_state.processing_started = False
    # logger.info("Processing state reset.")


# --- Page Title ---
st.title("📄 ArabicPDF - PDF to Word Extractor")
st.markdown("Upload Arabic PDF files, process each, then merge and download the result as a single Word document.") # Updated description

# --- Sidebar for Configuration ---
st.sidebar.header("⚙️ Configuration")
api_key_from_secrets = st.secrets.get("GEMINI_API_KEY", "")
api_key = st.sidebar.text_input(
    "Enter your Google Gemini API Key", type="password",
    help="Required. Get your key from Google AI Studio.", value=api_key_from_secrets or ""
)
if api_key_from_secrets and api_key == api_key_from_secrets: st.sidebar.success("API Key loaded from Secrets.", icon="✅")
elif not api_key_from_secrets and not api_key: st.sidebar.warning("API Key not found or entered.", icon="🔑")
elif api_key and not api_key_from_secrets: st.sidebar.info("Using manually entered API Key.", icon="⌨️")
elif api_key and api_key_from_secrets and api_key != api_key_from_secrets: st.sidebar.info("Using manually entered API Key (overrides secret).", icon="⌨️")

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
    "Choose PDF files", type="pdf", accept_multiple_files=True,
    label_visibility="collapsed", key="pdf_uploader"
)

# Detect if files have changed
current_file_count = len(uploaded_files) if uploaded_files else 0
if current_file_count != st.session_state.last_uploaded_files_count:
    reset_processing_state()
    st.session_state.last_uploaded_files_count = current_file_count
    st.rerun()

# --- Buttons Area ---
col1, col2 = st.columns([3, 2])

with col1:
    process_button_clicked = st.button(
        "✨ Process PDFs, Create Word Files, then Merge", # Updated Label
        key="process_button", use_container_width=True,
        disabled=st.session_state.processing_started
    )

with col2:
    # Download button visibility depends on merged_doc_buffer existence AND processing not running
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
        st.download_button(
            label=f"📥 Download Merged ({st.session_state.files_processed_count}) Files (.docx)",
            data=st.session_state.merged_doc_buffer,
            file_name="merged_arabic_documents.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button",
            use_container_width=True
        )
        # logger.info("Download button rendered for merged document.")


# --- Display Uploaded Files List ---
if uploaded_files:
    st.markdown("---")
    st.subheader(f"Uploaded Files ({len(uploaded_files)}):")
    filenames = [file.name for file in uploaded_files]
    df_files = pd.DataFrame({'Filename': filenames})
    st.dataframe(df_files, use_container_width=True, height=300) # Adjust height if needed


# --- UI Elements for Progress ---
progress_bar_placeholder = st.empty()
status_text_placeholder = st.empty()
results_container = st.container() # Container to show individual file results during processing

# --- Processing Logic ---
if process_button_clicked:
    # logger.info("Process button clicked.")
    reset_processing_state()
    st.session_state.processing_started = True

    # Checks before starting loop
    if not uploaded_files:
        st.warning("⚠️ Please upload PDF files first.")
        st.session_state.processing_started = False
    elif not api_key:
        st.error("❌ Please enter or configure your Gemini API Key in the sidebar.")
        st.session_state.processing_started = False
    elif not rules_prompt:
        st.warning("⚠️ The 'Extraction Rules' field is empty. Processing without specific instructions.")

    # Proceed only if checks passed and processing started
    if uploaded_files and api_key and st.session_state.processing_started:
        st.info(f"Processing {len(uploaded_files)} PDF file(s)...")

        # List to collect individual Word doc streams for merging
        processed_doc_streams = [] # Stores tuples of (filename, stream)

        total_files = len(uploaded_files)
        progress_bar = progress_bar_placeholder.progress(0, text="Starting processing...")

        for i, uploaded_file in enumerate(uploaded_files):
            original_filename = uploaded_file.name
            current_file_status = f"'{original_filename}' ({i + 1}/{total_files})"
            progress_text = f"Processing {current_file_status}..."
            progress_bar.progress(i / total_files, text=progress_text)
            status_text_placeholder.info(f"🔄 Starting {current_file_status}")

            # Derive docx filename base (might be useful for reporting)
            file_name_base = os.path.splitext(original_filename)[0]
            # docx_filename = f"{file_name_base}.docx" # Filename for potential individual doc (not strictly needed now)

            with results_container:
                st.markdown(f"--- \n**Processing: {original_filename}**")

            # --- Pipeline for each file ---
            raw_text = None
            processed_text = ""
            extraction_error = False
            gemini_error_occurred = False
            word_creation_error_occurred = False

            # 1. Extract Text
            status_text_placeholder.info(f"📄 Extracting text from {current_file_status}...")
            try:
                 file_clone_for_extraction = BytesIO(uploaded_file.getvalue())
                 raw_text = backend.extract_text_from_pdf(file_clone_for_extraction)
                 if raw_text is None: # Backend indicated critical extraction error
                     with results_container: st.error(f"❌ Critical error during text extraction. Skipping '{original_filename}'.")
                     extraction_error = True
                 elif isinstance(raw_text, str) and raw_text.startswith("Error:"): # Backend returned specific error string
                     with results_container: st.error(f"❌ Error extracting text from '{original_filename}': {raw_text}")
                     extraction_error = True
                 elif not raw_text or not raw_text.strip():
                     with results_container: st.warning(f"⚠️ No text extracted from '{original_filename}'. An empty section will be added to the merged document.")
                     processed_text = "" # Ensure processed_text is empty for create_word_document
            except Exception as ext_exc:
                 with results_container: st.error(f"❌ Unexpected error during text extraction for '{original_filename}': {ext_exc}")
                 extraction_error = True

            # 2. Process with Gemini (only if text extracted successfully)
            if not extraction_error and raw_text and raw_text.strip():
                 status_text_placeholder.info(f"🤖 Sending text from {current_file_status} to Gemini...")
                 try:
                     processed_text_result = backend.process_text_with_gemini(api_key, raw_text, rules_prompt)
                     if processed_text_result is None or (isinstance(processed_text_result, str) and processed_text_result.startswith("Error:")):
                         with results_container: st.error(f"❌ Gemini error for '{original_filename}': {processed_text_result or 'Unknown API error'}")
                         gemini_error_occurred = True
                         processed_text = "" # Use empty text if Gemini fails, will generate placeholder doc
                     else:
                         processed_text = processed_text_result # Store successful result
                 except Exception as gem_exc:
                      with results_container: st.error(f"❌ Unexpected error during Gemini processing for '{original_filename}': {gem_exc}")
                      gemini_error_occurred = True
                      processed_text = "" # Use empty text on unexpected error, will generate placeholder doc

            # 3. Create Individual Word Document (if extraction didn't critically fail)
            word_doc_stream = None
            if not extraction_error:
                 status_text_placeholder.info(f"📝 Creating intermediate Word document for {current_file_status}...")
                 try:
                     # Call the backend function that creates a SINGLE doc stream
                     # Pass potentially empty processed_text (backend handles this)
                     word_doc_stream = backend.create_word_document(processed_text)
                     if word_doc_stream:
                          # Add the successful stream and filename to the list for merging
                          processed_doc_streams.append((original_filename, word_doc_stream))
                          with results_container:
                               # Display success even if the content was empty (placeholder was created)
                               success_msg = f"✅ Created intermediate Word file for '{original_filename}'."
                               if not processed_text and not gemini_error_occurred:
                                   success_msg += " (Note: source text was empty/Gemini failed)"
                               st.success(success_msg)
                          # logger.info(f"Successfully created intermediate doc stream for {original_filename}")
                     else: # backend.create_word_document returned None
                          word_creation_error_occurred = True
                          with results_container:
                               st.error(f"❌ Failed to create intermediate Word file for '{original_filename}' (backend returned None).")
                          # logger.error(f"backend.create_word_document returned None for {original_filename}")
                 except Exception as doc_exc:
                      word_creation_error_occurred = True
                      with results_container:
                          st.error(f"❌ Error during intermediate Word file creation for '{original_filename}': {doc_exc}")
                      # logger.error(f"Exception during Word creation for {original_filename}: {doc_exc}")

            # Update progress bar
            status_msg_suffix = ""
            # Mark error if any *critical* step failed (extraction error OR word creation error)
            if extraction_error or word_creation_error_occurred:
                 status_msg_suffix = " Error."
            # Gemini error is logged but doesn't prevent merge attempt with placeholder content
            progress_bar.progress((i + 1) / total_files, text=f"Processed {current_file_status}{status_msg_suffix}")

        # --- End of file loop ---
        progress_bar_placeholder.empty()
        status_text_placeholder.empty()

        # 4. Merge Documents and Update State (if any individual docs were created)
        final_status_message = ""
        rerun_needed = False
        successfully_created_doc_count = len(processed_doc_streams) # Count based on streams collected

        if successfully_created_doc_count > 0:
            # logger.info(f"Merging {successfully_created_doc_count} individual Word documents.")
            results_container.info(f"💾 Merging {successfully_created_doc_count} intermediate Word document(s)... Please wait.")
            try:
                # Call the NEW backend merge function
                merged_doc_buffer = backend.merge_word_documents(processed_doc_streams)

                if merged_doc_buffer:
                    st.session_state.merged_doc_buffer = merged_doc_buffer
                    st.session_state.files_processed_count = successfully_created_doc_count # Store count of merged docs
                    final_status_message = f"✅ Processing complete! Merged document created from {successfully_created_doc_count} source file(s). Click 'Download Merged' above."
                    results_container.success(final_status_message)
                    # logger.info("Merged doc created successfully, state updated.")
                    rerun_needed = True
                else:
                    final_status_message = "❌ Failed to merge Word documents (backend returned None)."
                    results_container.error(final_status_message)
                    # logger.error(final_status_message)

            except Exception as merge_exc:
                final_status_message = f"❌ Error during document merging: {merge_exc}"
                # Log the error for debugging merge issues
                logging.error(f"Error during merge_word_documents call: {merge_exc}", exc_info=True)
                results_container.error(final_status_message)
                # logger.error(final_status_message)

        else: # No individual documents were successfully created to merge
             final_status_message = "⚠️ No intermediate Word documents were successfully created to merge."
             results_container.warning(final_status_message)
             if uploaded_files: # Only add this if files were actually uploaded initially
                  results_container.info("Please check the individual file statuses above for errors.")
             # logger.warning(final_status_message)


        # Update final state variables
        st.session_state.processing_complete = True
        st.session_state.processing_started = False

        # logger.info("Processing marked complete. Rerun needed: %s", rerun_needed)
        if rerun_needed:
            st.rerun()

    else:
        # Case where processing didn't start due to initial checks failing
        if not uploaded_files or not api_key:
             st.session_state.processing_started = False


# --- Fallback info message ---
if not uploaded_files and not st.session_state.processing_started and not st.session_state.processing_complete:
    st.info("Upload PDF files, configure settings, and click 'Process PDFs'.")

# --- Footer ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
