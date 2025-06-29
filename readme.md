# Resume EDA and Parsing with Gemini API

This repository provides an end-to-end pipeline for automated Exploratory Data Analysis (EDA) and structured parsing of resumes using the Google Gemini API. The system is designed for correspondence studies on immigrant employment, enabling structured extraction and quality assessment of resume data for research and analytics.

## Features

- **Automated Resume Parsing**: Uploads PDF resumes and extracts structured information using advanced LLM prompt engineering.
- **Prompt Engineering Strategy**: Utilizes robust, JSON-based prompt templates for consistent and reliable data extraction (see `prompt_engineering_eda.md` and `prompt_engineering_parsing.md`).
- **Strict JSON Resume Extraction**: The `prompt_engineering_parsing.md` prompt ensures all resume data is extracted in a strict JSON format, suitable for downstream analytics and database storage.
- **Quality Scoring**: Assigns scores to resumes based on experience, education, and skills using a transparent rubric.
- **Company & Institution Assessment**: Evaluates company size and educational institution prestige using defined criteria.

- **CURRENT LIMITATION**: Gemini has trouble processing word files. PDFs are tested and work fine. 

## Recent Updates

- Added MongoDB Atlas integration for shared database access (512MB free tier)
- Implemented word document support through automatic docx to PDF conversion
- Created resumed_exported module for converting MongoDB data to PDF resumes
- Switched to class-based architecture for improved code organization
- Implemented JSON Resume pipeline for generating formatted PDFs
- Added MongoDB pull data module for collection management 
- Added a feature to upload a mongoDB document to gemini input (gemini.mongo_document = mongo_document) - used with mongodb pull data functions from last update
- Made file uploads to gemini optional. Can work with either files, or mongo_documents
- Added a multi agent workflow framework - can pass mutliple models, and save responses to a single mongodb document. 
- Current challenges:
  - Logger creates single file in loops
  - Empty error files being generated
  - Some JSON Resume themes producing suboptimal results

## Setup instructions
1. Install Node.js and npm (optional: if planning to use resumed_exporter to convert json to pretty PDFs)
```cmd
# Download and install Node.js from https://nodejs.org/
# During installation, ensure "Add to PATH" is selected
# Verify installation
node --version
npm --version
```

2. Install required npm packages globally (optional just like in step 1)
```cmd
# Install resumed CLI tool
npm install -g resumed

# Install JSON Resume themes
npm install -g jsonresume-theme-even
# Add other themes as needed from https://jsonresume.org/themes/
```

3. Create a python `venv` and install dependencies
``` cmd
python venv path/to/venv 
pip install -r requirements.txt
```

4. Create a .env file and set up the API keys.
``` 
# Add your Gemini API key here
GEMINI_API_KEY=YOURAPIKEY

# MongoDB connection (optional)
MONGODB_URI=mongodb://localhost:27017/ #Use a connection string provided by prayag to use prod db
```

5. Create a mongoDB server, db, and collections (Skip this step if using a prod db)

6. Place Resume Inputs (PDFS) in `Resume_inputs` folder

7. Ensure prompt files exist (md format) and they contain triple backticks marking the beginning and end of the prompt

8. Run main.py if parsing multiple files, changing whatever parameters you need for geminipipeline function. Review output text in `text_output` dir, and logs in `logs` dir.

*Note*: the `gemini_pipeline` function can be called without a loop 

## File and Function Overview

- `single_agent.py`: Template code when using a single agent, and looping through files in a dir,  converting docx to pdfs when required, and saving to mongoDB.
- `multi_agent.py`: Template code when using multi agent flow, and looping through files in a dir, converting docx to pdfs when required, and saving to mongoDB.
- `libs/gemini_processor.py`: Handles LLM interaction
- `libs/mongodb.py`: Handles mongodb interactions. Upload and get documents
- `libs/resumed_exported.py`: Handles conversion of MongoDB data to PDF resumes using JSON Resume.Requirees npm and some node dependencies
- `libs/.env`: Contains secrets
- `Resumee_inputs`: Add resume documents to be parsed in this dir
- `Prompt_templates/`: Contains prompt templates
- `requirements.txt`: Python dependencies.

---
# Detailed documentation (Methods, and Attributes by libs/files.py)

## GeminiProcessor Documentation

### Module
- **File**: `libs/gemini_processor.py`
- **Purpose**: Handles LLM interactions with Google Gemini API.
- **Dependencies**: `os`, `re`, `datetime`, `sys`, `google.genai`, `dotenv`, `utils.get_logger`

### Class: `GeminiProcessor`

### Description
Facilitates file processing, prompt management, and content generation using the Gemini API.

### Initialization
```python
GeminiProcessor(model_name: str = "gemini-1.5-flash", temperature: float = 0.4, api_key: Optional[str] = None, enable_google_search: bool = False)
```

#### Parameters
- `model_name` (str): Gemini model (default: `"gemini-1.5-flash"`).
- `temperature` (float): Randomness control (default: `0.4`).
- `api_key` (Optional[str]): API key, loads from `GEMINI_API_KEY` if `None`.
- `enable_google_search` (bool): Enables Google Search tool (default: `False`).

#### Attributes
- `model_name` (str)
- `temperature` (float)
- `client` (genai.Client)
- `tools` (List[types.Tool])
- `uploaded_resume_file` (Optional[types.FileData])
- `prompt_template` (Optional[str])
- `mongo_document` (Optional[Any])

### Methods

#### `load_prompt_template(file_path: str) -> str`
Loads prompt template from a markdown file between triple backticks.

- **Args**: `file_path` (str)
- **Returns**: `str`
- **Exceptions**: `FileNotFoundError`, `ValueError`

#### `upload_file(document_path: str) -> types.FileData`
Uploads a file to Gemini API.

- **Args**: `document_path` (str)
- **Returns**: `types.FileData`
- **Exceptions**: `FileNotFoundError`

#### `delete_uploaded_file() -> None`
Deletes the uploaded file.

- **Exceptions**: Logged errors

#### `generate_content(prompt: Optional[str] = None) -> types.GenerateContentResponse`
Generates content using the Gemini model.

- **Args**: `prompt` (Optional[str])
- **Returns**: `types.GenerateContentResponse`
- **Exceptions**: `ValueError`

#### `save_generated_content(response: types.GenerateContentResponse, output_dir: str = "text_output") -> None`
Saves generated content to a file.

- **Args**: `response`, `output_dir` (str)
- **Exceptions**: Logged errors

#### `process_file(file_path: str, prompt_template_path: str) -> types.GenerateContentResponse`
WRAPPER, NOT VERY USEFUL. UNLESS YOU"RE SURE YOU WANT TO 1)LOAD TEMPLATE, UPLOAD FILE, SAVE OUTPUT, and GET RESPONSE
Processes a file by loading template, uploading file, generating, and saving content.

- **Args**: `file_path` (str), `prompt_template_path` (str)
- **Returns**: `types.GenerateContentResponse`
- **Exceptions**: `ValueError`

## Example
```python
processor = GeminiProcessor()
processor.load_prompt_template("prompts/template.md")
response = processor.process_file("resume.pdf", "prompts/template.md")
```

## Notes
- Supports MongoDB document processing (commented out for testing).
- Uses custom logging via `get_logger`.
- Ensures cleanup of uploaded files.

# MongoDB Utilities Documentation

## Overview
The `mongodb.py` module provides utilities for interacting with MongoDB to save and retrieve LLM responses and file metadata.

## Module
- **File**: `mongodb.py`
- **Purpose**: Manages MongoDB operations for LLM response storage and retrieval.
- **Dependencies**: `os`, `json`, `pymongo`, `datetime`, `hashlib`, `dotenv`, `sys`, `utils.get_logger`

## Functions

### `_get_mongo_client() -> MongoClient | None`
Creates a MongoDB client using the `MONGODB_URI` environment variable.

- **Returns**: `MongoClient` or `None` if connection fails.
- **Exceptions**: Logs errors if connection fails.

### `_clean_raw_llm_response(llm_raw_text: str) -> dict | ValueError`
Cleans raw LLM text, extracting JSON between triple backticks.

- **Args**: `llm_raw_text` (str)
- **Returns**: Parsed JSON `dict` or `ValueError` if invalid.
- **Exceptions**: Logs JSON parsing errors.

### `save_single_LLM_response_to_mongodb(llm_response, db_name: str = "Resume_study", collection_name: str = "EDA_data", file_path: str = "HRC resume 10.pdf", mongo_client: MongoClient | None = None) -> None`
Saves a single LLM response to MongoDB (deprecated, use `save_llm_responses_to_mongodb`).

- **Args**:
  - `llm_response`: LLM response object
  - `db_name` (str): Database name
  - `collection_name` (str): Collection name
  - `file_path` (str): File path
  - `mongo_client`: Optional MongoClient
- **Exceptions**: Logs errors for file or MongoDB issues.

### `save_llm_responses_to_mongodb(responses_by_agent: dict[str, any], *, db_name: str = "Resume_study", collection_name: str = "EDA_data", file_path: str, mongo_client: MongoClient | None = None) -> None`
Saves multiple LLM agent responses to MongoDB.

- **Args**:
  - `responses_by_agent` (dict): Agent names mapped to response objects
  - `db_name` (str): Database name
  - `collection_name` (str): Collection name
  - `file_path` (str): File path
  - `mongo_client`: Optional MongoClient
- **Exceptions**: Logs errors for file or MongoDB issues.

### `get_all_file_ids(db_name: str, collection_name: str, mongo_client: MongoClient | None = None) -> list`
Retrieves all `file_id` values from a MongoDB collection.

- **Args**:
  - `db_name` (str): Database name
  - `collection_name` (str): Collection name
  - `mongo_client`: Optional MongoClient
- **Returns**: List of `file_id` values
- **Exceptions**: Logs retrieval errors.

### `get_document_by_fileid(db_name: str, collection_name: str, file_id: str, mongo_client: MongoClient | None = None) -> dict | None`
Retrieves a document by `file_id`.

- **Args**:
  - `db_name` (str): Database name
  - `collection_name` (str): Collection name
  - `file_id` (str): File ID
  - `mongo_client`: Optional MongoClient
- **Returns**: Document `dict` or `None`
- **Exceptions**: Logs retrieval errors.

## Example
```python
from mongodb import save_llm_responses_to_mongodb, get_all_file_ids

client = _get_mongo_client()
save_llm_responses_to_mongodb({"EDA": response}, file_path="resume.pdf", mongo_client=client)
file_ids = get_all_file_ids("Resume_study", "EDA_data", client)
```

## Notes
- Uses `get_logger` for logging.
- Manages MongoDB connections with automatic closure.
- Supports file metadata (hash, size, industry prefix).
- `save_single_LLM_response_to_mongodb` is deprecated.