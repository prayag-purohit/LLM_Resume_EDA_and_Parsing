# treatment_generation_script.py
#
# Description:
# This script automates the process of generating treated resumes for a correspondence study.
# It reads standardized "control" resumes from a MongoDB collection, applies various
# treatments (Canadian Education, Canadian Work Experience), validates the output using
# cosine similarity, and saves the final, treated resumes to a new collection.
#
# Workflow for each source resume:
# 1. Fetch a standardized resume from the 'Standardized_resume_data' collection.
# 2. Randomly select two Canadian Education (CEC) and two Canadian Work (CWE) treatment.
# 3. Generate 4 versions of the resume:
#    - Control (rephrased summary/highlights only)
#    - Treatment I (rephrased + CEC)
#    - Treatment II (rephrased + CWE)
#    - Treatment III (rephrased + CEC + CWE)
# 4. For each generation, validate the rephrasing with a focused cosine similarity score.
# 5. Save the 4 generated documents as separate entries in the 'Treated_resumes' collection.


import sys
sys.path.append('..')
sys.path.append('../libs')

from libs.mongodb import get_all_file_ids,_get_mongo_client ,get_document_by_fileid, _clean_raw_llm_response
from libs.gemini_processor import GeminiProcessor
from utils import get_logger
import json
import random
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

logger = get_logger(__name__)

# Sector we are processing
SECTOR = "ITC"

# MongoDB configuration
MONGO_CLIENT = _get_mongo_client()
DB_NAME = "Resume_study"
SOURCE_COLLECTION_NAME = "Standardized_resume_data"
TARGET_COLLECTION_NAME = "Treated_resumes"

# Gemini model configuration
GEMINI_MODEL_NAME = "gemini-2.5-flash"
GEMINI_TEMPERATURE = 0.7
ENABLE_GOOGLE_SEARCH = False
PROMPT_TEMPLATE_PATH = "Phase 2 Workflow/Prompts/prompt_treatment_generation.md"
MAX_RETRIES = 2

# Treatment file paths
TREATMENT_CEC_FILE = "Phase 2 Workflow/Education_treatment_dummy.xlsx"
TREATMENT_CWE_FILE = "Phase 2 Workflow/WE_treatment_dummy.xlsx"
# Load treatment data from Excel files in pandas DataFrames
cec_treatment_df = pd.read_excel(TREATMENT_CEC_FILE)
cec_treatment_df = cec_treatment_df[cec_treatment_df['sector'] == SECTOR].reset_index(drop=True)
cwe_treatment_df = pd.read_excel(TREATMENT_CWE_FILE)
cwe_treatment_df = cwe_treatment_df[cwe_treatment_df['sector'] == SECTOR].reset_index(drop=True)


# Load the model once to be reused in the loop for cosine similarity calculations
SIMILARITY_MODEL = SentenceTransformer('all-MiniLM-L6-v2')

def extract_rephrased_text(resume_data):
    text_parts = []
    if 'basics' in resume_data and 'summary' in resume_data['basics']:
        text_parts.append(resume_data['basics']['summary'])
    if 'work_experience' in resume_data:
        for job in resume_data['work_experience']:
            if 'highlights' in job and isinstance(job['highlights'], list):
                text_parts.append(" ".join(job['highlights']))
    return " ".join(text_parts)

def calculate_focused_similarity(control_resume_data, treated_resume_data):
    control_text = extract_rephrased_text(control_resume_data)
    treated_text = extract_rephrased_text(treated_resume_data)
    
    if not control_text or not treated_text:
        return 0.0

    control_embedding = SIMILARITY_MODEL.encode(control_text)
    treated_embedding = SIMILARITY_MODEL.encode(treated_text)
    
    score = cosine_similarity([control_embedding], [treated_embedding])[0][0]
    return score

def select_and_prepare_treatments(
    cec_treatment_df,
    cwe_treatment_df,
    source_resume_data,
    treatment_prompt,
):
    """
    Selects random treatments for Canadian Education (CEC) and Canadian Work Experience (CWE),
    and prepares treatment prompts with corresponding treatment metadata for a resume.

    Args:
        cec_treatment_df (pd.DataFrame): DataFrame containing CEC treatments for the sector.
        cwe_treatment_df (pd.DataFrame): DataFrame containing CWE treatments for the sector.
        source_resume_data (dict): Resume data to be treated.
        treatment_prompt (str): Prompt template with placeholders for resume and treatment.
        logger (logging.Logger, optional): Logger instance for logging messages.

    Returns:
        dict: Dictionary with keys 'I', 'II', 'III', each mapping to a dictionary with:
              - 'prompt': The prepared treatment prompt.
              - 'treatment_applied': The chosen treatment details as a JSON-compatible dict.
            Returns None if treatments are unavailable.
    """
    # Check if treatment DataFrames are empty
    if cec_treatment_df.empty or cwe_treatment_df.empty:
        logger.error("No treatments available for Canadian Education or Canadian Work Experience.")
        return None

    # Select two random treatments for CEC and CWE
    random_cec_treatments = cec_treatment_df.sample(n=2, replace=False).to_dict(orient='records')
    logger.info(f"Selected Canadian Education treatments: {random_cec_treatments}")
    random_cwe_treatments = cwe_treatment_df.sample(n=2, replace=False).to_dict(orient='records')
    logger.info(f"Selected Canadian Work Experience treatments: {random_cwe_treatments}")

    # Initialize treatment prompts dictionary
    treatment_prompts = {}

    # Prepare base prompt with resume data
    base_prompt = treatment_prompt.replace("{JSON_resume_object}", str(source_resume_data))

    # Select first treatment for Education (I)
    chosen_cec_idx = random.choice([0, 1])
    education_treatment_prompt = base_prompt.replace(
        "{Treatment_object}", str(random_cec_treatments[chosen_cec_idx])
    )
    treatment_prompts["Type_I"] = {
        "prompt": education_treatment_prompt,
        "treatment_applied": {"Canadian_Education": random_cec_treatments[chosen_cec_idx]}
    }

    # Select first treatment for Work Experience (II)
    chosen_cwe_idx = random.choice([0, 1])
    work_experience_treatment_prompt = base_prompt.replace(
        "{Treatment_object}", str(random_cwe_treatments[chosen_cwe_idx])
    )
    treatment_prompts["Type_II"] = {
        "prompt": work_experience_treatment_prompt,
        "treatment_applied": {"Canadian_Work_Experience": random_cwe_treatments[chosen_cwe_idx]}
    }

    # Use the other treatments for mixed treatment (III)
    mixed_cec_idx = 1 - chosen_cec_idx  # Select the other CEC treatment
    mixed_cwe_idx = 1 - chosen_cwe_idx  # Select the other CWE treatment
    mixed_treatment = {
        "Canadian_Education": random_cec_treatments[mixed_cec_idx],
        "Canadian_Work_Experience": random_cwe_treatments[mixed_cwe_idx]
    }
    education_work_experience_treatment_prompt = base_prompt.replace(
        "{Treatment_object}", str(mixed_treatment)
    )
    treatment_prompts["Type_III"] = {
        "prompt": education_work_experience_treatment_prompt,
        "treatment_applied": mixed_treatment
    }

    return treatment_prompts

#=============================================================================================================================================================================

# 1. Import all files from the source collection for the specified sector
all_files = get_all_file_ids(
    db_name=DB_NAME,
    collection_name=SOURCE_COLLECTION_NAME,
    mongo_client=MONGO_CLIENT
)

sector_files = [f for f in all_files if SECTOR in f]
if not sector_files:
    logger.error(f"No files found for sector {SECTOR}. Exiting.")
    sys.exit(1)
logger.info(f"Found {len(sector_files)} files for sector: {SECTOR}.")

# 2. Initialize the GeminiProcessor
treatment_model = GeminiProcessor(
    model_name= GEMINI_MODEL_NAME,
    temperature=GEMINI_TEMPERATURE,
    enable_google_search=ENABLE_GOOGLE_SEARCH
)
treatment_prompt = treatment_model.load_prompt_template(prompt_file_path=PROMPT_TEMPLATE_PATH)


# main processing loop
for file in sector_files[0:1]:
    # Building the final document structure, initializing empty doc with metadata
    logger.info(f"Processing file: {file}")
    file_data = get_document_by_fileid(
        db_name=DB_NAME,
        collection_name=SOURCE_COLLECTION_NAME,
        file_id=file,
        mongo_client=MONGO_CLIENT
    )
    # Filter the resume data for the current file
    source_resume_data = file_data.get('resume_data', {})
    if not source_resume_data:
        logger.error(f"No resume data found for file {file}. Skipping.")
        sys.exit(1)

    final_doc = {}
    metadata_keys = ['file_id', 'industry_prefix', 'file_size_bytes', 'file_hash']
    metadata = {k: file_data.get(k) for k in metadata_keys}
    final_doc.update(metadata)
    final_doc['control_resume'] = source_resume_data.get('resume_data', {})

    # Get two random treatments for Canadian Education and Canadian Work Experience
    treatment_prompts = select_and_prepare_treatments(
        cec_treatment_df,
        cwe_treatment_df,
        source_resume_data,
        treatment_prompt,
    )
    if not treatment_prompts:
        logger.error(f"No treatments available for file {file}. Skipping.")
        sys.exit(1)

    for key, value in treatment_prompts.items():
        temp_treatment_dict = {}
        logger.info(f"Generating treatment {key} for file {file}.")
        # Generate the treated resume using GeminiProcessor
        response = treatment_model.generate_content(
            contents=[value['prompt']],
            model=GEMINI_MODEL_NAME
        )
        
        if not response or not response.contents:
            logger.error(f"Failed to generate content for treatment {key} in file {file}.")
            continue
        
        # Clean the raw response
        treated_resume = _clean_raw_llm_response(response.contents[0])
        
        # Validate the rephrasing with cosine similarity
        focused_similarity_score = calculate_focused_similarity(
            source_resume_data, treated_resume
        )
        
        if focused_similarity_score < 0.85:
            logger.warning(f"Low similarity score ({focused_similarity_score}) for treatment {key} in file {file}. Please add retry logic")
            sys.exit(1)
        
        temp_treatment_dict['focused_similarity_score'] = focused_similarity_score
        temp_treatment_dict['treatment_applied'] = value['treatment_applied']
        temp_treatment_dict['resume_data'] = treated_resume
        
        final_doc[key] = temp_treatment_dict



    
    
