# app.py (Modified for direct appending)

import streamlit as st
import backend  # Assumes backend.py is in the same directory
import os
from io import BytesIO
import logging

# --- NEW: Import docx elements for direct manipulation ---
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
# ---

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
    'files_processed_count': 0, # Counts files successfully appended
    'processing_complete': False,
    'processing_started': False,
    'ordered_files': [],
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
st.markdown("Upload Arabic PDF files, arrange their processing order, then process and download as a single Word document.") # Modified description

# --- Sidebar (Unchanged) ---
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

# Model Selection (Unchanged)
st.sidebar.markdown("---") # Separator
st.sidebar.header("🧠 AI Model")
model_options = {
    "Gemini 1.5 Flash (Fastest, Cost-Effective)": "gemini-1.5-flash-latest",
    "Gemini 1.5 Pro (Advanced, Slower, Higher Cost)": "gemini-1.5-pro-latest",
}
selected_model_display_name = st.sidebar.selectbox(
    "Choose the Gemini model for processing:",
    options=list(model_options.keys()),
    index=0,
    key="gemini_model_select",
    help="Select the AI model. Pro is more capable but slower and costs more."
)
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

# --- TOP: Buttons Area & Progress Indicators (Updated labels) ---
st.subheader("🚀 Actions & Progress (Top)")
col_b1_top, col_b2_top = st.columns([3, 2])

with col_b1_top:
    process_button_top_clicked = st.button(
        "✨ Process Files & Create Document (Top)", # Renamed
        key="process_button_top",
        use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files
    )

with col_b2_top:
    # Show download button if buffer exists and not processing
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
        st.download_button(
            label=f"📥 Download Processed ({st.session_state.files_processed_count}) Files (.docx)", # Updated label
            data=st.session_state.merged_doc_buffer,
            file_name="processed_arabic_document.docx", # Updated filename
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button_top",
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

# --- Interactive File List (Unchanged) ---
st.subheader(f"Files in Processing Order ({len(st.session_state.ordered_files)}):")

if not st.session_state.ordered_files:
    st.info("Use the uploader above to add files. They will appear here for ordering.")
else:
    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([0.5, 5, 1, 1, 1])
    with col_h1: st.markdown("**#**")
    with col_h2: st.markdown("**Filename**")
    with col_h3: st.markdown("**Up**")
    with col_h4: st.markdown("**Down**")
    with col_h5: st.markdown("**Remove**")

    for i, file in enumerate(st.session_state.ordered_files):
        col1, col2, col3, col4, col5 = st.columns([0.5, 5, 1, 1, 1])
        with col1: st.write(f"{i+1}")
        with col2: st.write(file.name)
        with col3: st.button("⬆️", key=f"up_{i}", on_click=move_file, args=(i, -1), disabled=(i == 0), help="Move Up")
        with col4: st.button("⬇️", key=f"down_{i}", on_click=move_file, args=(i, 1), disabled=(i == len(st.session_state.ordered_files) - 1), help="Move Down")
        with col5: st.button("❌", key=f"del_{i}", on_click=remove_file, args=(i,), help="Remove")

    st.button("🗑️ Remove All Files",
              key="remove_all_button",
              on_click=clear_all_files_callback,
              help="Click to remove all files from the list.",
              type="secondary")


st.markdown("---") # Separator after file list

# --- BOTTOM: Buttons Area & Progress Indicators (Updated labels) ---
st.subheader("🚀 Actions & Progress (Bottom)")
col_b1_bottom, col_b2_bottom = st.columns([3, 2])

with col_b1_bottom:
    process_button_bottom_clicked = st.button(
        "✨ Process Files & Create Document (Bottom)", # Renamed
        key="process_button_bottom",
        use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files
    )

with col_b2_bottom:
    # Show download button if buffer exists and not processing
    if st.session_state.merged_doc_buffer and not st.session_state.processing_started:
        st.download_button(
            label=f"📥 Download Processed ({st.session_state.files_processed_count}) Files (.docx)", # Updated label
            data=st.session_state.merged_doc_buffer,
            file_name="processed_arabic_document.docx", # Updated filename
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            key="download_merged_button_bottom",
            use_container_width=True
        )
    elif st.session_state.processing_started:
        st.info("Processing in progress...", icon="⏳")
    else:
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
    elif not selected_model_id:
        st.error("❌ No Gemini model selected in the sidebar.")
        st.session_state.processing_started = False

    # Proceed only if checks passed
    if st.session_state.ordered_files and api_key and st.session_state.processing_started and selected_model_id:

        # --- NEW: Initialize the master Document object ---
        master_document = Document()
        try:
            # Set default styles ONCE for the whole document
            style = master_document.styles['Normal']
            font = style.font
            font.name = 'Arial'
            font.rtl = True

            # Set complex script font using oxml
            style_element = style.element
            rpr_elements = style_element.xpath('.//w:rPr')
            rpr = rpr_elements[0] if rpr_elements else OxmlElement('w:rPr')
            if not rpr_elements: style_element.append(rpr) # Append if created

            font_name_element = rpr.find(qn('w:rFonts'))
            if font_name_element is None:
                font_name_element = OxmlElement('w:rFonts')
                rpr.append(font_name_element)
            font_name_element.set(qn('w:cs'), 'Arial') # Complex Script font

            # Set default paragraph format to RTL
            paragraph_format = style.paragraph_format
            paragraph_format.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            paragraph_format.right_to_left = True
            logging.info("Initialized master Document and set default styles for Arabic.")
        except Exception as style_exc:
            logging.error(f"Failed to set default styles on master document: {style_exc}", exc_info=True)
            st.error(f"❌ Critical error initializing document styles: {style_exc}")
            st.session_state.processing_started = False # Stop processing
            master_document = None # Ensure we don't proceed


        # --- Proceed only if document initialization succeeded ---
        if master_document is not None:
            files_successfully_appended = 0 # Counter for successful appends
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
                append_error_occurred = False # New flag for append errors

                # 1. Extract Text
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
                        with results_container: st.warning(f"⚠️ No text extracted from '{original_filename}'. Placeholder will be added.")
                        processed_text = "" # Ensure processed_text is empty for append logic
                except Exception as ext_exc:
                    with results_container: st.error(f"❌ Unexpected error during text extraction for '{original_filename}': {ext_exc}")
                    extraction_error = True

                # 2. Process with Gemini
                if not extraction_error: # Proceed only if extraction didn't fail critically
                    if raw_text and raw_text.strip(): # Only call Gemini if there's text
                        status_text_placeholder_top.info(f"🤖 Sending text from {current_file_status} to Gemini ({selected_model_display_name})...")
                        status_text_placeholder_bottom.info(f"🤖 Sending text from {current_file_status} to Gemini ({selected_model_display_name})...")
                        try:
                            processed_text_result = backend.process_text_with_gemini(
                                api_key, raw_text, rules_prompt, selected_model_id
                            )
                            if processed_text_result is None or (isinstance(processed_text_result, str) and processed_text_result.startswith("Error:")):
                                with results_container: st.error(f"❌ Gemini error for '{original_filename}': {processed_text_result or 'Unknown API error'}")
                                gemini_error_occurred = True
                                processed_text = "" # Use empty string on Gemini error
                            else:
                                processed_text = processed_text_result
                        except Exception as gem_exc:
                            with results_container: st.error(f"❌ Unexpected error during Gemini processing for '{original_filename}': {gem_exc}")
                            gemini_error_occurred = True
                            processed_text = "" # Use empty string on unexpected error
                    else:
                         # If extraction yielded empty text, processed_text remains ""
                         logging.info(f"Skipping Gemini for '{original_filename}' as extracted text was empty.")

                    # 3. --- NEW: Append to Master Document ---
                    status_text_placeholder_top.info(f"📝 Appending content for {current_file_status} to document...")
                    status_text_placeholder_bottom.info(f"📝 Appending content for {current_file_status} to document...")
                    try:
                        append_success = backend.append_text_to_document(
                            master_document,
                            processed_text,
                            original_filename,
                            is_first_file=(i == 0)
                        )
                        if append_success:
                            with results_container:
                                success_msg = f"✅ Appended content for '{original_filename}'."
                                if not processed_text or not processed_text.strip():
                                    if gemini_error_occurred: success_msg += " (Note: placeholder used due to Gemini error)"
                                    elif raw_text is None or not raw_text.strip() and not extraction_error: success_msg += " (Note: placeholder used as no text was extracted)"
                                    else: success_msg += " (Note: placeholder used as content was empty)"
                                st.success(success_msg)
                            files_successfully_appended += 1 # Increment success counter
                        else:
                            # Error message should have been logged/added by backend function
                            with results_container: st.error(f"❌ Failed to append content for '{original_filename}' (see logs/document for details).")
                            append_error_occurred = True

                    except Exception as append_exc:
                        with results_container: st.error(f"❌ Unexpected error appending content for '{original_filename}': {append_exc}")
                        append_error_occurred = True

                else: # Extraction failed critically
                     with results_container: st.warning(f"⏩ Skipping Gemini processing and document appending for '{original_filename}' due to extraction errors.")


                # Update overall progress on BOTH bars
                status_msg_suffix = ""
                if extraction_error or gemini_error_occurred or append_error_occurred: status_msg_suffix = " with issues."
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

            # 4. --- NEW: Save the Master Document ---
            final_status_message = ""
            rerun_needed = False

            with results_container:
                st.markdown("---") # Separator before final status
                if files_successfully_appended > 0 or total_files > 0: # Save even if only placeholders/errors were added
                    st.info(f"💾 Finalizing Word document containing content from {files_successfully_appended}/{total_files} file(s)...")
                    try:
                        final_doc_stream = io.BytesIO()
                        master_document.save(final_doc_stream)
                        final_doc_stream.seek(0)

                        st.session_state.merged_doc_buffer = final_doc_stream
                        st.session_state.files_processed_count = files_successfully_appended # Store count of successes
                        final_status_message = f"✅ Processing complete! Document created with content from {files_successfully_appended} source file(s)."
                        if files_successfully_appended < total_files:
                             final_status_message += f" ({total_files - files_successfully_appended} file(s) had issues - check statuses above)."
                        st.success(final_status_message)
                        rerun_needed = True # Rerun to show download buttons

                    except Exception as save_exc:
                        final_status_message = f"❌ Error saving the final Word document: {save_exc}"
                        logging.error(f"Error during final document save: {save_exc}", exc_info=True)
                        st.error(final_status_message)
                else: # Should not happen if initial checks passed, but as a fallback
                    final_status_message = "⚠️ No files were processed or appended."
                    st.warning(final_status_message)

            st.session_state.processing_complete = True
            st.session_state.processing_started = False

            if rerun_needed:
                st.rerun() # Rerun to make download buttons visible / update UI state

    else: # Initial checks failed (no files, no api key, etc.) or doc init failed
        st.session_state.processing_started = False # Ensure it's reset


# --- Fallback info message (Unchanged) ---
if not st.session_state.ordered_files and not st.session_state.processing_started and not st.session_state.processing_complete:
    st.info("Upload PDF files using the 'Choose PDF files' button above.")

# --- Footer (Unchanged) ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
