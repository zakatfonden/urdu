# app.py (Modified for DOCX Input, Translation, and Merging)

import streamlit as st
import backend  # Assumes backend_py_docx_merge.py is in the same directory
import os
from io import BytesIO
import logging
# docx imports no longer needed directly in app.py for this workflow
# from docx import Document
# from docx.shared import Pt
# from docx.enum.text import WD_ALIGN_PARAGRAPH
# from docx.oxml.ns import qn
# from docx.oxml import OxmlElement

# Configure basic logging if needed
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Streamlit Page Configuration ---
st.set_page_config(
    page_title="UrduDoc Translator", # Changed title
    page_icon="🔄",
    layout="wide"
)

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
    """Adds newly uploaded files (.docx) to the ordered list."""
    # --- CHANGED: Use a different key to avoid conflict if user switches between apps ---
    uploader_key = "docx_uploader"
    if uploader_key in st.session_state and st.session_state[uploader_key]:
        current_filenames = {f.name for f in st.session_state.ordered_files}
        new_files_added_count = 0
        for uploaded_file in st.session_state[uploader_key]:
             # Basic check for file extension (optional but good practice)
            if uploaded_file.name.lower().endswith('.docx'):
                if uploaded_file.name not in current_filenames:
                    st.session_state.ordered_files.append(uploaded_file)
                    current_filenames.add(uploaded_file.name)
                    new_files_added_count += 1
                # else: # Optional: Notify about duplicates
                #     st.toast(f"File '{uploaded_file.name}' is already in the list.")
            else:
                 st.warning(f"Skipped '{uploaded_file.name}'. Only .docx files are accepted.", icon="⚠️")


        if new_files_added_count > 0:
            st.toast(f"Added {new_files_added_count} new DOCX file(s) to the list.")
            reset_processing_state()
        # Clear the uploader widget state after processing
        # st.session_state[uploader_key] = [] # Optional

def clear_all_files_callback():
    """Clears the ordered file list and resets processing state."""
    st.session_state.ordered_files = []
    # --- CHANGED: Use the correct uploader key ---
    uploader_key = "docx_uploader"
    if uploader_key in st.session_state:
        st.session_state[uploader_key] = []
    reset_processing_state()
    st.toast("Removed all files from the list.")


# --- Page Title ---
st.title("🔄 Urdu/Farsi/English DOCX to Arabic Translator") # Changed
st.markdown("Upload Word (`.docx`) files, arrange order, translate content to Arabic, and download the merged result.") # Changed

# --- Sidebar ---
st.sidebar.header("⚙️ Configuration")

# API Key Input (Unchanged)
api_key_from_secrets = st.secrets.get("GEMINI_API_KEY", "")
api_key = st.sidebar.text_input(
    "Enter your Google Gemini API Key", type="password",
    help="Required for translation. Get your key from Google AI Studio.", value=api_key_from_secrets or ""
)
# API Key Status Messages (Unchanged)
if api_key_from_secrets and api_key == api_key_from_secrets: st.sidebar.success("API Key loaded from Secrets.", icon="✅")
elif not api_key_from_secrets and not api_key: st.sidebar.warning("API Key not found or entered.", icon="🔑")
elif api_key and not api_key_from_secrets: st.sidebar.info("Using manually entered API Key.", icon="⌨️")
elif api_key and api_key_from_secrets and api_key != api_key_from_secrets: st.sidebar.info("Using manually entered API Key (overrides secret).", icon="⌨️")

# Model Selection (Unchanged)
st.sidebar.markdown("---")
st.sidebar.header("🧠 AI Model for Translation")
model_options = {
    "Gemini 1.5 Flash (Fastest, Cost-Effective)": "gemini-1.5-flash-latest",
    "Gemini 1.5 Pro (Advanced, Slower, Higher Cost)": "gemini-1.5-pro-latest",
}
selected_model_display_name = st.sidebar.selectbox(
    "Choose the Gemini model for translation:",
    options=list(model_options.keys()),
    index=0,
    key="gemini_model_select",
    help="Select the AI model. Pro is better for nuanced translation."
)
selected_model_id = model_options[selected_model_display_name]
st.sidebar.caption(f"Selected model ID: `{selected_model_id}`")

# --- UPDATED: Translation Rules ---
st.sidebar.markdown("---")
st.sidebar.header("📜 Translation Rules")
# Simplified prompt focusing only on translation
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
# --- END UPDATED RULES ---


# --- Main Area ---

st.header("📁 Manage DOCX Files for Translation")

# --- CHANGED: File Uploader for DOCX ---
uploaded_files_widget = st.file_uploader(
    "Choose Word (.docx) files to translate:",
    type="docx",  # Accept only .docx
    accept_multiple_files=True,
    key="docx_uploader", # Use a distinct key
    on_change=handle_uploads,
    label_visibility="visible"
)
# ---

st.markdown("---")

# --- TOP: Buttons Area & Progress Indicators ---
st.subheader("🚀 Actions & Progress (Top)")
col_b1_top, col_b2_top = st.columns([3, 2])

with col_b1_top:
    # --- CHANGED: Button key and label ---
    process_button_top_clicked = st.button(
        "✨ Translate Files & Merge (Top)",
        key="process_button_top_docx", # New key
        use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files
    )

with col_b2_top:
    # Show download button if buffer exists and not processing
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
        # --- CHANGED: Download button key, label, filename ---
        st.download_button(
            label=f"📥 Download Merged ({st.session_state.files_processed_count}) Translations (.docx)",
            data=st.session_state.merged_doc_buffer,
            file_name="merged_arabic_translations.docx", # New filename
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button_top_docx", # New key
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

# --- Interactive File List (Unchanged logic, displays .docx files) ---
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

    # --- CHANGED: Button key ---
    st.button("🗑️ Remove All Files",
              key="remove_all_button_docx", # New key
              on_click=clear_all_files_callback,
              help="Click to remove all files from the list.",
              type="secondary")


st.markdown("---") # Separator after file list

# --- BOTTOM: Buttons Area & Progress Indicators ---
st.subheader("🚀 Actions & Progress (Bottom)")
col_b1_bottom, col_b2_bottom = st.columns([3, 2])

with col_b1_bottom:
     # --- CHANGED: Button key and label ---
    process_button_bottom_clicked = st.button(
        "✨ Translate Files & Merge (Bottom)",
        key="process_button_bottom_docx", # New key
        use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files
    )

with col_b2_bottom:
    # Show download button if buffer exists and not processing
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
         # --- CHANGED: Download button key, label, filename ---
        st.download_button(
            label=f"📥 Download Merged ({st.session_state.files_processed_count}) Translations (.docx)",
            data=st.session_state.merged_doc_buffer,
            file_name="merged_arabic_translations.docx", # New filename
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button_bottom_docx", # New key
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
    reset_processing_state()
    st.session_state.processing_started = True

    # Re-check conditions
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

    # Proceed only if checks passed
    if st.session_state.ordered_files and api_key and st.session_state.processing_started and selected_model_id:

        processed_doc_streams = [] # List to hold intermediate arabic doc streams
        files_successfully_processed = 0 # Counter for successful intermediate docs
        total_files = len(st.session_state.ordered_files)

        # Initialize BOTH progress bars
        progress_bar_top = progress_bar_placeholder_top.progress(0, text="Starting processing...")
        progress_bar_bottom = progress_bar_placeholder_bottom.progress(0, text="Starting processing...")

        for i, file_to_process in enumerate(st.session_state.ordered_files):
            original_filename = file_to_process.name
            current_file_status = f"'{original_filename}' ({i + 1}/{total_files})"
            progress_text = f"Processing {current_file_status}..."

            # Update progress bars and status texts
            progress_value = i / total_files
            progress_bar_top.progress(progress_value, text=progress_text)
            progress_bar_bottom.progress(progress_value, text=progress_text)
            status_text_placeholder_top.info(f"🔄 Starting {current_file_status}")
            status_text_placeholder_bottom.info(f"🔄 Starting {current_file_status}")

            with results_container:
                st.markdown(f"--- \n**Processing: {original_filename}**")

            raw_text = None
            translated_text = "" # Holds the Arabic translation
            extraction_error = False
            gemini_error_occurred = False
            word_creation_error_occurred = False

            # 1. Extract Text from DOCX
            status_text_placeholder_top.info(f"📄 Extracting text from {current_file_status}...")
            status_text_placeholder_bottom.info(f"📄 Extracting text from {current_file_status}...")
            try:
                # Use the new backend function for DOCX
                raw_text = backend.extract_text_from_docx(file_to_process)
                if isinstance(raw_text, str) and raw_text.startswith("Error:"):
                    with results_container: st.error(f"❌ Error extracting text from '{original_filename}': {raw_text}")
                    extraction_error = True
                elif not raw_text or not raw_text.strip():
                    with results_container: st.warning(f"⚠️ No text extracted from '{original_filename}'. An empty section will be added.")
                    # Keep raw_text empty, translation will be skipped
                # else: # Success
                #    with results_container: st.info(f"Extracted text length: {len(raw_text)}")

            except Exception as ext_exc:
                with results_container: st.error(f"❌ Unexpected error during DOCX text extraction for '{original_filename}': {ext_exc}")
                extraction_error = True

            # 2. Translate with Gemini (if text extracted)
            if not extraction_error:
                if raw_text and raw_text.strip():
                    status_text_placeholder_top.info(f"🤖 Translating text from {current_file_status} via Gemini ({selected_model_display_name})...")
                    status_text_placeholder_bottom.info(f"🤖 Translating text from {current_file_status} via Gemini ({selected_model_display_name})...")
                    try:
                        # Use the same Gemini function, passing the extracted text and translation rules
                        processed_text_result = backend.process_text_with_gemini(
                            api_key, raw_text, current_rules, selected_model_id
                        )
                        if processed_text_result is None or (isinstance(processed_text_result, str) and processed_text_result.startswith("Error:")):
                            with results_container: st.error(f"❌ Gemini translation error for '{original_filename}': {processed_text_result or 'Unknown API error'}")
                            gemini_error_occurred = True
                            translated_text = "" # Use empty string on error
                        else:
                            translated_text = processed_text_result # Store the Arabic translation
                    except Exception as gem_exc:
                        with results_container: st.error(f"❌ Unexpected error during Gemini translation for '{original_filename}': {gem_exc}")
                        gemini_error_occurred = True
                        translated_text = ""
                else:
                    # If no text extracted, skip translation
                    logging.info(f"Skipping Gemini translation for '{original_filename}' as extracted text was empty.")
                    translated_text = "" # Ensure it's empty

                # 3. Create Individual Word Document with Arabic Translation
                status_text_placeholder_top.info(f"📝 Creating intermediate Word document for {current_file_status}...")
                status_text_placeholder_bottom.info(f"📝 Creating intermediate Word document for {current_file_status}...")
                try:
                    # Use the new backend function to create a doc from the translated text
                    word_doc_stream = backend.create_arabic_word_doc_from_text(
                        translated_text,
                        original_filename
                    )
                    if word_doc_stream:
                        # Add the stream to the list for later merging
                        processed_doc_streams.append((original_filename, word_doc_stream))
                        files_successfully_processed += 1 # Increment counter
                        with results_container:
                            success_msg = f"✅ Created intermediate document for '{original_filename}'."
                            if not translated_text or not translated_text.strip():
                                if gemini_error_occurred: success_msg += " (Note: placeholder used due to translation error)"
                                elif raw_text is None or not raw_text.strip() and not extraction_error: success_msg += " (Note: placeholder used as no text was extracted)"
                                else: success_msg += " (Note: placeholder used as translation was empty)"
                            st.success(success_msg)
                    else:
                        word_creation_error_occurred = True
                        with results_container: st.error(f"❌ Failed to create intermediate Word file for '{original_filename}' (backend returned None).")

                except Exception as doc_exc:
                    word_creation_error_occurred = True
                    with results_container: st.error(f"❌ Error during intermediate Word file creation for '{original_filename}': {doc_exc}")

            else: # Extraction failed critically
                 with results_container: st.warning(f"⏩ Skipping translation and document creation for '{original_filename}' due to extraction errors.")


            # Update overall progress on BOTH bars
            status_msg_suffix = ""
            if extraction_error or gemini_error_occurred or word_creation_error_occurred: status_msg_suffix = " with issues."
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

        # 4. --- Merge Documents ---
        final_status_message = ""
        rerun_needed = False

        with results_container:
            st.markdown("---") # Separator before final status
            if files_successfully_processed > 0:
                st.info(f"💾 Merging {files_successfully_processed} translated Word document(s)... Please wait.")
                try:
                    # Call the merge function from the backend
                    merged_buffer = backend.merge_word_documents(processed_doc_streams)

                    if merged_buffer:
                        st.session_state.merged_doc_buffer = merged_buffer
                        st.session_state.files_processed_count = files_successfully_processed
                        final_status_message = f"✅ Processing complete! Merged document created from {files_successfully_processed} source file(s)."
                        if files_successfully_processed < total_files:
                             final_status_message += f" ({total_files - files_successfully_processed} file(s) had issues)."
                        st.success(final_status_message)
                        rerun_needed = True # Rerun to show download buttons
                    else:
                        final_status_message = "❌ Failed to merge Word documents (backend returned None)."
                        st.error(final_status_message)

                except Exception as merge_exc:
                    final_status_message = f"❌ Error during document merging: {merge_exc}"
                    logging.error(f"Error during merge_word_documents call: {merge_exc}", exc_info=True)
                    st.error(final_status_message)
            elif total_files > 0:
                 final_status_message = "⚠️ No documents were successfully processed to merge."
                 st.warning(final_status_message)
                 st.info("Please check the individual file statuses above for errors.")
            # Else: No files were uploaded initially, already handled

        st.session_state.processing_complete = True
        st.session_state.processing_started = False

        if rerun_needed:
            st.rerun() # Rerun to make download buttons visible / update UI state

    else: # Initial checks failed (no files, no api key, etc.)
        st.session_state.processing_started = False # Ensure it's reset


# --- Fallback info message ---
if not st.session_state.ordered_files and not st.session_state.processing_started and not st.session_state.processing_complete:
    st.info("Upload Word (.docx) files using the button above.")

# --- Footer ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
