# app.py (Modified for DOCX Input, Translation, Merging, and Visual ETA Remaining)

import streamlit as st
import backend  # Assumes backend.py (backend_py_updated_v1) is in the same directory
import os
from io import BytesIO
import logging
import time # Needed for time calculations
import math # Needed for ceiling function

# Configure basic logging if needed
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="UrduDoc Translator",
    page_icon="🔄",
    layout="wide"
)

# --- Constants for Estimation ---
# Adjust these based on observation if needed
# Using previously doubled values
BASE_PROCESSING_TIME_SECONDS = 60  # Base time for setup, merging etc. (30 * 2)
TIME_PER_FILE_FLASH_SECONDS = 60 # Estimated avg time per file for Gemini Flash (30 * 2)
TIME_PER_FILE_PRO_SECONDS = 120  # Estimated avg time per file for Gemini Pro (60 * 2)
# END UPDATED CONSTANTS

# --- Initialize Session State ---
default_state = {
    'merged_doc_buffer': None,
    'files_processed_count': 0, # Counts files successfully processed into intermediate docs
    'processing_complete': False,
    'processing_started': False,
    'ordered_files': [], # List to hold UploadedFile objects for .docx
}
for key, value in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Helper Functions ---
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
    reset_processing_state() # Reset if order changes

def remove_file(index):
    """Removes the file at the given index."""
    files = st.session_state.ordered_files
    if 0 <= index < len(files):
        removed_file = files.pop(index)
        st.toast(f"Removed '{removed_file.name}'.")
        st.session_state.ordered_files = files
        reset_processing_state() # Reset if files change
    else:
        st.warning(f"Could not remove file at index {index} (already removed or invalid?).")

def handle_uploads():
    """Adds newly uploaded files (.docx) to the ordered list."""
    uploader_key = "docx_uploader"
    if uploader_key in st.session_state and st.session_state[uploader_key]:
        current_filenames = {f.name for f in st.session_state.ordered_files}
        new_files_added_count = 0
        for uploaded_file in st.session_state[uploader_key]:
            # Basic check for file extension
            if uploaded_file.name.lower().endswith('.docx'):
                if uploaded_file.name not in current_filenames:
                    st.session_state.ordered_files.append(uploaded_file)
                    current_filenames.add(uploaded_file.name)
                    new_files_added_count += 1
            else:
                 st.warning(f"Skipped '{uploaded_file.name}'. Only .docx files are accepted.", icon="⚠️")

        if new_files_added_count > 0:
            st.toast(f"Added {new_files_added_count} new DOCX file(s) to the list.")
            reset_processing_state()
        # st.session_state[uploader_key] = [] # Optional

def clear_all_files_callback():
    """Clears the ordered file list and resets processing state."""
    st.session_state.ordered_files = []
    uploader_key = "docx_uploader"
    if uploader_key in st.session_state:
        st.session_state[uploader_key] = [] # Clear uploader state as well
    reset_processing_state()
    st.toast("Removed all files from the list.")

def format_time(seconds):
    """Formats seconds into a human-readable string (e.g., X min Y sec)."""
    if seconds < 0: seconds = 0 # Ensure non-negative time
    if seconds < 60:
        # Show seconds precisely when less than a minute
        return f"{math.ceil(seconds)} sec"
    minutes = int(seconds // 60)
    remaining_seconds = math.ceil(seconds % 60)
    if remaining_seconds == 0:
        return f"{minutes} min"
    else:
        # Pad seconds with leading zero
        sec_str = str(remaining_seconds).zfill(2)
        return f"{minutes} min {sec_str} sec"


# --- Page Title ---
st.title("🔄 Urdu/Farsi/English DOCX to Arabic Translator")
st.markdown("Upload Word (`.docx`) files, arrange order, translate content to Arabic, and download the merged result.")

# --- Sidebar ---
st.sidebar.header("⚙️ Configuration")

# API Key Input
api_key_from_secrets = st.secrets.get("GEMINI_API_KEY", "")
api_key = st.sidebar.text_input(
    "Enter your Google Gemini API Key", type="password",
    help="Required for translation. Get your key from Google AI Studio.", value=api_key_from_secrets or ""
)
# API Key Status Messages
if api_key_from_secrets and api_key == api_key_from_secrets: st.sidebar.success("API Key loaded from Secrets.", icon="✅")
elif not api_key_from_secrets and not api_key: st.sidebar.warning("API Key not found or entered.", icon="🔑")
elif api_key and not api_key_from_secrets: st.sidebar.info("Using manually entered API Key.", icon="⌨️")
elif api_key and api_key_from_secrets and api_key != api_key_from_secrets: st.sidebar.info("Using manually entered API Key (overrides secret).", icon="⌨️")

# Model Selection
st.sidebar.markdown("---")
st.sidebar.header("🧠 AI Model for Translation")
model_options = {
    "Gemini 1.5 Flash (Fastest, Cost-Effective)": "gemini-1.5-flash-latest",
    "Gemini 1.5 Pro (Advanced, Slower, Higher Cost)": "gemini-1.5-pro-latest",
}
selected_model_display_name = st.sidebar.selectbox(
    "Choose the Gemini model for translation:",
    options=list(model_options.keys()),
    index=0, # Default to Flash
    key="gemini_model_select",
    help="Select the AI model. Pro is better for nuanced translation but slower."
)
selected_model_id = model_options[selected_model_display_name]
st.sidebar.caption(f"Selected model ID: `{selected_model_id}`")

# Translation Rules
st.sidebar.markdown("---")
st.sidebar.header("📜 Translation Rules")
default_rules = """
Translate the following text accurately into Modern Standard Arabic.
The input text might be in Urdu, Farsi, or English.
Preserve the meaning and intent of the original text.
Format the output as clean Arabic paragraphs suitable for a document.
Return ONLY the Arabic translation, without any introductory phrases, explanations, or markdown formatting.
"""
rules_prompt = st.sidebar.text_area(
    "Enter the translation instructions for Gemini:", value=default_rules, height=200,
    help="Instructions for how Gemini should translate the text extracted from the Word documents."
)

# --- Main Area ---

st.header("📁 Manage DOCX Files for Translation")

# File Uploader for DOCX
uploaded_files_widget = st.file_uploader(
    "Choose Word (.docx) files to translate:",
    type="docx",
    accept_multiple_files=True,
    key="docx_uploader",
    on_change=handle_uploads,
    label_visibility="visible"
)

st.markdown("---")

# --- TOP: Buttons Area & Progress Indicators ---
st.subheader("🚀 Actions & Progress (Top)")
col_b1_top, col_b2_top = st.columns([3, 2])

with col_b1_top:
    process_button_top_clicked = st.button(
        "✨ Translate Files & Merge (Top)",
        key="process_button_top_docx",
        use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files
    )

with col_b2_top:
    # Show download button if buffer exists and not processing
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
        st.download_button(
            label=f"📥 Download Merged ({st.session_state.files_processed_count}) Translations (.docx)",
            data=st.session_state.merged_doc_buffer,
            file_name="merged_arabic_translations.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button_top_docx",
            use_container_width=True
        )
    elif st.session_state.processing_started:
        st.info("Processing in progress...", icon="⏳")
    else:
        st.markdown("*(Download button appears here after processing)*")


# Placeholders for top progress indicators
progress_bar_placeholder_top = st.empty()
status_text_placeholder_top = st.empty()

st.markdown("---") # Separator before file list

# --- Interactive File List ---
st.subheader(f"Files in Processing Order ({len(st.session_state.ordered_files)}):")

if not st.session_state.ordered_files:
    st.info("Use the uploader above to add DOCX files. They will appear here.")
else:
    # Header row
    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([0.5, 5, 1, 1, 1])
    with col_h1: st.markdown("**#**")
    with col_h2: st.markdown("**Filename**")
    with col_h3: st.markdown("**Up**")
    with col_h4: st.markdown("**Down**")
    with col_h5: st.markdown("**Remove**")

    # File rows - use unique keys based on index `i`
    for i, file in enumerate(st.session_state.ordered_files):
        col1, col2, col3, col4, col5 = st.columns([0.5, 5, 1, 1, 1])
        with col1: st.write(f"{i+1}")
        with col2: st.write(file.name)
        # Ensure keys are unique for each file's buttons
        with col3: st.button("⬆️", key=f"up_docx_{i}", on_click=move_file, args=(i, -1), disabled=(i == 0), help="Move Up")
        with col4: st.button("⬇️", key=f"down_docx_{i}", on_click=move_file, args=(i, 1), disabled=(i == len(st.session_state.ordered_files) - 1), help="Move Down")
        with col5: st.button("❌", key=f"del_docx_{i}", on_click=remove_file, args=(i,), help="Remove")

    st.button("🗑️ Remove All Files",
              key="remove_all_button_docx",
              on_click=clear_all_files_callback,
              help="Click to remove all files from the list.",
              type="secondary")


st.markdown("---") # Separator after file list

# --- BOTTOM: Buttons Area & Progress Indicators ---
st.subheader("🚀 Actions & Progress (Bottom)")
col_b1_bottom, col_b2_bottom = st.columns([3, 2])

with col_b1_bottom:
    process_button_bottom_clicked = st.button(
        "✨ Translate Files & Merge (Bottom)",
        key="process_button_bottom_docx",
        use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files
    )

with col_b2_bottom:
    # Show download button if buffer exists and not processing
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
        st.download_button(
            label=f"📥 Download Merged ({st.session_state.files_processed_count}) Translations (.docx)",
            data=st.session_state.merged_doc_buffer,
            file_name="merged_arabic_translations.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button_bottom_docx",
            use_container_width=True
        )
    elif st.session_state.processing_started:
        st.info("Processing in progress...", icon="⏳")
    else:
        st.markdown("*(Download button appears here after processing)*")

# Placeholders for bottom progress indicators
progress_bar_placeholder_bottom = st.empty()
status_text_placeholder_bottom = st.empty()

# --- Container for Individual File Results ---
results_container = st.container()


# --- == Processing Logic (Extract-Translate-Create-Merge) == ---
# Check if EITHER process button was clicked
if process_button_top_clicked or process_button_bottom_clicked:
    # 1. Reset state from previous runs
    reset_processing_state()
    st.session_state.processing_started = True
    rerun_needed = False # Flag to trigger rerun at the end if needed

    # 2. Perform initial checks
    if not st.session_state.ordered_files:
        st.warning("⚠️ No DOCX files in the list to process.")
        st.session_state.processing_started = False
    elif not api_key:
        st.error("❌ Please enter or configure your Gemini API Key in the sidebar.")
        st.session_state.processing_started = False
    elif not rules_prompt.strip():
        st.warning("⚠️ The 'Translation Rules' field is empty. Using default rules.")
        current_rules = default_rules # Use default if empty
    elif not selected_model_id:
        st.error("❌ No Gemini model selected in the sidebar.")
        st.session_state.processing_started = False
    else:
        current_rules = rules_prompt # Use rules from text area

    # 3. Proceed only if checks passed and processing started
    if st.session_state.processing_started:

        processed_doc_streams = [] # List to hold intermediate arabic doc streams
        files_successfully_processed = 0 # Counter for successful intermediate docs
        total_files = len(st.session_state.ordered_files)

        # --- Calculate and Display Initial Estimated Time ---
        time_per_file = TIME_PER_FILE_PRO_SECONDS if "pro" in selected_model_id else TIME_PER_FILE_FLASH_SECONDS
        # This is the total estimated duration for the whole process
        estimated_total_seconds = BASE_PROCESSING_TIME_SECONDS + (total_files * time_per_file)
        estimated_time_str = format_time(estimated_total_seconds)
        initial_status_msg = f"⏳ Starting processing for {total_files} file(s). Initial estimate: ~{estimated_time_str}"
        status_text_placeholder_top.info(initial_status_msg)
        status_text_placeholder_bottom.info(initial_status_msg)
        # --- End Initial Estimation ---

        # Initialize BOTH progress bars
        progress_bar_top = progress_bar_placeholder_top.progress(0, text="Preparing...")
        progress_bar_bottom = progress_bar_placeholder_bottom.progress(0, text="Preparing...")
        time.sleep(1) # Brief pause to allow user to see estimate

        # 4. --- Loop through files ---
        start_time = time.time() # Record start time for actual duration calculation
        for i, file_to_process in enumerate(st.session_state.ordered_files):
            original_filename = file_to_process.name
            current_file_status = f"'{original_filename}' ({i + 1}/{total_files})"

            # --- Calculate Estimated Remaining Time ---
            # Estimate based on how many files are left + remaining base time
            files_remaining = total_files - i
            # Simple estimate: time left is time for remaining files + base time (assuming base time is mostly merge)
            estimated_remaining_seconds = (files_remaining * time_per_file) + BASE_PROCESSING_TIME_SECONDS
            # Alternative: Subtract estimated time for completed files from total estimate
            # estimated_elapsed_for_files = i * time_per_file
            # estimated_remaining_seconds = estimated_total_seconds - estimated_elapsed_for_files
            remaining_time_str = format_time(estimated_remaining_seconds)
            # --- End Remaining Time Calculation ---

            # Update progress bars and status texts including estimated remaining time
            progress_value = i / total_files # Progress based on files started
            progress_text = f"Processing {current_file_status}..."
            status_text = f"🔄 {progress_text} (Est. remaining: ~{remaining_time_str})"

            progress_bar_top.progress(progress_value, text=progress_text) # Bar shows overall progress
            progress_bar_bottom.progress(progress_value, text=progress_text)
            status_text_placeholder_top.info(status_text) # Text shows detail + remaining time
            status_text_placeholder_bottom.info(status_text)

            # --- Start Processing Current File ---
            with results_container:
                st.markdown(f"--- \n**Processing: {original_filename}**")

            raw_text = None
            translated_text = ""
            extraction_error = False
            gemini_error_occurred = False
            word_creation_error_occurred = False

            # 4a. Extract Text
            try:
                raw_text = backend.extract_text_from_docx(file_to_process)
                if isinstance(raw_text, str) and raw_text.startswith("Error:"):
                    with results_container: st.error(f"❌ Error extracting text: {raw_text}")
                    extraction_error = True
                elif not raw_text or not raw_text.strip():
                    with results_container: st.warning(f"⚠️ No text extracted.")
            except Exception as ext_exc:
                with results_container: st.error(f"❌ Unexpected error during text extraction: {ext_exc}")
                extraction_error = True

            # 4b. Translate
            if not extraction_error:
                if raw_text and raw_text.strip():
                    try:
                        processed_text_result = backend.process_text_with_gemini(
                            api_key, raw_text, current_rules, selected_model_id
                        )
                        if processed_text_result is None or (isinstance(processed_text_result, str) and processed_text_result.startswith("Error:")):
                            error_msg = processed_text_result or 'Unknown API error'
                            with results_container: st.error(f"❌ Gemini translation error: {error_msg}")
                            gemini_error_occurred = True
                            translated_text = ""
                        else:
                            translated_text = processed_text_result
                    except Exception as gem_exc:
                        with results_container: st.error(f"❌ Unexpected error during translation: {gem_exc}")
                        gemini_error_occurred = True
                        translated_text = ""
                else:
                    logging.info(f"Skipping translation for '{original_filename}' (no text).")
                    translated_text = ""

                # 4c. Create Doc
                try:
                    word_doc_stream = backend.create_arabic_word_doc_from_text(
                        translated_text, original_filename
                    )
                    if word_doc_stream:
                        processed_doc_streams.append((original_filename, word_doc_stream))
                        files_successfully_processed += 1
                        with results_container:
                            success_msg = f"✅ Created intermediate document."
                            if not translated_text or not translated_text.strip():
                                if gemini_error_occurred: success_msg += " (Note: placeholder used due to translation error)"
                                elif raw_text is None or not raw_text.strip() and not extraction_error: success_msg += " (Note: placeholder used as no text was extracted)"
                                else: success_msg += " (Note: placeholder used as translation was empty)"
                            st.success(success_msg)
                    else:
                        word_creation_error_occurred = True
                        with results_container: st.error(f"❌ Failed to create intermediate Word file (backend returned None).")
                except Exception as doc_exc:
                    word_creation_error_occurred = True
                    with results_container: st.error(f"❌ Error during intermediate Word file creation: {doc_exc}")
            else:
                 with results_container: st.warning(f"⏩ Skipping translation and document creation due to extraction errors.")

            # --- Update Progress Bar Fully After File 'i' is Done ---
            # This makes the bar reflect completed files accurately.
            status_msg_suffix = ""
            if extraction_error or gemini_error_occurred or word_creation_error_occurred: status_msg_suffix = " with issues."
            final_progress_value = (i + 1) / total_files
            final_progress_text = f"Processed {current_file_status}{status_msg_suffix}"
            # Only update the bar's internal text here, the visual status text was updated before processing the file.
            progress_bar_top.progress(final_progress_value, text=final_progress_text)
            progress_bar_bottom.progress(final_progress_value, text=final_progress_text)


        # --- End of file loop ---
        end_time = time.time() # Record end time
        actual_duration_seconds = end_time - start_time
        actual_duration_str = format_time(actual_duration_seconds)

        # 5. --- Merge Documents ---
        # Clear progress bars, update status to merging
        progress_bar_placeholder_top.empty()
        progress_bar_placeholder_bottom.empty()
        merge_status_text = f"Processing complete ({actual_duration_str}). Merging {files_successfully_processed} documents..."
        status_text_placeholder_top.info(merge_status_text)
        status_text_placeholder_bottom.info(merge_status_text)

        final_status_message = ""
        merge_successful = False

        with results_container:
            st.markdown("---") # Separator before final merge status
            if files_successfully_processed > 0:
                st.info(f"💾 Merging {files_successfully_processed} translated Word document(s)... Please wait.")
                try:
                    # Perform the merge
                    merged_buffer = backend.merge_word_documents(processed_doc_streams)
                    if merged_buffer:
                        st.session_state.merged_doc_buffer = merged_buffer
                        st.session_state.files_processed_count = files_successfully_processed
                        merge_successful = True
                        # Final success message
                        final_status_message = f"✅ Success! Merged document created from {files_successfully_processed} source file(s)."
                        if files_successfully_processed < total_files:
                            final_status_message += f" ({total_files - files_successfully_processed} file(s) had issues)."
                        final_status_message += f" Total time: {actual_duration_str}."
                        status_text_placeholder_top.success(final_status_message)
                        status_text_placeholder_bottom.success(final_status_message)
                        rerun_needed = True # Rerun to show download button
                    else:
                        # Merge failed in backend
                        final_status_message = f"❌ Failed to merge Word documents (backend returned None). Total time: {actual_duration_str}."
                        status_text_placeholder_top.error(final_status_message)
                        status_text_placeholder_bottom.error(final_status_message)
                except Exception as merge_exc:
                    # Exception during merge
                    final_status_message = f"❌ Error during document merging: {merge_exc}. Total time: {actual_duration_str}."
                    logging.error(f"Error during merge_word_documents call: {merge_exc}", exc_info=True)
                    status_text_placeholder_top.error(final_status_message)
                    status_text_placeholder_bottom.error(final_status_message)
            elif total_files > 0:
                 # No files were successfully processed to merge
                 final_status_message = f"⚠️ No documents were successfully processed to merge. Total time: {actual_duration_str}."
                 status_text_placeholder_top.warning(final_status_message)
                 status_text_placeholder_bottom.warning(final_status_message)
                 st.info("Please check the individual file statuses above for errors.")
            # Else: No files were uploaded initially, already handled

        # Final state updates
        st.session_state.processing_complete = True
        st.session_state.processing_started = False

        # Rerun if merge was successful to update UI
        if rerun_needed:
            st.rerun()

    else: # Initial checks failed
        st.session_state.processing_started = False

# --- Fallback info message ---
if not st.session_state.ordered_files and not st.session_state.processing_started and not st.session_state.processing_complete:
    st.info("Upload Word (.docx) files using the button above.")

# --- Footer ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
