import os
import json
from pymongo import MongoClient
from datetime import datetime
import hashlib
from dotenv import load_dotenv
from PYTHON_MODULES.utils import get_logger

logger = get_logger(__name__)

load_dotenv()

# === Setup ===

def _get_mongo_client(Prod: bool = False) -> MongoClient:
    """
    Create and return a MongoDB client based on the environment variable MONGODB_URI and MONGODB_PROD.
    Defaults to the Local URI if Prod is False.

    Args:
        Prod (bool): If True, use the production MongoDB URI; otherwise, use the development URI.
    """
    if Prod:
        mongo_uri = os.getenv("MONGODB_PROD_URI")
    else:
        mongo_uri = os.getenv("MONGODB_LOCAL_URI")
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

def _parse_llm_text_to_dict(llm_raw_text: str, file_name: str):
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

def _build_document(template: dict, data_sources: dict) -> dict:
    """
    Recursively builds a document by populating a template with data sources.
    """
    doc = {}
    for key, value in template.items():
        if isinstance(key, str) and key.startswith("$unpack"):
            # This is our special key. The value is the name of the data source to unpack.
            source_name = value
            if source_name in data_sources and isinstance(data_sources[source_name], dict):
                doc.update(data_sources[source_name])
        elif isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            # This is a placeholder like "{{file_id}}".
            placeholder = value[2:-2]
            if placeholder in data_sources:
                doc[key] = data_sources[placeholder]
        elif isinstance(value, dict):
            # Recursively build sub-documents
            doc[key] = _build_document(value, data_sources)
        else:
            # This is a static value from the template
            doc[key] = value
    return doc

# === Save to MongoDB ===
def save_document_from_template(
                    schema_template: dict,
                    data_sources: dict,
                    db_name="Resume_study",
                    collection_name="EDA_data",
                    mongo_client=None):
    """
    Saves a document to MongoDB based on a schema template and a dictionary of data sources.
    """
    if mongo_client is None:
        mongo_client = _get_mongo_client()
        close_client = True
    else:
        close_client = False

    if not mongo_client:
        logger.error("Cannot save to MongoDB: Client not available.")
        return

    try:
        db = mongo_client[db_name]
        collection = db[collection_name]

        # Build the final document using our helper function
        doc_to_insert = _build_document(schema_template, data_sources)

        collection.insert_one(doc_to_insert)
        file_id = data_sources.get("file_id", "Unknown")
        logger.info(f"Successfully saved document to MongoDB for: {file_id}")

    except Exception as e:
        logger.error(f"MongoDB Error during save: {e}")
    finally:
        if close_client and mongo_client:
            mongo_client.close()




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
#if __name__ == "__main__":

