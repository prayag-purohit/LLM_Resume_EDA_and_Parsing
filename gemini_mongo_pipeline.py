import os
import json
import re
import pandas as pd
from pymongo import MongoClient
from datetime import datetime
from google import genai # New recommended import for the core library
from google.genai import types # New recommended import for specific types like Tool, GenerationConfig
import hashlib
from dotenv import load_dotenv
import logging

# Set up logging
# Ensure logs directory exists
os.makedirs("logs", exist_ok=True)
os.makedirs("logs/Errors", exist_ok=True)
# Create a log file name that includes 'error' if any error occurs during runtime.
# However, logging.basicConfig does not support dynamic renaming of log files after creation.
# The log file name is set at startup and cannot be changed on error.
# To separate error logs, use a separate FileHandler for errors.

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
general_log = os.path.join("logs", f"resume_parser{ts}.log")
error_log   = os.path.join("logs", "Errors", f"error_resume_parser{ts}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(general_log, mode="a"),
        logging.StreamHandler(),
    ]
)

# 4) Now add a second FileHandler for ERROR+ only:
err_handler = logging.FileHandler(error_log, mode="a")
err_handler.setLevel(logging.ERROR)
err_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

logging.getLogger().addHandler(err_handler)

logger = logging.getLogger(__name__)


load_dotenv()


# === Setup ===

def _get_mongo_client():
    mongo_uri = os.getenv("MONGODB_URI")
    logger.info(f"MongoDB URI: {mongo_uri}")
    if not mongo_uri:
        logger.error("Error: MongoDB URI is required (MONGO_URI environment variable).")
        return None
    try:
        mongo_client = MongoClient(mongo_uri)
        # You might want to test the connection here, e.g., by listing databases
        mongo_client.admin.command('ping')
        logger.info("Successfully connected to MongoDB.")
        return mongo_client
    except Exception as e:
        logger.error(f"Error connecting to MongoDB: {e}")
        return None   

def _load_prompt_template(file_path="prompt_engineering_eda.md"):
    """Load a prompt template from md file. The prompt should be enclosed between triple backticks."""
    prompt_path = file_path
    try:
        with open(prompt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Extract the prompt template between triple backticks
        prompt_match = re.search(r'```\n(.*?)\n```', content, re.DOTALL)
        if prompt_match:
            logger.info(f"Successfully loaded prompt template from {prompt_path}")
            return prompt_match.group(1)
        else:
            logger.error(f"Could not find prompt template (between ```) in {prompt_path}")
            return None
    except FileNotFoundError:
        logger.error(f"Prompt template file not found: {prompt_path}")
        return None
    except Exception as e:
        logger.error(f"Error loading prompt template: {e}")
        return None

# === Function to parse the resume using Gemini ===

def _process_with_gemini(prompt_file_path: str, file_path: str, model_name: str, temperature: float, google_search_tool: bool):
    """
    Process a file with the Gemini API and return the response.
    
    Args:
        prompt_file_path (str): The path to the prompt template file.
        file_path (str): The path to the resume file to be analyzed.
        model_name (str): The name of the Gemini model to use.
        temperature (float): The temperature setting for content generation.
        google_search_tool (bool): Whether to enable the Google Search tool.
    """

    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return None

    API_KEY = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=API_KEY)
    
    
    try:
        resume_document = client.files.upload(file=file_path)
        logger.info(f"Successfully uploaded file: {resume_document.name} - {resume_document.display_name}")
    except Exception as e:
        logger.error(f"Error uploading file {file_path}: {e}")
        return None
    
    tools = []
    if google_search_tool:
        tools.append(types.Tool(google_search=types.GoogleSearch()))

    
    PROMPT_TEMPLATE = _load_prompt_template(prompt_file_path)
    if not PROMPT_TEMPLATE:
        logger.error("Failed to load prompt template. Aborting analysis.")
        raise ValueError("Prompt template file is required for analysis. Make sure the file exists and the core prompt is enclosed between ```")
    
    prompt = PROMPT_TEMPLATE
    response = None
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt, resume_document],
            config=types.GenerateContentConfig(
                temperature=temperature,
                tools=tools
                )
        )
        if response.text:
            logger.info("Content generation successful.")
            # Save raw response to file for debugging
            try:
                os.makedirs("text_output", exist_ok=True)
                timestamp_str = datetime.now().strftime("%d-%m-%y_%H-%M")
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                output_filename = f"{base_name}_{timestamp_str}.txt"
                output_path = os.path.join("text_output", output_filename)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(response.text)
            except Exception as e_write:
                logger.error(f"Error writing raw response to file: {e_write}")
            return response
        else:
            logger.error("Gemini returned no text.")
            return None
    except Exception as e:
        logger.error(f"Error during Gemini content generation: {e}")
        if hasattr(response, 'promptFeedback') and response.promptFeedback:
            logger.error(f"Prompt Feedback: {response.promptFeedback}")
            if hasattr(response, 'promptFeedback') and hasattr(response.promptFeedback, 'blockReason') and response.promptFeedback.blockReason:
                logger.error(f"Block Reason: {response.promptFeedback.blockReason}")
        # Clean up uploaded file if generation fails and file exists
        return None
    
    finally:
        # Additional cleanup to ensure file is deleted even on success
        if resume_document:
            try:
                client.files.delete(name=resume_document.name)
                logger.info(f"Deleted uploaded file: {resume_document.name}")
            except Exception as e:
                logger.error(f"Error deleting uploaded file {resume_document.name}: {e}")


# === Save to MongoDB ===

def _save_to_mongodb(llm_raw_text,
                    llm_response, 
                    file_name,
                    db_name="Resume_study", 
                    collection_name="EDA_data",
                    file_path="HRC resume 10.pdf", #Default file for testing
                    mongo_client= None,
                    model_name=None):
    """
    Save the LLM response to MongoDB.

    Args:
        llm_raw_text (str): The raw text response from the LLM.
        llm_response: The LLM response object.
        file_name (str): The name of the file being processed.
        db_name (str): The MongoDB database name.
        collection_name (str): The MongoDB collection name.
        file_path (str): The path to the resume file being processed.
        mongo_client: Provide a mongo_client if running inside a loop
    """
    
    with open(file_path, "rb") as f:
        raw_file_bytes = f.read()
    
    llm_raw_text_clean = llm_raw_text.strip()
    if llm_raw_text_clean.startswith("```json"):
        llm_raw_text_clean = llm_raw_text_clean[len("```json"):].strip()
    if llm_raw_text_clean.startswith("```"):
        llm_raw_text_clean = llm_raw_text_clean[len("```"):].strip()
    if llm_raw_text_clean.endswith("```"):
        llm_raw_text_clean = llm_raw_text_clean[:-3].strip()
    
    try:
        llm_raw_text_dict = json.loads(llm_raw_text_clean)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON for {file_name}: {e}")
        logger.debug(f"Problematic JSON string: {llm_raw_text_clean}")
    # Decide how to handle: skip saving, save raw text in an error field, or raise
        return ValueError(f"Invalid JSON format in LLM response for {file_name}. Please check the response format.")
    
    if mongo_client is None:
        mongo_client = _get_mongo_client()
        close_client = True
    else:
        close_client = False
         # Corrected: added ()

    if not mongo_client:
        logger.error("Cannot save to MongoDB: Client not available.")
        return

    try:
        db = mongo_client[db_name]
        collection = db[collection_name]
        # Add a timestamp for when the record was created
        #collection.create_index("_id", unique=True)

        doc = {
            # 1)Primary key
            "file_id": file_name,
            # 2)File metadata
            "file_size_bytes": len(raw_file_bytes),
            "file_hash": hashlib.sha256(raw_file_bytes).hexdigest(),

            **llm_raw_text_dict,

            # 3)LLM metadata
            "model_name": model_name,
            "usage_tokens": llm_response.usage_metadata.model_dump(
	            include={
		            "prompt_token_count",
                    "prompt_tokens_details",
                    "thoughts_token_count",
                    "tool_use_prompt_tokens_details",
                    "total_token_count"}),
            
            "timestamp": datetime.now(),
        }
        collection.insert_one(doc)
        logger.info(f"Successfully saved data to MongoDB: {file_name}")

    except Exception as e:
        logger.error(f"MongoDB Error during save: {e}")
    finally:
        if close_client and mongo_client:
            mongo_client.close()
            logger.info("Closed MongoDB connection")



# === Wrapper function ===
def gemini_pipeline(prompt_file_path: str,
                    file_path: str = "HRC resume 10.pdf",
                    mongo_collection: str = None,
                    mongo_db: str = None,
                    google_search_tool: bool = False,
                    think_tool: bool = False,
                    model_name: str = "gemini-1.5-flash",
                    temperature: float = 0.4,
                    loop: bool = False
                    ):
    """
    This function is a wrapper for the Gemini pipeline.
    It processes a file using the Gemini API and optionally saves the results to MongoDB.

    Args:
        prompt_file_path (str): The path to the prompt template file.
        file_path (str): The path to the resume file to be analyzed.
        mongo_collection (str, optional): The MongoDB collection name to save the results.
        mongo_db (str, optional): The MongoDB database name to save the results.
        google_search_tool (bool): Whether to enable the Google Search tool.
        think_tool (bool): Whether to enable the Think tool.
        model_name (str): The name of the Gemini model to use.
        temperature (float): The temperature setting for content generation.
    """
    response = _process_with_gemini(prompt_file_path, file_path, model_name, temperature, google_search_tool)
    # 
    if loop:
        mongo_client = _get_mongo_client()
    else:
        mongo_client = None
    if response and mongo_collection and mongo_db:
        _save_to_mongodb(response.text, response, file_name=os.path.basename(file_path), db_name=mongo_db,model_name=model_name ,collection_name=mongo_collection, file_path=file_path, mongo_client=mongo_client)
    return response