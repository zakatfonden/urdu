# app.py
import streamlit as st
import backend # Assumes backend.py is in the same directory
import os
from io import BytesIO
import logging # Optional: if you want frontend logging too

# ... (rest of imports and config) ...

# --- Initialize Session State ---
# ... (session state setup) ...

# --- Page Title ---
st.title("📄 ArabicPDF - PDF to Word Extractor")
st.markdown("Upload Arabic PDF files (text-based or image-based), apply rules via Gemini, and download as Word documents.")
st.info("ℹ️ **Note:** For image-based PDFs (scans), this app uses OCR. This requires **Tesseract OCR engine** (with Arabic language pack) and **Poppler** to be installed on the system where the app is running.")


# --- Sidebar for Configuration ---
st.sidebar.header("⚙️ Configuration")
# ... (API Key Input) ...
# ... (Model Selection) ...
# ... (Extraction Rules) ...

# Add dependency note to sidebar too? Optional.
st.sidebar.markdown("---")
st.sidebar.caption("Requires Tesseract & Poppler for OCR on image-based PDFs.")


# --- Main Area for File Upload and Processing ---
# ... (rest of file upload logic) ...

# --- Buttons Area ---
# ... (button logic) ...

# --- UI Elements for Progress ---
# ... (placeholders) ...

# --- Processing Logic ---
if process_button_clicked:
    # ... (start of processing logic) ...

            # 1. Extract Text (Now potentially uses OCR)
            status_text_placeholder.info(f"📄 Extracting text from {current_file_status} (using PyPDF2/OCR)...") # Updated message
            # Give the raw uploaded file object to the backend function
            uploaded_file.seek(0) # Ensure the uploader stream is at the start
            raw_text = backend.extract_text_from_pdf(uploaded_file) # Pass the file obj directly

            if raw_text is None: # Check for None indicating critical failure
                 with results_container:
                     st.error(f"❌ Critical error extracting text (PyPDF2 and OCR failed or dependencies missing). Skipping.")
                 progress_bar.progress((i + 1) / total_files, text=progress_text + " Extraction Error.")
                 continue # Skip to next file
            elif not raw_text.strip(): # Check for empty string (extraction worked but found nothing)
                 with results_container:
                     st.warning(f"⚠️ No text extracted (PDF might be image-only with no OCR results, or truly empty). Creating empty Word file '{docx_filename}'.")
                 # Proceed to create an empty docx
                 processed_text = ""
                 gemini_error_occurred = False # No Gemini call needed
            else:
                # 2. Process with Gemini (Only if text was extracted)
                status_text_placeholder.info(f"🤖 Sending text from {current_file_status} to Gemini ({model_name})...")
                processed_text_result = backend.process_text_with_gemini(api_key, model_name, raw_text, rules_prompt)

                # Check if the result is an error string
                if isinstance(processed_text_result, str) and processed_text_result.startswith("Error:"):
                     with results_container:
                         st.error(f"❌ Gemini error: {processed_text_result}")
                     gemini_error_occurred = True
                     # Decide if you want to create an empty doc or skip
                     # Here we'll skip creating doc on Gemini error
                     progress_bar.progress((i + 1) / total_files, text=progress_text + " Gemini Error.")
                     continue # Skip to next file

                else:
                     processed_text = processed_text_result
                     gemini_error_occurred = False # Reset flag if successful
                     # logger.info(f"Gemini processing successful for {original_filename}.")


            # 3. Create Word Document (Proceed if text extraction worked, even if empty, unless Gemini errored)
            # No direct changes needed here, just ensure it handles empty processed_text gracefully
            # which the backend function already does.
            status_text_placeholder.info(f"📝 Creating Word document '{docx_filename}'...")
            try:
                # Pass the potentially empty processed_text
                word_doc_stream = backend.create_word_document(processed_text)
                if word_doc_stream:
                    processed_files_data.append((docx_filename, word_doc_stream))
                    files_successfully_processed_count += 1
                    with results_container:
                        st.success(f"✅ Created '{docx_filename}'")
                else:
                    with results_container:
                        st.error(f"❌ Failed to create Word stream for '{docx_filename}' (backend returned None).")
            except Exception as doc_exc:
                 with results_container:
                     st.error(f"❌ Error during Word document creation for '{original_filename}': {doc_exc}")

            # Update progress bar after file completion or error
            progress_bar.progress((i + 1) / total_files, text=f"Processed {current_file_status}")

    # ... (rest of processing logic: zipping, state updates, etc.) ...

# --- Fallback info message ---
# ... (fallback message) ...

# --- Footer ---
# ... (footer) ...
