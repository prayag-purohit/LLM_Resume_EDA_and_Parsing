"""
Resume Extraction and EDA Multi-Agent Workflow
=============================================

This script automates the process of extracting structured data from resumes using multiple Gemini LLM agents, performing Exploratory Data Analysis (EDA), and validating the results. It is designed for batch processing of resume files and saving results to MongoDB.

Workflow Overview
-----------------
1. **File Preparation**: Loops through all files in the `Resume_inputs` directory.
2. **Conversion**: Converts `.docx` resumes to PDF and archives the originals.
3. **Upload**: Uploads each resume to the root Gemini agent.
4. **First Pass (Resume Data Extraction)**: Uses a Gemini agent to extract structured data from the resume using a prompt template.
5. **Second Pass (EDA)**: Runs EDA on the extracted data using another Gemini agent and a separate prompt template.
6. **Third Pass (Validation)**: Validates the extracted and analyzed data using a validation agent.
7. **Saving Results**: Saves all LLM responses to MongoDB. If saving fails, raw responses are logged for debugging.
8. **Cleanup**: Deletes uploaded files from the agent and moves processed files to the archive directory.

**Agent Retry Logic and Pipeline Re-runs**
------------------------------------------
- Each agent step (Extraction, EDA, Validation) includes robust retry logic:
    - If the LLM response is empty, missing, or contains invalid JSON, the agent will retry up to 2 times (`MAX_RETRIES`).
    - All parsing errors and retry attempts are logged for traceability.
- If the validation agent returns a `validation_score` less than 7, the entire extraction/EDA/validation pipeline is re-run (up to 2 additional times per file).
    - Each pipeline re-run also includes per-agent retries as above.
    - Validation flags are logged when the score is low.
- Files are only moved to the processed directory after all retries and re-runs are complete, ensuring only successfully processed files are archived.

Key Components
--------------
- **GeminiProcessor**: Handles LLM interactions for each task (extraction, EDA, validation).
- **MongoDB Integration**: Saves structured responses for further analysis.
- **Logging**: Tracks progress and errors for each file, including retry and re-run attempts.
- **Error Handling & Retries**: Retries LLM calls if invalid JSON is detected in responses, and re-runs the pipeline if validation fails.

Directory Structure
-------------------
- `Resume_inputs/` : Input resumes (.docx or .pdf)
- `Resume_inputs/base_docx_pre-conversion/` : Archived original .docx files
- `data/Processed_resumes/` : Processed resumes (PDFs)
- `data/text_output/` : LLM output text files
- `Phase 1 Workflow/Prompts/` : Prompt templates for each agent

How to Use
----------
1. Place your resume files in the `Resume_inputs` directory.
2. Ensure MongoDB is running and accessible.
3. Run this script. It will process all files in the input directory.
4. Check the output directories and MongoDB for results.

Dependencies
------------
- Python 3.x
- `docx2pdf` for file conversion
- Custom modules: `libs.gemini_processor`, `libs.mongodb`, `utils`

"""
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


import shutil
from datetime import datetime
from docx2pdf import convert
import libs.gemini_processor as gemini_processor
from libs.mongodb import save_llm_responses_to_mongodb, _get_mongo_client
from utils import get_logger
import time
from dotenv import load_dotenv
load_dotenv()

# -----------------------------
# Configuration and Directories
# -----------------------------
# LOOP_DIR: Directory containing input resumes (.docx or .pdf)
# ARCHIVE_ROOT: Where original .docx files are archived after conversion
# PROCESSED_DIR: Where processed resumes (PDFs) are moved after processing
# TEXT_OUTPUT_DIR: Where LLM output text files are saved
LOOP_DIR = "Resume_inputs"
ARCHIVE_ROOT = "Resume_inputs"
PROCESSED_DIR = "data/Processed_resumes"
TEXT_OUTPUT_DIR = "data/text_output"

# -------------------
# MongoDB Connection
# -------------------
# DB_NAME: Name of the MongoDB database
# mongo_client: MongoDB client instance for saving results
DB_NAME = "Resume_study"
mongo_client = _get_mongo_client()

# --------------
# Logging Setup
# --------------
logger = get_logger(__name__)

# -----------------------------
# Gemini Agent Initialization
# -----------------------------
# root_gemini: Handles file uploads (shared with other agents)
# gemini_resume_data: Extracts structured data from resumes
# gemini_eda: Performs Exploratory Data Analysis (EDA)
# gemini_validation: Validates the extracted and analyzed data
root_gemini = gemini_processor.GeminiProcessor(
    model_name="gemini-2.5-flash",
    temperature=0.4,
    enable_google_search=False
)

gemini_resume_data = gemini_processor.GeminiProcessor(
    model_name="gemini-2.5-flash",
    temperature=0.4,
    enable_google_search=True
)

gemini_eda = gemini_processor.GeminiProcessor(
    model_name='gemini-2.5-flash',
    temperature=0.4,
    enable_google_search=False
)

gemini_validation = gemini_processor.GeminiProcessor(
    model_name="gemini-2.5-pro",
    temperature=0.4,
    enable_google_search=False
)

MAX_RETRIES = 2

# -----------------------------------
# Utility: Move file with timestamp
# -----------------------------------
def safe_move(src, dst):
    """
    Move a file from src to dst. If dst exists, append a timestamp to avoid overwriting.
    Returns the final destination path.
    """
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        dst = f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    shutil.move(src, dst)
    return dst

# ---------------------------------------------------
# Utility: Convert .docx to PDF and archive original
# ---------------------------------------------------
def convert_to_pdf(input_path: str, archive_root: str = None) -> str:
    """
    Converts a .docx file to PDF, archives the original .docx, and returns the PDF path.
    Args:
        input_path: Path to the .docx file
        archive_root: Directory to archive the original .docx (optional)
    Returns:
        Path to the converted PDF file.
    """
    base, _ = os.path.splitext(input_path)
    pdf_path = f"{base}.pdf"
    convert(input_path, pdf_path)
    if archive_root:
        archive_dir = os.path.join(archive_root, "base_docx_pre-conversion")
        os.makedirs(archive_dir, exist_ok=True)
        archived = os.path.join(archive_dir, os.path.basename(input_path))
        safe_move(input_path, archived)
    return pdf_path

# ---------------------------------------------------
# Main Processing Flow (see docstring for overview)
# ---------------------------------------------------
if __name__ == "__main__":
    for filename in os.listdir(LOOP_DIR):
        try:
            file_path = os.path.join(LOOP_DIR, filename)
            if not os.path.isfile(file_path):
                continue

            # Step 1: Convert .docx to PDF and archive original
            if filename.lower().endswith(".docx"):
                file_path = convert_to_pdf(file_path, ARCHIVE_ROOT)
            processed_filename = os.path.basename(file_path)
            resume_data_response = None
            eda_response = None
            resume_data_retries = 0
            eda_retries = 0
            validation_retries = 0
            try:
                # Step 2: Upload file to root Gemini agent
                uploaded_file = root_gemini.upload_file(file_path)
            except Exception as e:
                logger.error(f"Failed while uploading file {filename}, ERROR: {e}")

            # Step 3: Resume Data Extraction (First Pass)
            logger.info(f'Conducting first pass for {processed_filename}')
            try:
                gemini_resume_data.load_prompt_template('Phase 1 Workflow/Prompts/prompt_std_resume_data.md')
                gemini_resume_data.uploaded_resume_file = root_gemini.uploaded_resume_file
                attempt = 0
                while attempt < MAX_RETRIES:
                    resume_data_response = gemini_resume_data.generate_content()
                    parsed = None
                    try:
                        from libs.mongodb import _clean_raw_llm_response
                        parsed = _clean_raw_llm_response(resume_data_response.text, processed_filename)
                    except Exception as e:
                        logger.error(f"Error parsing resume_data_response: {e}")
                    # Retry if invalid JSON is detected
                    if parsed and "error" in parsed and "Invalid JSON format" in parsed["error"]:
                        logger.warning(f"Invalid JSON detected in resume_data_response, retrying (attempt {attempt+1}) for {processed_filename}...")
                        attempt += 1
                        resume_data_retries = attempt
                        continue
                    break
                if resume_data_retries > 0:
                    logger.info(f"First pass for {processed_filename} required {resume_data_retries} retry(ies).")
            except Exception as e: 
                logger.error(f"Failed in first pass, file: {filename}, ERROR: {e}")

            # Step 4: EDA (Second Pass)
            logger.info(f'Conducting second pass (EDA) for {processed_filename}')
            try:
                eda_prompt = gemini_eda.load_prompt_template('Phase 1 Workflow/Prompts/prompt_std_EDA.md')
                eda_prompt = eda_prompt + "\nThe LLM Response:" + resume_data_response.text
                gemini_eda.uploaded_resume_file = root_gemini.uploaded_resume_file
                attempt = 0
                while attempt < MAX_RETRIES:
                    eda_response = gemini_eda.generate_content(prompt = eda_prompt)
                    parsed = None
                    try:
                        from libs.mongodb import _clean_raw_llm_response
                        parsed = _clean_raw_llm_response(eda_response.text, processed_filename)
                    except Exception as e:
                        logger.error(f"Error parsing eda_response: {e}")
                    # Retry if invalid JSON is detected
                    if parsed and "error" in parsed and "Invalid JSON format" in parsed["error"]:
                        logger.warning(f"Invalid JSON detected in eda_response, retrying (attempt {attempt+1}) for {processed_filename}...")
                        attempt += 1
                        eda_retries = attempt
                        continue
                    break
                if eda_retries > 0:
                    logger.info(f"Second pass (EDA) for {processed_filename} required {eda_retries} retry(ies).")
                gemini_eda.save_generated_content(response=eda_response, output_dir=TEXT_OUTPUT_DIR)
            except Exception as e:
                logger.error(f"Failed in second pass, file: {filename}, ERROR: {e}")
            
            # Step 5: Validation Agent (Third Pass)
            logger.info(f'Conducting third pass (validation agent) for {processed_filename}')
            validation_response = None
            validation_score = None
            try:
                validation_prompt = gemini_validation.load_prompt_template('Phase 1 Workflow/Prompts/prompt_std_validation.md')
                # Compose the prompt with references to both previous responses
                validation_prompt = validation_prompt + "\nResume Data Response:" + resume_data_response.text
                validation_prompt = validation_prompt + "\nEDA Response:" + eda_response.text
                gemini_validation.uploaded_resume_file = root_gemini.uploaded_resume_file
                attempt = 0
                while attempt < MAX_RETRIES:
                    validation_response = gemini_validation.generate_content(prompt=validation_prompt)
                    parsed = None
                    try:
                        from libs.mongodb import _clean_raw_llm_response
                        parsed = _clean_raw_llm_response(validation_response.text, processed_filename)
                        validation_score = parsed.get("validation_score")
                    except Exception as e:
                        logger.error(f"Error parsing validation_response: {e}")
                    # Retry if invalid JSON is detected
                    if parsed and "error" in parsed and "Invalid JSON format" in parsed["error"]:
                        logger.warning(f"Invalid JSON detected in validation_response, retrying (attempt {attempt+1}) for {processed_filename}...")
                        attempt += 1
                        validation_retries = attempt
                        continue
                    break
                if validation_retries > 0:
                    logger.info(f"Third pass (validation agent) for {processed_filename} required {validation_retries} retry(ies).")
                gemini_validation.save_generated_content(response=validation_response, output_dir=TEXT_OUTPUT_DIR)
            except Exception as e:
                logger.error(f"Failed in third pass (validation agent), file: {filename}, ERROR: {e}")

            # If validation_score is present and less than 7, re-run the extraction/EDA/validation loop (up to 2 times)
            rerun_count = 0
            MAX_RERUNS = 2
            while validation_score is not None:
                try:
                    score_val = float(validation_score)
                except Exception:
                    score_val = None
                if score_val is not None and score_val < 7 and rerun_count < MAX_RERUNS:
                    # Log validation_flags if present
                    validation_flags = None
                    if parsed and isinstance(parsed, dict):
                        validation_flags = parsed.get("validation_flags")
                    logger.warning(f"Validation score {score_val} < 7 for {processed_filename}. Validation flags: {validation_flags}")
                    rerun_count += 1
                    logger.info(f"Re-running extraction, EDA, and validation for {processed_filename} due to low validation score (attempt {rerun_count}).")
                    try:
                        # --- Extraction Agent with Retry ---
                        gemini_resume_data.load_prompt_template('Phase 1 Workflow/Prompts/prompt_std_resume_data.md')
                        gemini_resume_data.uploaded_resume_file = root_gemini.uploaded_resume_file
                        extraction_attempt = 0
                        resume_data_response = None
                        while extraction_attempt < MAX_RETRIES:
                            resume_data_response = gemini_resume_data.generate_content()
                            parsed_extraction = None
                            try:
                                from libs.mongodb import _clean_raw_llm_response
                                parsed_extraction = _clean_raw_llm_response(resume_data_response.text, processed_filename)
                            except Exception as e:
                                logger.error(f"Error parsing resume_data_response (re-run): {e}")
                            # Retry if invalid JSON or empty/missing response
                            if (parsed_extraction and "error" in parsed_extraction and "Invalid JSON format" in parsed_extraction["error"]) or not resume_data_response or not hasattr(resume_data_response, 'text') or getattr(resume_data_response, 'text', None) in (None, ""):
                                logger.warning(f"Extraction re-run: Invalid/empty response, retrying (attempt {extraction_attempt+1}) for {processed_filename}...")
                                extraction_attempt += 1
                                continue
                            break
                        if extraction_attempt > 0:
                            logger.info(f"Extraction re-run for {processed_filename} required {extraction_attempt} retry(ies).")
                        if not resume_data_response or not hasattr(resume_data_response, 'text') or getattr(resume_data_response, 'text', None) in (None, ""):
                            logger.error(f"Extraction re-run failed for {processed_filename}: No response or missing text after retries. Will retry re-run loop if attempts remain.")
                            continue
                        logger.info(f"Extraction re-run complete for {processed_filename}.");

                        # --- EDA Agent with Retry ---
                        eda_prompt = gemini_eda.load_prompt_template('Phase 1 Workflow/Prompts/prompt_std_EDA.md')
                        eda_prompt = eda_prompt + "\nThe LLM Response:" + resume_data_response.text
                        gemini_eda.uploaded_resume_file = root_gemini.uploaded_resume_file
                        eda_attempt = 0
                        eda_response = None
                        while eda_attempt < MAX_RETRIES:
                            eda_response = gemini_eda.generate_content(prompt=eda_prompt)
                            parsed_eda = None
                            try:
                                from libs.mongodb import _clean_raw_llm_response
                                parsed_eda = _clean_raw_llm_response(eda_response.text, processed_filename)
                            except Exception as e:
                                logger.error(f"Error parsing eda_response (re-run): {e}")
                            if (parsed_eda and "error" in parsed_eda and "Invalid JSON format" in parsed_eda["error"]) or not eda_response or not hasattr(eda_response, 'text') or getattr(eda_response, 'text', None) in (None, ""):
                                logger.warning(f"EDA re-run: Invalid/empty response, retrying (attempt {eda_attempt+1}) for {processed_filename}...")
                                eda_attempt += 1
                                continue
                            break
                        if eda_attempt > 0:
                            logger.info(f"EDA re-run for {processed_filename} required {eda_attempt} retry(ies).")
                        if not eda_response or not hasattr(eda_response, 'text') or getattr(eda_response, 'text', None) in (None, ""):
                            logger.error(f"EDA re-run failed for {processed_filename}: No response or missing text after retries. Will retry re-run loop if attempts remain.")
                            continue
                        logger.info(f"EDA re-run complete for {processed_filename}.");

                        # --- Validation Agent with Retry ---
                        validation_prompt = gemini_validation.load_prompt_template('Phase 1 Workflow/Prompts/prompt_std_validation.md')
                        validation_prompt = validation_prompt + "\nResume Data Response:" + resume_data_response.text
                        validation_prompt = validation_prompt + "\nEDA Response:" + eda_response.text
                        gemini_validation.uploaded_resume_file = root_gemini.uploaded_resume_file
                        validation_attempt = 0
                        validation_response = None
                        while validation_attempt < MAX_RETRIES:
                            validation_response = gemini_validation.generate_content(prompt=validation_prompt)
                            parsed_validation = None
                            try:
                                from libs.mongodb import _clean_raw_llm_response
                                parsed_validation = _clean_raw_llm_response(validation_response.text, processed_filename)
                                validation_score = parsed_validation.get("validation_score")
                                validation_flags = parsed_validation.get("validation_flags")
                            except Exception as e:
                                logger.error(f"Error parsing validation_response (re-run): {e}")
                            if (parsed_validation and "error" in parsed_validation and "Invalid JSON format" in parsed_validation["error"]) or not validation_response or not hasattr(validation_response, 'text') or getattr(validation_response, 'text', None) in (None, ""):
                                logger.warning(f"Validation re-run: Invalid/empty response, retrying (attempt {validation_attempt+1}) for {processed_filename}...")
                                validation_attempt += 1
                                continue
                            break
                        if validation_attempt > 0:
                            logger.info(f"Validation re-run for {processed_filename} required {validation_attempt} retry(ies).")
                        if not validation_response or not hasattr(validation_response, 'text') or getattr(validation_response, 'text', None) in (None, ""):
                            logger.error(f"Validation re-run failed for {processed_filename}: No response or missing text after retries. Will retry re-run loop if attempts remain.")
                            continue
                        gemini_validation.save_generated_content(response=validation_response, output_dir=TEXT_OUTPUT_DIR)
                        logger.info(f"Validation re-run complete for {processed_filename}.")
                        # Update validation_score and validation_flags for next check
                        try:
                            from libs.mongodb import _clean_raw_llm_response
                            parsed = _clean_raw_llm_response(validation_response.text, processed_filename)
                            validation_score = parsed.get("validation_score")
                            validation_flags = parsed.get("validation_flags")
                        except Exception as e:
                            logger.error(f"Error parsing validation_response after re-run: {e}")
                            continue
                    except Exception as e:
                        logger.error(f"Error during re-run for low validation score for {processed_filename}: {e}")
                        continue
                else:
                    break
                

        except Exception as e:
            logger.exception(f'Error processing file {filename}: {e}', exc_info=True)

        # Step 6: Save all LLM responses to MongoDB (if available)
        llm_responses_dict = {}
        if resume_data_response is not None:
            llm_responses_dict["resume_data"] = resume_data_response
        if eda_response is not None:
            llm_responses_dict["EDA"] = eda_response
        if validation_response is not None:
            llm_responses_dict["validation"] = validation_response

        if llm_responses_dict:
            try:
                save_llm_responses_to_mongodb(
                    llm_responses_dict,
                    db_name=DB_NAME,
                    collection_name="Standardized_resume_data",
                    file_path=file_path,
                    mongo_client=mongo_client,
                )
            except Exception as e:
                logger.error(f"Error saving to MongoDB for {processed_filename}: {e}")
                # If saving fails, log raw LLM responses for debugging
                raw_log_dir = os.path.join(TEXT_OUTPUT_DIR, "raw_failed_llm_responses")
                os.makedirs(raw_log_dir, exist_ok=True)
                if resume_data_response is not None and hasattr(resume_data_response, 'text'):
                    with open(os.path.join(raw_log_dir, f"{processed_filename}_resume_data_raw.txt"), "w", encoding="utf-8") as f:
                        f.write(resume_data_response.text)
                if eda_response is not None and hasattr(eda_response, 'text'):
                    with open(os.path.join(raw_log_dir, f"{processed_filename}_eda_raw.txt"), "w", encoding="utf-8") as f:
                        f.write(eda_response.text)
        
        # Step 7: Cleanup - delete uploaded file and move processed file
        root_gemini.delete_uploaded_file()
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        dest_path = safe_move(file_path, os.path.join(PROCESSED_DIR, processed_filename))
        logger.info(f"File successfully processed: {processed_filename}")
