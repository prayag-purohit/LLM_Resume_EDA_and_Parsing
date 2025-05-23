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

# Create a log file name that includes 'error' if any error occurs during runtime.
# However, logging.basicConfig does not support dynamic renaming of log files after creation.
# The log file name is set at startup and cannot be changed on error.
# To separate error logs, use a separate FileHandler for errors.

log_file_base = f"resume_parser{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
log_file_path = os.path.join("logs", log_file_base)
error_log_file_path = os.path.join("logs", f"resume_parser_error{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler(),
        logging.FileHandler(error_log_file_path, mode='a')
    ]
)

# Set error handler to only log errors and above
for handler in logging.getLogger().handlers:
    if isinstance(handler, logging.FileHandler) and handler.baseFilename == error_log_file_path:
        handler.setLevel(logging.ERROR)

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

def gemini_pipeline(prompt_file_path: str,
                    file_path="HRC resume 10.pdf",
                    google_search_tool: bool = False,
                    think_tool: bool = False,
                    model_name: str = "gemini-1.5-flash",
                    temperature: float = 0.4,
                    ):
    """
    This function is a wrapper for the Gemini pipeline.
    It initializes the Gemini client, loads a prompt template *file*,
    It has an option to upload a resume file, and enabling the Google Search tool.
    sends a request to the Gemini model for content generation.
    Saves logs, and stores text outputs in a dir

    Args:
        prompt_file_path (str/file_path): The prompt template file to use for the analysis. the prompt should be encolsed between "```"
        file_path (str): The path to the resume file to be analyzed.
        google_search_tool (bool): Whether to enable the Google Search tool.
        think_tool (bool): Whether to enable the Think tool.
        model_name (str): The name of the Gemini model to use.
        temperature (float): The temperature setting for content generation.
    """
    #model = _Gemini_init() # This didn't work lol
    load_dotenv()
    API_KEY = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=API_KEY)
    # Upload a resume file to Gemini

    if not os.path.exists(file_path):
        logger.error(f"Resume file not found: {file_path}")
        return None
    logger.info(f"Attempting to upload file: {file_path}")
    resume_document = client.files.upload(file=file_path)
    logger.info(f"Successfully uploaded file: {resume_document.name} - {resume_document.display_name}")

    # Initialize the Google GenAI client

    tools = []
    if google_search_tool:
        google_search_tool = types.Tool(google_search=types.GoogleSearch())
        tools.append(google_search_tool)
    if think_tool:
        think_tool = types.Tool(think=types.Think())
        tools.append(think_tool)

    # Initialize the prompt template
    PROMPT_TEMPLATE = _load_prompt_template(prompt_file_path)
    if not PROMPT_TEMPLATE:
        logger.error("Failed to load prompt template. Aborting analysis.")
        raise ValueError("Prompt template file is required for analysis. Make sure the file exists and the core prompt is enclosed between ```")
    prompt = PROMPT_TEMPLATE
    

    # Sending request to Gemini
    logger.info("Sending request to Gemini for content generation...")
    raw_text = None
    try:
    # Adding caching mechanism here would be beneficial, i.e. using the cached prompt, and getting new document
        response = client.models.generate_content(
            model=model_name, 
            contents=[prompt, resume_document],
            tools=tools,
            config=types.GenerateContentConfig(
                temperature=0.4, 
                ))
        
        raw_text = response.text
        logger.info("Content generation successful.")

        if raw_text is None:
            logger.error("Gemini returned no text.")
            # Clean up uploaded file
        if resume_document:
            try:
                genai.delete_file(resume_document.name)
                logger.info(f"Cleaned up uploaded file: {resume_document.name}")
            except Exception as del_e:
                logger.error(f"Error deleting uploaded file {resume_document.name}: {del_e}")
            return None
        
        # Delete file after processed to save space on cloud
        client.files.delete(name=resume_document.name)
        logger.info(f"SUCCESSS: Deleted uploaded file: {resume_document.name}")
        logger.info("Returning response")
        return response
    
    except Exception as e:
        logger.error(f"Error during Gemini content generation: {e}")
        if hasattr(response, 'promptFeedback') and response.promptFeedback:
            logger.error(f"Prompt Feedback: {response.promptFeedback}")
            if hasattr(response, 'promptFeedback') and hasattr(response.promptFeedback, 'blockReason') and response.promptFeedback.blockReason:
                logger.error(f"Block Reason: {response.promptFeedback.blockReason}")
        # Clean up uploaded file if generation fails and file exists
        if resume_document:
            try:
                client.files.delete(name=resume_document.name)
                logger.info(f"Cleaned up uploaded file: {resume_document.name}")
            except Exception as del_e:
                logger.error(f"Error deleting uploaded file {resume_document.name}: {del_e}")
        return None

    finally:
        logger.info("Gemini raw response received. Saving to resume_parser_output.txt for debugging.")
        try:
            # Ensure text_output directory exists
            os.makedirs("text_output", exist_ok=True)
            # Format timestamp as dd-mm-yy_HH-MM
            timestamp_str = datetime.now().strftime("%d-%m-%y_%H-%M")
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_filename = f"{base_name}_{timestamp_str}.txt"
            output_path = os.path.join("text_output", output_filename)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(raw_text)
        except Exception as e_write:
            logger.error(f"Error writing raw response to file: {e_write}")


# === Save to MongoDB ===

def save_to_mongodb(llm_raw_text,
                    llm_response, 
                    file_name: str,
                    db_name="Resume_study", 
                    collection_name="EDA_data",
                    file_path="HRC resume 10.pdf"
                    mongo_client = None,
                    ):
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
    llm_raw_text_dict = json.loads(llm_raw_text_clean)
    
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
            "model_name": llm_response.model_version,
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

