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
- Added MongoDB pull data module for collection management
- Implemented JSON Resume pipeline for generating formatted PDFs
- Current challenges:
  - Logger creates single file in loops
  - Empty error files being generated
  - Some JSON Resume themes producing suboptimal results

## Setup instructions
1. Install Node.js and npm
```cmd
# Download and install Node.js from https://nodejs.org/
# During installation, ensure "Add to PATH" is selected
# Verify installation
node --version
npm --version
```

2. Install required npm packages globally
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

## File Overview

- `main.py`: Main entry point for batch processing resumes.
- `gemini_mongo_pipeline.py`: Handles LLM interaction and MongoDB storage.
- `prompt_engineering_eda.md`: Original EDA prompt for exploratory analysis.
- `prompt_engineering_parsing.md`: Strict JSON extraction prompt for structured parsing.
- `requirements.txt`: Python dependencies.
- `resumed_exported.py`: Handles conversion of MongoDB data to PDF resumes using JSON Resume

## Key functions and parameters
`gemini_mongo_pipeline` holds function for LLM interaction and mongo db storage

1. `_process_with_gemini`: Process a file (file mandatory) with the Gemini API and return the response.
    
    Args:\
        - prompt_file_path (str): The path to the prompt template file.\
        - file_path (str): The path to the resume file to be analyzed.\
        - model_name (str): The name of the Gemini model to use.\
        - temperature (float): The temperature setting for content generation.\
        - google_search_tool (bool): Whether to enable the Google Search tool.

2. `_save_to_mongodb` : Save the LLM response to MongoDB in a fixed format. This function, stores the LLM returned JSON as it is, and stores other metadata such as file name, token usage.

    Args:\
        - llm_raw_text (str): The raw text response from the LLM.\
        - llm_response: The LLM response object.\
        - file_name (str): The name of the file being processed.\
        - db_name (str): The MongoDB database name.\
        - collection_name (str): The MongoDB collection name.\
        - file_path (str): The path to the resume file being processed.\
        - mongo_client: Provide a mongo_client if running inside a loop

3. `gemini_pipeline` : Uses both the functions above in sequence.
    
    Args:\
        - prompt_file_path (str): The path to the prompt template file.\
        - file_path (str): The path to the resume file to be analyzed.\
        - mongo_collection (str, optional): The MongoDB collection name to save the results.\
        - mongo_db (str, optional): The MongoDB database name to save the results.\
        - google_search_tool (bool): Whether to enable the Google Search tool.\
        - think_tool (bool): Whether to enable the Think tool.\
        - model_name (str): The name of the Gemini model to use.\
        - temperature (float): The temperature setting for content generation.

In addition, there is a `local_file_loop` function in `main.py` that goes through all the resumes put in `Resume_inputs` dir, and runs an EDA or Parsing pipeline based on the parameters given. 

## Example Output

See `text_output/` for sample extracted JSON files.
[MongoDB_output_images]

To see mongoDB output examples look at the MongoDB_output_images folder. 

---

For more details, see the prompt files and code comments.

