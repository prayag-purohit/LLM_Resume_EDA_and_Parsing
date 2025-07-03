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
    logger.info(f"MongoDB URI:{mongo_uri}")
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

def _clean_raw_llm_response(llm_raw_text, file_name=None):
    """
    Clean and parse the raw LLM response text as JSON.
    Args:
        llm_raw_text (str): The raw text response from the LLM.
        file_name (str, optional): The name of the file being processed (for logging).
    Returns:
        dict: Parsed JSON if successful, or a dict with error info if JSON is invalid.
    """
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
        logger.error(f"Failed to parse LLM response as JSON for {file_name}: {e}\nModel response: {llm_raw_text_clean[:5000]}")
        logger.debug(f"Problematic JSON string: {llm_raw_text_clean}")
        # Return a serializable error dict instead of ValueError
        return {
            "error": f"Invalid JSON format in LLM response for {file_name}.",
            "exception": str(e),
            "raw_text": llm_raw_text_clean[:5000]  # Optionally truncate for storage
        }


# === Save to MongoDB ===
# Deprecated: This function is kept for backward compatibility, but prefer using `save_llm_responses_to_mongodb` for multiple responses.
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
    
    llm_raw_text_dict = _clean_raw_llm_response(llm_raw_text=llm_raw_text, file_name=file_name)
    
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

def save_llm_responses_to_mongodb(
    responses_by_agent: dict[str, any],
    *,
    db_name: str = "Resume_study",
    collection_name: str = "EDA_data",
    file_path: str,
    mongo_client: MongoClient | None = None,
):
    """
    Persist one or more LLM agent outputs—each under a distinct key—to MongoDB.

    Args:
        responses_by_agent: 
            A dict mapping agent names → genai SDK response objects.
            e.g. {"EDA": resp1, "Standardized_Raw": resp2, ...}
        db_name:        target database
        collection_name:target collection
        file_path:      path to the original PDF/DOCX
        mongo_client:   if provided, reuse it; otherwise we open/close our own.
    """
    if not responses_by_agent:
        logger.warning("No agent responses provided. Aborting save.")
        return

    # --- 1. Read file bytes & metadata ---
    try:
        raw = open(file_path, "rb").read()
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return

    file_name = os.path.basename(file_path)
    industry_prefix = file_name.split(" ")[0]
    file_hash = hashlib.sha256(raw).hexdigest()

    # --- 2. Prepare aggregators ---
    model_names = set()
    usage_agg = {
        "prompt_token_count": 0,
        "thoughts_token_count": 0,
        "total_token_count": 0,
    }
    usage_by_agent = {}
    cleaned_by_agent: dict[str, dict] = {}

    def safe_int(val):
        return int(val) if val is not None else 0

    # --- 3. Clean each agent’s output & aggregate metadata ---
    for agent_name, resp in responses_by_agent.items():
        # a) clean text
        if hasattr(resp, "text"):
            cleaned = _clean_raw_llm_response(llm_raw_text=resp.text, file_name=file_name)
            cleaned_by_agent[agent_name] = cleaned
        else:
            cleaned_by_agent[agent_name] = {}

        # b) collect modelVersion
        if hasattr(resp, "model_version"):
            model_names.add(resp.model_version)

        # c) sum usage metadata and store per-agent usage (filtered)
        if hasattr(resp, "usage_metadata"):
            u = resp.usage_metadata.model_dump()
            # Only keep the desired fields
            filtered_u = {k: u.get(k) for k in [
                "prompt_token_count",
                "thoughts_token_count",
                "tool_use_prompt_token_count",
                "total_token_count"
            ] if k in u}
            usage_agg["prompt_token_count"] += safe_int(u.get("prompt_token_count"))
            usage_agg["thoughts_token_count"] += safe_int(u.get("thoughts_token_count"))
            usage_agg["total_token_count"]   += safe_int(u.get("total_token_count"))
            usage_by_agent[agent_name] = filtered_u
        else:
            usage_by_agent[agent_name] = {}

    # --- 4. Mongo connection ---
    close_conn = False
    if mongo_client is None:
        mongo_client = _get_mongo_client()
        close_conn = True
    if not mongo_client:
        logger.error("Cannot connect to MongoDB.")
        return

    # --- 5. Build & insert document ---
    try:
        doc = {
            "file_id":            file_name,
            "industry_prefix":    industry_prefix,
            "file_size_bytes":    len(raw),
            "file_hash":          file_hash,
            "model_names":        list(model_names),
            "num_agents":         len(responses_by_agent),
            "usage_tokens": {
                **usage_agg,
                "usage_by_agent": usage_by_agent
            },
            "timestamp":          datetime.now(),
            # embed each agent’s cleaned JSON under its key:
            **{agent: cleaned_by_agent[agent] for agent in cleaned_by_agent}
        }
        db = mongo_client[db_name]
        db[collection_name].insert_one(doc)
        logger.info(f"Saved LLM outputs for {file_name} to {db_name}.{collection_name}")
    except Exception as e:
        logger.error(f"Error saving to MongoDB: {e}")
    finally:
        if close_conn:
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
