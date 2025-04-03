# app.py (with Duplicated Controls and Model Selection)

import streamlit as st
import backend  # Assumes backend.py is in the same directory
import os
from io import BytesIO
import logging
# import pandas as pd # No longer needed for displaying file list

# Configure basic logging if needed
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="ArabicPDF",
    page_icon="📄",
    layout="wide"
)

# --- Initialize Session State ---
default_state = {
    'merged_doc_buffer': None,
    'files_processed_count': 0,
    'processing_complete': False,
    'processing_started': False,
    'ordered_files': [],  # List to hold UploadedFile objects in custom order
}
for key, value in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Helper Functions (Unchanged) ---
def reset_processing_state():
    """Resets state related to processing results and status."""
    st.session_state.merged_doc_buffer = None
    st.session_state.files_processed_count = 0
    st.session_state.processing_complete = False
    st.session_state.processing_started = False

def move_file(index, direction):
    """Moves the file at the given index up (direction=-1) or down (direction=1)."""
    files = st.session_state.ordered_files
    if not (0 <= index < len(files)): return
    new_index = index + direction
    if not (0 <= new_index < len(files)): return
    files[index], files[new_index] = files[new_index], files[index]
    st.session_state.ordered_files = files
    reset_processing_state()

def remove_file(index):
    """Removes the file at the given index."""
    files = st.session_state.ordered_files
    if 0 <= index < len(files):
        removed_file = files.pop(index)
        st.toast(f"Removed '{removed_file.name}'.")
        st.session_state.ordered_files = files
        reset_processing_state()
    else:
        st.warning(f"Could not remove file at index {index} (already removed or invalid?).")

def handle_uploads():
    """Adds newly uploaded files to the ordered list, avoiding duplicates by name."""
    if 'pdf_uploader' in st.session_state and st.session_state.pdf_uploader:
        current_filenames = {f.name for f in st.session_state.ordered_files}
        new_files_added_count = 0
        for uploaded_file in st.session_state.pdf_uploader:
            if uploaded_file.name not in current_filenames:
                st.session_state.ordered_files.append(uploaded_file)
                current_filenames.add(uploaded_file.name)
                new_files_added_count += 1

        if new_files_added_count > 0:
            st.toast(f"Added {new_files_added_count} new file(s) to the end of the list.")
            reset_processing_state()
            # Clear the uploader widget state after processing its contents
            # st.session_state.pdf_uploader = [] # Optional: Uncomment if you want uploader to clear visually

def clear_all_files_callback():
    """Clears the ordered file list and resets processing state."""
    st.session_state.ordered_files = []
    if 'pdf_uploader' in st.session_state:
        st.session_state.pdf_uploader = []
    reset_processing_state()
    st.toast("Removed all files from the list.")


# --- Page Title ---
st.title("📄 ArabicPDF - PDF to Word Extractor")
st.markdown("Upload Arabic PDF files, arrange their processing order, then merge and download.")

# --- Sidebar ---
st.sidebar.header("⚙️ Configuration")

# API Key Input
api_key_from_secrets = st.secrets.get("GEMINI_API_KEY", "")
api_key = st.sidebar.text_input(
    "Enter your Google Gemini API Key", type="password",
    help="Required. Get your key from Google AI Studio.", value=api_key_from_secrets or ""
)
# API Key Status Messages
if api_key_from_secrets and api_key == api_key_from_secrets: st.sidebar.success("API Key loaded from Secrets.", icon="✅")
elif not api_key_from_secrets and not api_key: st.sidebar.warning("API Key not found or entered.", icon="🔑")
elif api_key and not api_key_from_secrets: st.sidebar.info("Using manually entered API Key.", icon="⌨️")
elif api_key and api_key_from_secrets and api_key != api_key_from_secrets: st.sidebar.info("Using manually entered API Key (overrides secret).", icon="⌨️")

# --- NEW: Model Selection ---
st.sidebar.markdown("---") # Separator
st.sidebar.header("🧠 AI Model")
# Map user-friendly names to model IDs
model_options = {
    "Gemini 1.5 Flash (Fastest, Cost-Effective)": "gemini-1.5-flash-latest",
    "Gemini 1.5 Pro (Advanced, Slower, Higher Cost)": "gemini-1.5-pro-latest",
}
selected_model_display_name = st.sidebar.selectbox(
    "Choose the Gemini model for processing:",
    options=list(model_options.keys()), # Use display names as options
    index=0, # Default to Flash
    key="gemini_model_select",
    help="Select the AI model. Pro is more capable but slower and costs more."
)
# Get the actual model ID based on the user's selection
selected_model_id = model_options[selected_model_display_name]
st.sidebar.caption(f"Selected model ID: `{selected_model_id}`")

# Extraction Rules (Unchanged)
st.sidebar.markdown("---") # Separator
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


# --- Main Area ---

st.header("📁 Manage Files for Processing")

# File Uploader (Unchanged)
uploaded_files_widget = st.file_uploader(
    "Choose PDF files to add to the list below:", type="pdf", accept_multiple_files=True,
    key="pdf_uploader",
    on_change=handle_uploads,
    label_visibility="visible"
)

st.markdown("---")

# --- TOP: Buttons Area & Progress Indicators ---
st.subheader("🚀 Actions & Progress (Top)")
col_b1_top, col_b2_top = st.columns([3, 2])

with col_b1_top:
    process_button_top_clicked = st.button(
        "✨ Process Files & Merge (Top)",
        key="process_button_top", # Unique key
        use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files
    )

with col_b2_top:
    # Show download button if buffer exists and not processing
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
        st.download_button(
            label=f"📥 Download Merged ({st.session_state.files_processed_count}) Files (.docx)",
            data=st.session_state.merged_doc_buffer,
            file_name="merged_arabic_documents.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button_top", # Unique key
            use_container_width=True
        )
    elif st.session_state.processing_started:
         st.info("Processing in progress...", icon="⏳")
    else:
        # Placeholder or message when download isn't ready
        st.markdown("*(Download button appears here after processing)*")


# Placeholders for top progress indicators
progress_bar_placeholder_top = st.empty()
status_text_placeholder_top = st.empty()

st.markdown("---") # Separator before file list

# --- Interactive File List (Unchanged) ---
st.subheader(f"Files in Processing Order ({len(st.session_state.ordered_files)}):")

if not st.session_state.ordered_files:
    st.info("Use the uploader above to add files. They will appear here for ordering.")
else:
    # Header row
    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([0.5, 5, 1, 1, 1])
    with col_h1: st.markdown("**#**")
    with col_h2: st.markdown("**Filename**")
    with col_h3: st.markdown("**Up**")
    with col_h4: st.markdown("**Down**")
    with col_h5: st.markdown("**Remove**")

    # File rows
    for i, file in enumerate(st.session_state.ordered_files):
        col1, col2, col3, col4, col5 = st.columns([0.5, 5, 1, 1, 1])
        with col1: st.write(f"{i+1}")
        with col2: st.write(file.name)
        with col3: st.button("⬆️", key=f"up_{i}", on_click=move_file, args=(i, -1), disabled=(i == 0), help="Move Up")
        with col4: st.button("⬇️", key=f"down_{i}", on_click=move_file, args=(i, 1), disabled=(i == len(st.session_state.ordered_files) - 1), help="Move Down")
        with col5: st.button("❌", key=f"del_{i}", on_click=remove_file, args=(i,), help="Remove")

    # Clear all button
    st.button("🗑️ Remove All Files",
              key="remove_all_button",
              on_click=clear_all_files_callback,
              help="Click to remove all files from the list.",
              type="secondary")


st.markdown("---") # Separator after file list

# --- BOTTOM: Buttons Area & Progress Indicators ---
st.subheader("🚀 Actions & Progress (Bottom)")
col_b1_bottom, col_b2_bottom = st.columns([3, 2])

with col_b1_bottom:
    process_button_bottom_clicked = st.button(
        "✨ Process Files & Merge (Bottom)",
        key="process_button_bottom", # Unique key
        use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files
    )

with col_b2_bottom:
    # Show download button if buffer exists and not processing
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
        st.download_button(
            label=f"📥 Download Merged ({st.session_state.files_processed_count}) Files (.docx)",
            data=st.session_state.merged_doc_buffer,
            file_name="merged_arabic_documents.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button_bottom", # Unique key
            use_container_width=True
        )
    elif st.session_state.processing_started:
        st.info("Processing in progress...", icon="⏳")
    else:
        # Placeholder or message when download isn't ready
        st.markdown("*(Download button appears here after processing)*")

# Placeholders for bottom progress indicators
progress_bar_placeholder_bottom = st.empty()
status_text_placeholder_bottom = st.empty()

# --- Container for Individual File Results (Displayed below bottom progress) ---
results_container = st.container()


# --- Processing Logic ---
# Check if EITHER process button was clicked
if process_button_top_clicked or process_button_bottom_clicked:
    reset_processing_state()
    st.session_state.processing_started = True

    # Re-check conditions
    if not st.session_state.ordered_files:
        st.warning("⚠️ No files in the list to process.")
        st.session_state.processing_started = False
    elif not api_key:
        st.error("❌ Please enter or configure your Gemini API Key in the sidebar.")
        st.session_state.processing_started = False
    elif not rules_prompt:
        st.warning("⚠️ The 'Extraction Rules' field is empty. Processing without specific instructions.")
    # --- NEW: Check selected model ---
    elif not selected_model_id:
         st.error("❌ No Gemini model selected in the sidebar.") # Should not happen with default
         st.session_state.processing_started = False

    # Proceed only if checks passed
    if st.session_state.ordered_files and api_key and st.session_state.processing_started and selected_model_id:

        processed_doc_streams = []
        total_files = len(st.session_state.ordered_files)

        # Initialize BOTH progress bars
        progress_bar_top = progress_bar_placeholder_top.progress(0, text="Starting processing...")
        progress_bar_bottom = progress_bar_placeholder_bottom.progress(0, text="Starting processing...")

        for i, file_to_process in enumerate(st.session_state.ordered_files):
            original_filename = file_to_process.name
            current_file_status = f"'{original_filename}' ({i + 1}/{total_files})"
            progress_text = f"Processing {current_file_status}..."

            # Update BOTH progress bars and status texts
            progress_value = i / total_files
            progress_bar_top.progress(progress_value, text=progress_text)
            progress_bar_bottom.progress(progress_value, text=progress_text)
            status_text_placeholder_top.info(f"🔄 Starting {current_file_status}")
            status_text_placeholder_bottom.info(f"🔄 Starting {current_file_status}")

            with results_container:
                st.markdown(f"--- \n**Processing: {original_filename}**")

            raw_text = None
            processed_text = ""
            extraction_error = False
            gemini_error_occurred = False
            word_creation_error_occurred = False

            # 1. Extract Text
            # Update BOTH status texts
            status_text_placeholder_top.info(f"📄 Extracting text from {current_file_status}...")
            status_text_placeholder_bottom.info(f"📄 Extracting text from {current_file_status}...")
            try:
                 file_to_process.seek(0)
                 raw_text = backend.extract_text_from_pdf(file_to_process)
                 if raw_text is None:
                     with results_container: st.error(f"❌ Critical error during text extraction. Skipping '{original_filename}'.")
                     extraction_error = True
                 elif isinstance(raw_text, str) and raw_text.startswith("Error:"):
                     with results_container: st.error(f"❌ Error extracting text from '{original_filename}': {raw_text}")
                     extraction_error = True
                 elif not raw_text or not raw_text.strip():
                     with results_container: st.warning(f"⚠️ No text extracted from '{original_filename}'. An empty section will be added.")
                     processed_text = ""
            except Exception as ext_exc:
                 with results_container: st.error(f"❌ Unexpected error during text extraction for '{original_filename}': {ext_exc}")
                 extraction_error = True

            # 2. Process with Gemini
            if not extraction_error and raw_text and raw_text.strip():
                 # Update BOTH status texts
                 status_text_placeholder_top.info(f"🤖 Sending text from {current_file_status} to Gemini ({selected_model_display_name})...")
                 status_text_placeholder_bottom.info(f"🤖 Sending text from {current_file_status} to Gemini ({selected_model_display_name})...")
                 try:
                     # --- Pass selected_model_id to backend ---
                     processed_text_result = backend.process_text_with_gemini(
                         api_key, raw_text, rules_prompt, selected_model_id
                     )
                     # ---                                      ---
                     if processed_text_result is None or (isinstance(processed_text_result, str) and processed_text_result.startswith("Error:")):
                         with results_container: st.error(f"❌ Gemini error for '{original_filename}': {processed_text_result or 'Unknown API error'}")
                         gemini_error_occurred = True
                         processed_text = ""
                     else:
                         processed_text = processed_text_result
                 except Exception as gem_exc:
                      with results_container: st.error(f"❌ Unexpected error during Gemini processing for '{original_filename}': {gem_exc}")
                      gemini_error_occurred = True
                      processed_text = ""

            # 3. Create Individual Word Document
            word_doc_stream = None
            if not extraction_error:
                 # Update BOTH status texts
                 status_text_placeholder_top.info(f"📝 Creating intermediate Word document for {current_file_status}...")
                 status_text_placeholder_bottom.info(f"📝 Creating intermediate Word document for {current_file_status}...")
                 try:
                     word_doc_stream = backend.create_word_document(processed_text)
                     if word_doc_stream:
                          processed_doc_streams.append((original_filename, word_doc_stream))
                          with results_container:
                               success_msg = f"✅ Created intermediate Word file for '{original_filename}'."
                               if not processed_text or not processed_text.strip():
                                   if gemini_error_occurred: success_msg += " (Note: placeholder text used due to Gemini error)"
                                   elif raw_text is None or not raw_text.strip(): success_msg += " (Note: placeholder text used as no text was extracted)"
                                   else: success_msg += " (Note: content appears empty)"
                               st.success(success_msg)
                     else:
                          word_creation_error_occurred = True
                          with results_container: st.error(f"❌ Failed to create intermediate Word file for '{original_filename}' (backend returned None).")
                 except Exception as doc_exc:
                      word_creation_error_occurred = True
                      with results_container: st.error(f"❌ Error during intermediate Word file creation for '{original_filename}': {doc_exc}")

            # Update overall progress on BOTH bars
            status_msg_suffix = ""
            if extraction_error or word_creation_error_occurred or gemini_error_occurred: status_msg_suffix = " with issues."
            final_progress_value = (i + 1) / total_files
            final_progress_text = f"Processed {current_file_status}{status_msg_suffix}"
            progress_bar_top.progress(final_progress_value, text=final_progress_text)
            progress_bar_bottom.progress(final_progress_value, text=final_progress_text)

        # --- End of file loop ---

        # Clear BOTH progress bars and status texts
        progress_bar_placeholder_top.empty()
        status_text_placeholder_top.empty()
        progress_bar_placeholder_bottom.empty()
        status_text_placeholder_bottom.empty()

        # 4. Merge Documents and Update State
        final_status_message = ""
        rerun_needed = False
        successfully_created_doc_count = len(processed_doc_streams)

        with results_container:
            st.markdown("---") # Separator before final status
            if successfully_created_doc_count > 0:
                st.info(f"💾 Merging {successfully_created_doc_count} intermediate Word document(s)... Please wait.")
                try:
                    merged_doc_buffer = backend.merge_word_documents(processed_doc_streams)

                    if merged_doc_buffer:
                        st.session_state.merged_doc_buffer = merged_doc_buffer
                        st.session_state.files_processed_count = successfully_created_doc_count
                        final_status_message = f"✅ Processing complete! Merged document created from {successfully_created_doc_count} source file(s). Click 'Download Merged' above or below."
                        st.success(final_status_message)
                        rerun_needed = True # Rerun to show download buttons
                    else:
                        final_status_message = "❌ Failed to merge Word documents (backend returned None)."
                        st.error(final_status_message)
                except Exception as merge_exc:
                    final_status_message = f"❌ Error during document merging: {merge_exc}"
                    logging.error(f"Error during merge_word_documents call: {merge_exc}", exc_info=True)
                    st.error(final_status_message)
            else:
                 final_status_message = "⚠️ No intermediate Word documents were successfully created to merge."
                 st.warning(final_status_message)
                 if st.session_state.ordered_files: st.info("Please check the individual file statuses above for errors.")

        st.session_state.processing_complete = True
        st.session_state.processing_started = False

        if rerun_needed:
            st.rerun() # Rerun to make download buttons visible / update UI state

    else:
        # Processing didn't start due to initial checks failing
        if not st.session_state.ordered_files or not api_key or not selected_model_id:
             st.session_state.processing_started = False # Ensure it's reset


# --- Fallback info message (Unchanged) ---
if not st.session_state.ordered_files and not st.session_state.processing_started and not st.session_state.processing_complete:
    st.info("Upload PDF files using the 'Choose PDF files' button above.")

# --- Footer (Unchanged) ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
