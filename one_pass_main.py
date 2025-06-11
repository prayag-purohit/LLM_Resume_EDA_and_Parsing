import os
import shutil
from datetime import datetime
from docx2pdf import convert
import PYTHON_MODULES.gemini_processor as gemini_processor
from PYTHON_MODULES.mongodb import save_document_from_template, _get_mongo_client, _parse_llm_text_to_dict
import hashlib
from dotenv import load_dotenv
import PYTHON_MODULES.utils as utils
import json

logger = utils.get_logger(__name__)
load_dotenv()

gemini = gemini_processor.GeminiProcessor(
    model_name="gemini-2.0-flash",
    temperature=0.4,
    api_key=os.getenv("GEMINI_API_KEY"),
    enable_google_search=True
)

def safe_move(src, dst):
    if os.path.exists(dst):
        base, ext = os.path.splitext(dst)
        dst = f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    shutil.move(src, dst)
    return dst

def loop_local_files(
    loop_dir: str = "Resume_inputs",
    prompt_path: str = "prompt_engineering_parsing.md",
    schema_path: str = "mongo_schema.json",
    collection_name: str = "JSON_raw",
    db_name: str = "Resume_study"
):
    """
    Loops through local files, runs a two-pass (flag, then EDA) process,
    and saves the combined result to MongoDB using a schema template.
    """
    mongo_client = _get_mongo_client(Prod=False)
    if not mongo_client:
        logger.error("Could not connect to MongoDB. Aborting process.")
        return

    # --- 1. Load All Configurations Outside the Loop ---
    try:
        prompt = gemini.load_prompt_template(prompt_path)
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_template = json.load(f)
        logger.info("Successfully loaded all prompts and schema template.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Failed to load configuration files. Aborting. Error: {e}")
        return

    for filename in os.listdir(loop_dir):
        processed_file_path = None
        try:
            original_file_path = os.path.join(loop_dir, filename)
            if not os.path.isfile(original_file_path):
                continue

            # --- 2. Handle File Conversion ---
            if filename.lower().endswith(".docx"):
                pdf_file_path = os.path.splitext(original_file_path)[0] + ".pdf"
                logger.info(f"Converting {filename} to PDF...")
                convert(original_file_path, pdf_file_path)

                archive_dir = os.path.join(loop_dir, "base_docx_pre-conversion")
                os.makedirs(archive_dir, exist_ok=True)
                safe_move(original_file_path, os.path.join(archive_dir, filename))

                processed_file_path = pdf_file_path
                processed_filename = os.path.basename(pdf_file_path)
            else:
                processed_file_path = original_file_path
                processed_filename = filename

            logger.info(f"Processing: {processed_filename}")

            # --- 3. Orchestrate API Calls ---
            gemini.upload_file(processed_file_path)

            models_data = []
            # Giving data to model
            logger.info("Running the model with given prompt")

            response = gemini.generate_content(prompt=prompt)
            data = _parse_llm_text_to_dict(response.text, gemini.file_name)

            models_data.append({
                "model_type" : "Cleaning flagger",
                "model_name": gemini.model_name,
                "usage_tokens": response.usage_metadata.total_token_count
            })


            # --- 4. Move Processed File and Prepare Data ---
            processed_dir = "Processed_resumes"
            os.makedirs(processed_dir, exist_ok=True)
            dest_path = safe_move(processed_file_path, os.path.join(processed_dir, processed_filename))
            processed_file_path = None # Set to None to prevent re-deletion in finally block

            with open(dest_path, "rb") as f_bytes:
                raw_file_bytes = f_bytes.read()

            

            # --- 5. Consolidate All Data Sources for the Template ---
            data_sources = {
                "file_id": gemini.file_name,
                "file_size_bytes": len(raw_file_bytes),
                "file_hash": hashlib.sha256(raw_file_bytes).hexdigest(),
                "industry_prefix": gemini.industry_prefix,
                "eda_data": data,
                "models_data": models_data,  # List of model info
                "timestamp": datetime.now().isoformat()  # ISO format for JSON/MongoDB
            }

            # --- 6. Save to MongoDB Using the Generic Function ---
            save_document_from_template(
                schema_template=schema_template,
                data_sources=data_sources,
                db_name=db_name,
                collection_name=collection_name,
                mongo_client=mongo_client
            )

        except Exception as e:
            logger.error(f"An error occurred while processing {filename}: {e}", exc_info=True)
            # If the file was moved before the error, we don't want to try moving it again
            if processed_file_path and os.path.exists(processed_file_path):
                 error_dir = "Error_files"
                 os.makedirs(error_dir, exist_ok=True)
                 safe_move(processed_file_path, os.path.join(error_dir, os.path.basename(processed_file_path)))

        finally:
            # --- 7. Cleanup ---
            if gemini.uploaded_resume_file:
                gemini.delete_uploaded_file()

    if mongo_client:
        mongo_client.close()
        logger.info("Closed MongoDB connection.")

if __name__ == "__main__":
    loop_local_files(
        loop_dir = "Resume_inputs",
        flag_prompt_path = "Prompt_templates\prompt_engineering_flagforcleaning.md",
        eda_prompt_path = "Prompt_templates\prompt_engineering_eda.md",
        schema_path = "MONGO_SCHEMA\mongo_schema_single_pass.json",
        collection_name = "EDA_devtest",
        db_name = "Testing"
    )
