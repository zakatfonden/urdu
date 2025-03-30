# app.py (with Custom File Ordering)

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
    'ordered_files': [],  # <-- NEW: List to hold UploadedFile objects in custom order
}
for key, value in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = value

# --- Helper Functions for Modifying Order ---
# Place these before they are called by buttons

def reset_processing_state():
    """Resets state related to processing results and status."""
    st.session_state.merged_doc_buffer = None
    st.session_state.files_processed_count = 0
    st.session_state.processing_complete = False
    st.session_state.processing_started = False
    # logger.info("Processing state reset.")

def move_file(index, direction):
    """Moves the file at the given index up (direction=-1) or down (direction=1)."""
    files = st.session_state.ordered_files
    if not (0 <= index < len(files)):
        return # Index out of bounds

    new_index = index + direction
    if not (0 <= new_index < len(files)):
        return # Cannot move past ends

    # Swap elements
    files[index], files[new_index] = files[new_index], files[index]
    st.session_state.ordered_files = files # Update state
    reset_processing_state() # Order changed, invalidate previous results
    # No rerun needed, Streamlit handles rerun on state change from button click

def remove_file(index):
    """Removes the file at the given index."""
    files = st.session_state.ordered_files
    if 0 <= index < len(files):
        removed_file = files.pop(index)
        st.toast(f"Removed '{removed_file.name}'.")
        st.session_state.ordered_files = files # Update state
        reset_processing_state() # List changed, invalidate previous results
    else:
        st.warning(f"Could not remove file at index {index} (already removed or invalid?).")
    # No rerun needed

def handle_uploads():
    """Adds newly uploaded files to the ordered list, avoiding duplicates by name."""
    if 'pdf_uploader' in st.session_state and st.session_state.pdf_uploader:
        # Get filenames currently in our ordered list
        current_filenames = {f.name for f in st.session_state.ordered_files}
        new_files_added_count = 0
        # Check each file currently in the uploader widget's state
        for uploaded_file in st.session_state.pdf_uploader:
            if uploaded_file.name not in current_filenames:
                st.session_state.ordered_files.append(uploaded_file)
                current_filenames.add(uploaded_file.name) # Add to set to track additions within this batch
                new_files_added_count += 1

        if new_files_added_count > 0:
            st.toast(f"Added {new_files_added_count} new file(s) to the end of the list.")
            reset_processing_state() # New files added, invalidate previous results
            # Clear the uploader widget state *after* processing its contents
            # Note: This might feel slightly unintuitive as the widget clears,
            # but the files are now managed in st.session_state.ordered_files.
            # Consider if you want the uploader to *retain* the files visually.
            # If so, remove the line below, but be mindful of how users add *more* files.
            # st.session_state.pdf_uploader = [] # Optional: Clear uploader widget state

def clear_all_files_callback():
    """Clears the ordered file list and resets processing state."""
    st.session_state.ordered_files = []
    # Also clear the file uploader widget state if needed
    if 'pdf_uploader' in st.session_state:
        st.session_state.pdf_uploader = []
    reset_processing_state()
    st.toast("Removed all files from the list.")


# --- Page Title ---
st.title("📄 ArabicPDF - PDF to Word Extractor")
st.markdown("Upload Arabic PDF files, arrange their processing order, then merge and download.")

# --- Sidebar for Configuration (remains the same) ---
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


# --- Main Area ---

st.header("📁 Manage Files for Processing")

# --- File Uploader (triggers adding to the list) ---
# Use 'on_change' to add files to our managed list in session state
uploaded_files_widget = st.file_uploader(
    "Choose PDF files to add to the list below:", type="pdf", accept_multiple_files=True,
    key="pdf_uploader", # Assign key to access its state and potentially clear it
    on_change=handle_uploads, # Callback adds new files to st.session_state.ordered_files
    label_visibility="visible" # Make label visible
)

st.markdown("---")

# --- Interactive File List ---
st.subheader(f"Files in Processing Order ({len(st.session_state.ordered_files)}):")

if not st.session_state.ordered_files:
    st.info("Use the uploader above to add files. They will appear here for ordering.")
else:
    # Header row for the interactive list
    col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([0.5, 5, 1, 1, 1]) # Adjust ratios as needed
    with col_h1: st.markdown("**#**")
    with col_h2: st.markdown("**Filename**")
    with col_h3: st.markdown("**Up**")
    with col_h4: st.markdown("**Down**")
    with col_h5: st.markdown("**Remove**")

    # Display each file with interactive buttons
    for i, file in enumerate(st.session_state.ordered_files):
        col1, col2, col3, col4, col5 = st.columns([0.5, 5, 1, 1, 1]) # Match header ratios
        with col1:
            st.write(f"{i+1}") # Display number
        with col2:
            st.write(file.name) # Display filename
        with col3:
            # Disable "Up" button for the first item
            st.button("⬆️", key=f"up_{i}", on_click=move_file, args=(i, -1), disabled=(i == 0), help="Move Up")
        with col4:
            # Disable "Down" button for the last item
            st.button("⬇️", key=f"down_{i}", on_click=move_file, args=(i, 1), disabled=(i == len(st.session_state.ordered_files) - 1), help="Move Down")
        with col5:
            # Use a unique key based on index for removal
            st.button("❌", key=f"del_{i}", on_click=remove_file, args=(i,), help="Remove")

    # Add a button to clear the entire list
    st.button("🗑️ Remove All Files",
              key="remove_all_button",
              on_click=clear_all_files_callback, # Use specific callback
              help="Click to remove all files from the list.",
              type="secondary") # Make it less prominent than process


st.markdown("---") # Separator before action buttons


# --- Buttons Area ---
col_b1, col_b2 = st.columns([3, 2]) # Ratio for Process vs Download buttons

with col_b1:
    process_button_clicked = st.button(
        "✨ Process Files in Current Order & Merge",
        key="process_button", use_container_width=True, type="primary",
        disabled=st.session_state.processing_started or not st.session_state.ordered_files # Disable if processing or no files in list
    )

with col_b2:
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


# --- UI Elements for Progress ---
progress_bar_placeholder = st.empty()
status_text_placeholder = st.empty()

# --- Container for Individual File Results (Displayed below progress) ---
results_container = st.container()


# --- Processing Logic (Iterates over st.session_state.ordered_files) ---
if process_button_clicked:
    # Reset state again just to be safe when processing starts
    reset_processing_state()
    st.session_state.processing_started = True

    # Re-check conditions (API key, rules)
    if not st.session_state.ordered_files: # Check our ordered list now
        st.warning("⚠️ No files in the list to process.")
        st.session_state.processing_started = False
    elif not api_key:
        st.error("❌ Please enter or configure your Gemini API Key in the sidebar.")
        st.session_state.processing_started = False
    elif not rules_prompt:
        st.warning("⚠️ The 'Extraction Rules' field is empty. Processing without specific instructions.")

    # Proceed only if checks passed and processing started
    if st.session_state.ordered_files and api_key and st.session_state.processing_started:

        # List to collect individual Word doc streams for merging (in order)
        processed_doc_streams = [] # Stores tuples of (filename, stream)

        total_files = len(st.session_state.ordered_files)
        progress_bar = progress_bar_placeholder.progress(0, text="Starting processing...")

        # --- Iterate through the ORDERED list from session state ---
        for i, file_to_process in enumerate(st.session_state.ordered_files):
            original_filename = file_to_process.name
            current_file_status = f"'{original_filename}' ({i + 1}/{total_files})"
            progress_text = f"Processing {current_file_status}..."
            progress_bar.progress(i / total_files, text=progress_text)
            status_text_placeholder.info(f"🔄 Starting {current_file_status}")

            with results_container:
                st.markdown(f"--- \n**Processing: {original_filename}**")

            raw_text = None
            processed_text = ""
            extraction_error = False
            gemini_error_occurred = False
            word_creation_error_occurred = False

            # 1. Extract Text
            status_text_placeholder.info(f"📄 Extracting text from {current_file_status}...")
            try:
                 # --- Pass file object directly, ensure pointer is at start ---
                 file_to_process.seek(0)
                 raw_text = backend.extract_text_from_pdf(file_to_process)
                 # --- Backend error handling remains the same ---
                 if raw_text is None:
                     with results_container: st.error(f"❌ Critical error during text extraction. Skipping '{original_filename}'.")
                     extraction_error = True
                 elif isinstance(raw_text, str) and raw_text.startswith("Error:"):
                     with results_container: st.error(f"❌ Error extracting text from '{original_filename}': {raw_text}")
                     extraction_error = True
                 elif not raw_text or not raw_text.strip():
                     with results_container: st.warning(f"⚠️ No text extracted from '{original_filename}'. An empty section will be added.")
                     processed_text = "" # Ensure it's empty for doc creation
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
                         processed_text = "" # Use empty if Gemini fails
                     else:
                         processed_text = processed_text_result
                 except Exception as gem_exc:
                      with results_container: st.error(f"❌ Unexpected error during Gemini processing for '{original_filename}': {gem_exc}")
                      gemini_error_occurred = True
                      processed_text = "" # Use empty on unexpected error

            # 3. Create Individual Word Document (always attempt unless critical extraction error)
            word_doc_stream = None
            if not extraction_error: # Only skip if extraction failed completely
                 status_text_placeholder.info(f"📝 Creating intermediate Word document for {current_file_status}...")
                 try:
                     # processed_text will be "" if extraction yielded nothing or Gemini failed
                     word_doc_stream = backend.create_word_document(processed_text)
                     if word_doc_stream:
                          # Append the stream *along with the original filename* for potential use in merging logic
                          processed_doc_streams.append((original_filename, word_doc_stream))
                          with results_container:
                               success_msg = f"✅ Created intermediate Word file for '{original_filename}'."
                               # Add note if content is empty/placeholder
                               if not processed_text or not processed_text.strip():
                                   if gemini_error_occurred:
                                       success_msg += " (Note: placeholder text used due to Gemini error)"
                                   elif raw_text is None or not raw_text.strip():
                                        success_msg += " (Note: placeholder text used as no text was extracted)"
                                   else: # Case where Gemini might have returned empty string legitimately
                                       success_msg += " (Note: content appears empty)"

                               st.success(success_msg)
                     else:
                          word_creation_error_occurred = True
                          with results_container: st.error(f"❌ Failed to create intermediate Word file for '{original_filename}' (backend returned None).")

                 except Exception as doc_exc:
                      word_creation_error_occurred = True
                      with results_container: st.error(f"❌ Error during intermediate Word file creation for '{original_filename}': {doc_exc}")

            # Update overall progress
            status_msg_suffix = ""
            if extraction_error or word_creation_error_occurred or gemini_error_occurred:
                 status_msg_suffix = " with issues." # More generic than "Error."
            progress_bar.progress((i + 1) / total_files, text=f"Processed {current_file_status}{status_msg_suffix}")

        # --- End of file loop ---

        # Clear progress bar and transient status text
        progress_bar_placeholder.empty()
        status_text_placeholder.empty()

        # 4. Merge Documents and Update State
        final_status_message = ""
        rerun_needed = False
        successfully_created_doc_count = len(processed_doc_streams)

        with results_container:
            st.markdown("---") # Separator before final status
            if successfully_created_doc_count > 0:
                st.info(f"💾 Merging {successfully_created_doc_count} intermediate Word document(s)... Please wait.")
                try:
                    # Pass the list of (filename, stream) tuples
                    merged_doc_buffer = backend.merge_word_documents(processed_doc_streams)

                    if merged_doc_buffer:
                        st.session_state.merged_doc_buffer = merged_doc_buffer
                        st.session_state.files_processed_count = successfully_created_doc_count
                        final_status_message = f"✅ Processing complete! Merged document created from {successfully_created_doc_count} source file(s). Click 'Download Merged' above."
                        st.success(final_status_message)
                        rerun_needed = True # To show download button
                    else:
                        final_status_message = "❌ Failed to merge Word documents (backend returned None)."
                        st.error(final_status_message)

                except Exception as merge_exc:
                    final_status_message = f"❌ Error during document merging: {merge_exc}"
                    logging.error(f"Error during merge_word_documents call: {merge_exc}", exc_info=True)
                    st.error(final_status_message)

            else: # No individual documents were successfully created to merge
                 final_status_message = "⚠️ No intermediate Word documents were successfully created to merge."
                 st.warning(final_status_message)
                 if st.session_state.ordered_files: # Check if there were files initially
                      st.info("Please check the individual file statuses above for errors.")

        # Update final state variables
        st.session_state.processing_complete = True
        st.session_state.processing_started = False

        if rerun_needed:
            st.rerun() # Rerun to make download button visible / update UI state

    else:
        # Case where processing didn't start due to initial checks failing
        if not st.session_state.ordered_files or not api_key:
             st.session_state.processing_started = False # Ensure it's reset


# --- Fallback info message ---
if not st.session_state.ordered_files and not st.session_state.processing_started and not st.session_state.processing_complete:
    st.info("Upload PDF files using the 'Choose PDF files' button above.")

# --- Footer ---
st.markdown("---")
st.markdown("Developed with Streamlit and Google Gemini.")
