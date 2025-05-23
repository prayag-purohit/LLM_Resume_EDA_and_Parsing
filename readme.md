# Resume EDA with Gemini API

This repository provides an end-to-end pipeline for automated Exploratory Data Analysis (EDA) of resumes using the Google Gemini API. The system is designed for correspondence studies on immigrant employment, enabling structured extraction and quality assessment of resume data for research and analytics.

## Features

- **Automated Resume Parsing**: Uploads PDF/Docx resumes and extracts structured information using advanced LLM prompt engineering.
- **Prompt Engineering Strategy**: Utilizes a robust, JSON-based prompt template for consistent and reliable data extraction (see `prompt_engineering_eda.md`).
- **Quality Scoring**: Assigns scores to resumes based on experience, education, and skills using a transparent rubric.
- **Company & Institution Assessment**: Evaluates company size and educational institution prestige using defined criteria.
- **Data Storage**: Saves results to both MongoDB and Excel for downstream analysis.
- **Logging**: Comprehensive logging for both info and error events.

## Repository Structure

- `EDA.py` — Main pipeline for resume upload, prompt construction, Gemini API interaction, and data storage.
- `prompt_engineering_eda.md` — Detailed prompt template and strategy for LLM-based extraction.
- `requirements.txt` — Python dependencies.
- `logs/` — Log files for pipeline runs and errors.
- `text_output/` — Raw LLM outputs for debugging and traceability.

## How It Works

1. **Upload Resume**: The pipeline uploads a PDF/Docx resume to the Gemini API.
2. **Prompt Construction**: Uses a carefully engineered prompt to instruct the LLM to extract structured data (see `prompt_engineering_eda.md`).
3. **LLM Extraction**: Gemini returns a JSON object with experience, education, skills, quality scores, and background info.
4. **Data Storage**: Results are saved to MongoDB and/or Excel, along with file metadata and LLM usage statistics.
5. **Cleanup**: Uploaded files are deleted from the cloud after processing.

## Setup & Usage
0. Create a `virtual` env (in VS code: ctrl + shift + p --> select interpretor --> Create virtual environment)
1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Set environment variables**:
   - `GEMINI_API_KEY`: Your Google Gemini API key
   - `MONGODB_URI`: MongoDB connection string i.e. mongodb://localhost:27017/
   (You have to create use a `.env` file for convenience.)
3. **Run the pipeline**:
   - Edit `EDA.py` to specify your resume file path if needed.
   - Run:
     ```bash
     python EDA.py
     ```

## Prompt Engineering

The prompt template (see `prompt_engineering_eda.md`) ensures:
- Structured JSON output for easy parsing
- Robust handling of missing data
- Consistent scoring and assessment
- Stepwise extraction for complex resumes

## Example Output

The LLM returns a JSON object with fields such as:
```json
{
  "candidate_summary": "...",
  "industry_sector": "...",
  "EDA": {
    "experience": { ... },
    "education": { ... },
    "skills": { ... },
    "quality_scores": { ... },
    "background": { ... }
  }
}
```
![MongoDB Image](MongoDB_images\database_image.png)

---

[MongoDB output text](MongoDB_images\output.json)

See `prompt_engineering_eda.md` for the full schema and scoring rubric.

