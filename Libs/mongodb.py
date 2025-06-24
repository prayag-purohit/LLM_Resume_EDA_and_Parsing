import os
import json
from pymongo import MongoClient
from datetime import datetime
import hashlib
from dotenv import load_dotenv
import sys 
sys.path.append('.')
from utils import get_logger

logger = get_logger(__name__)

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

def _clean_raw_llm_response(llm_raw_text):
    llm_raw_text_clean = llm_raw_text.strip()
    if llm_raw_text_clean.startswith("```json"):
        llm_raw_text_clean = llm_raw_text_clean[len("```json"):].strip()
    if llm_raw_text_clean.startswith("```"):
        llm_raw_text_clean = llm_raw_text_clean[len("```"):].strip()
    if llm_raw_text_clean.endswith("```"):
        llm_raw_text_clean = llm_raw_text_clean[:-3].strip()
    
    try:
        llm_raw_text_dict = json.loads(llm_raw_text_clean)
        return llm_raw_text_dict

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON for {file_name}: {e}")
        logger.debug(f"Problematic JSON string: {llm_raw_text_clean}")
    # Decide how to handle: skip saving, save raw text in an error field, or raise
        return ValueError(f"Invalid JSON format in LLM response for {file_name}. Please check the response format.")


# === Save to MongoDB ===

def save_single_LLM_response_to_mongodb(
                    llm_response, 
                    db_name="Resume_study", 
                    collection_name="EDA_data",
                    file_path="HRC resume 10.pdf", #Default file for testing
                    mongo_client= None, # Provide a mongo_client if running inside a loop
):
    """
    Save the LLM response to MongoDB.

    Args:
        llm_raw_text (str): The raw text response from the LLM.
        llm_response: The LLM response object.
        db_name (str): The MongoDB database name.
        collection_name (str): The MongoDB collection name.
        file_path (str): The path to the resume file being processed.
        mongo_client: Provide a mongo_client if running inside a loop
    """
    
    with open(file_path, "rb") as f:
        raw_file_bytes = f.read()

    file_name = os.path.basename(file_path)
    industry_prefix = file_name.split(' ')[0]
    llm_raw_text = llm_response.text
    
    llm_raw_text_dict = _clean_raw_llm_response(llm_raw_text=llm_raw_text)
    
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
            "industry_prefix": industry_prefix,
            "file_size_bytes": len(raw_file_bytes),
            "file_hash": hashlib.sha256(raw_file_bytes).hexdigest(),

            **llm_raw_text_dict,

            # 3)LLM metadata
            "model_name": llm_response.modelVersion,
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

def save_llm_responses_to_mongodb(
    *llm_responses,
    db_name="Resume_study",
    collection_name="EDA_data",
    file_path="HRC resume 10.pdf",
    mongo_client: MongoClient = None,
):
    """
    Saves one or more LLM responses related to a single file to MongoDB.

    This function aggregates text content and sums the usage metadata from all
    provided response objects into a single database record.

    Args:
        *llm_responses: A variable number of LLM response objects to process.
        db_name (str): The MongoDB database name.
        collection_name (str): The MongoDB collection name.
        file_path (str): The path to the file being processed.
        mongo_client: An active pymongo.MongoClient instance. If None, a new
                      connection is created and closed automatically.
    """
    # --- 1. Input Validation ---
    if not llm_responses:
        logger.warning("No LLM responses provided. Nothing to save.")
        return

    # --- 2. File Metadata Extraction ---
    try:
        with open(file_path, "rb") as f:
            raw_file_bytes = f.read()
        file_name = os.path.basename(file_path)
        industry_prefix = file_name.split(' ')[0]
    except FileNotFoundError:
        logger.error(f"File not found at path: {file_path}")
        return

    # --- 3. Aggregate Data from all LLM Responses ---
    combined_text_dict = {}
    model_names = set()
    
    # Initialize total usage with all potential keys
    aggregated_usage = {
        "prompt_token_count": 0,
        "thoughts_token_count": 0,
        "total_token_count": 0,
        # Details are lists, so we initialize them as empty lists to extend
        "prompt_tokens_details": [],
        "tool_use_prompt_tokens_details": [],
    }

    for response in llm_responses:
        # a) Combine cleaned text dictionaries
        if hasattr(response, 'text'):
            llm_raw_text_dict = _clean_raw_llm_response(llm_raw_text=response.text)
            combined_text_dict.update(llm_raw_text_dict)

        # b) Collect unique model names
        if hasattr(response, 'modelVersion'):
            model_names.add(response.modelVersion)
            
        # c) Sum usage metadata
        if hasattr(response, 'usage_metadata'):
            usage_data = response.usage_metadata.model_dump()
            aggregated_usage["prompt_token_count"] += usage_data.get("prompt_token_count", 0)
            aggregated_usage["thoughts_token_count"] += usage_data.get("thoughts_token_count", 0)
            aggregated_usage["total_token_count"] += usage_data.get("total_token_count", 0)
            
            if usage_data.get("prompt_tokens_details"):
                aggregated_usage["prompt_tokens_details"].extend(usage_data["prompt_tokens_details"])
            if usage_data.get("tool_use_prompt_tokens_details"):
                aggregated_usage["tool_use_prompt_tokens_details"].extend(usage_data["tool_use_prompt_tokens_details"])


    # --- 4. MongoDB Connection Handling ---
    if mongo_client is None:
        mongo_client = _get_mongo_client()
        close_client = True
    else:
        close_client = False

    if not mongo_client:
        logging.error("Cannot save to MongoDB: Client not available.")
        return

    # --- 5. Document Creation and Insertion ---
    try:
        db = mongo_client[db_name]
        collection = db[collection_name]

        doc = {
            # a) Primary key and file metadata
            "file_id": file_name,
            "industry_prefix": industry_prefix,
            "file_size_bytes": len(raw_file_bytes),
            "file_hash": hashlib.sha256(raw_file_bytes).hexdigest(),

            # b) Unpacked data from all combined LLM responses
            **combined_text_dict,

            # c) Aggregated LLM metadata
            "model_names": list(model_names), # Store a list of unique model names
            "num_responses_aggregated": len(llm_responses), # New metadata field
            "usage_tokens": aggregated_usage, # The fully summed usage
            "timestamp": datetime.now(),
        }
        collection.insert_one(doc)
        logger.info(f"Successfully saved aggregated data for {file_name} to MongoDB.")

    except Exception as e:
        logger.error(f"MongoDB Error during save: {e}")
    finally:
        if close_client and mongo_client:
            mongo_client.close()
            logger.info("Closed MongoDB connection")



# === Retrieve from MongoDB ===

def get_all_file_ids(db_name: str, 
                     collection_name: str, 
                     mongo_client=None) -> list:
    """
    Retrieve all file_id values from a MongoDB collection.

    Args:
        db_name (str): The MongoDB database name.
        collection_name (str): The MongoDB collection name.
        mongo_client: Optional existing MongoDB client.

    Returns:
        List of file_id values.
    """
    if mongo_client is None:
        mongo_client = _get_mongo_client()
        close_client = True
    else:
        close_client = False

    if not mongo_client:
        logger.error("Cannot retrieve file_ids: MongoDB client not available.")
        return []

    try:
        db = mongo_client[db_name]
        collection = db[collection_name]
        cursor = collection.find({}, {"file_id": 1, "_id": 0})  # Only retrieve file_id fields
        file_ids = [doc["file_id"] for doc in cursor if "file_id" in doc]
        logger.info(f"Retrieved {len(file_ids)} file_id(s) from MongoDB.")
        return file_ids
    except Exception as e:
        logger.error(f"MongoDB Error during file_id retrieval: {e}")
        return []
    finally:
        if close_client and mongo_client:
            mongo_client.close()
            logger.info("Closed MongoDB connection")

def get_document_by_fileid(db_name:str, 
                 collection_name:str, 
                 file_id:str, 
                 mongo_client=None):
    """
    Retrieve a document from MongoDB by file_id.
    
    Args:
        db (str): The database name.
        collection (str): The collection name.
        file_id (str): The file_id to search for.
        mongo_client: Provide a mongo_client if running inside a loop
    """
    if mongo_client is None:
        mongo_client = _get_mongo_client()
        close_client = True
    else:
        close_client = False

    if not mongo_client:
        logger.error("Cannot retrieve from MongoDB: Client not available.")
        return None

    try:
        db = mongo_client[db_name]
        collection = db[collection_name]
        document = collection.find_one({"file_id": file_id})
        return document
    except Exception as e:
        logger.error(f"MongoDB Error during retrieval: {e}")
    finally:
        if close_client and mongo_client:
            mongo_client.close()
            logger.info("Closed MongoDB connection")


#Testing
if __name__ == "__main__":
    mongo_client = _get_mongo_client()
