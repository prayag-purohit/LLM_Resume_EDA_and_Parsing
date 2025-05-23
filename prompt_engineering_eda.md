# Prompt Engineering Strategy for Resume EDA

To-Do: 
1. Add excel sheets that can be used as tools. Give multiple country university ranking lists that the model can utilize when needed 
2. Add function calling, that could be used to count the number of characters etc. We can store sections like professional summary's word count, resume legnth / word count, 

This document outlines the prompt engineering strategy for extracting structured information from resumes using the Gemini API.

## Core Principles

1. **Structured Output Format**: All prompts will request JSON-formatted responses to ensure consistent parsing
2. **Robustness to Missing Data**: Prompts will handle missing sections gracefully with default values
3. **Consistent Scoring Rubrics**: Clear scoring criteria for quality assessment
4. **Step-by-Step Extraction**: Break down complex extraction into manageable steps
5. **Few-Shot Examples**: Include examples to guide the model's understanding

## EDA Extraction Prompt Template

```
You are an expert resume analyzer for a correspondence study on immigrant employment. The JSON would be used to map the quality of the base resume, overall this task aims to map the sample quality distribution. Extract the following information from the provided resume (attached) in JSON format. 

Notes: 
* Some of the below mentioned sections may not be available in all resumes, those fields could be mapped null. The JSON data you give would be put in a MongoDB database directly.
* The company's, and institutions can be found with google search - they can be assessed through geographies, employee counts, whether they are listed on stock exchange
* Education institution would be counted as prestigious if they show up in national ranking lists (top 50), and/or if they are internationally recognized.  

1. Experience Analysis:
   - Total years of experience (numeric)
   - Last three positions with titles, company names, and dates
   - Company quality assessment for each based on  (large/medium/small)
   - Most recent industry sector

2. Education Analysis:
   - Highest degree obtained
   - Educational institutions
   - Whether institutions are internationally recognized/famous (true/false)
   - Field(s) of study

3. Skills Assessment:
   - Technical skills list
   - Soft skills list
   - Language proficiencies

4. Quality Scoring (1-10 scale):
   - Overall resume quality score
   - Experience quality score
   - Education quality score
   - Skills presentation score

5. Background Information:
   - Likely home country or region (if detectable)
   - International vs. domestic experience ratio

Use the following scoring rubric for quality assessment:
- 9-10: Exceptional (prestigious institutions/companies, clear progression, comprehensive skills)
- 7-8: Strong (good institutions/companies, solid progression, relevant skills)
- 5-6: Average (standard institutions/companies, some progression, basic skills)
- 3-4: Below average (limited experience, minimal progression, few relevant skills)
- 1-2: Poor (significant gaps, unclear experience, very limited skills)

Return ONLY a JSON object with no additional text. Use the following structure:
{
  "candidate_summary": "string – ~100-word high-level overview",
  "industry_sector": "string",
  "EDA": {
    "experience": {
      "total_years": "number",
      "recent_positions": [
        {
          "title": "string",
          "company": "string",
          "dates": "string",
          "company_size": "small|medium|large"
        }
      ]
    },
    "education": {
      "highest_degree": "string",
      "institutions": [
        {
          "name": "string",
          "is_prestigious": "boolean",
          "national_ranking": "number"
        }
      ],
      "fields_of_study": ["string"]
    },
    "skills": {
      "technical": ["string"],
      "soft": ["string"],
      "languages": ["string"]
    },
    "quality_scores": {
      "overall": "number",
      "experience": "number",
      "education": "number",
      "skills": "number"
    },
    "background": {
      "likely_home_country": "string",
      "international_experience_ratio": "number"
    }
  }
}


```
Attachment: Resume
## Company Size Assessment Criteria

To determine company size (large/medium/small):

- **Large**: Fortune 500, multinational corporations, well-known national brands, 1000+ employees
- **Medium**: Regional companies, established firms in specific industries, 100-999 employees
- **Small**: Local businesses, startups, specialized boutique firms, <100 employees

## Institution Prestige Assessment

To determine if an educational institution is prestigious:

- **Prestigious**: Top 100 global universities, well-known national institutions, ivy league, flagship state universities
- **Non-prestigious**: Regional colleges, community colleges, lesser-known institutions

## Handling Ambiguity

When information is unclear or missing:
- Use "unknown" for text fields
- Use -1 for numeric fields
- Use empty arrays [] for list fields
- Use false for boolean fields

## Example Few-Shot Learning

Include 1-2 examples of resumes and their correct JSON output to guide the model's understanding of the task.

## Fallback Strategy

If the model struggles with the complete extraction, implement a multi-step approach:
1. Extract basic information first (experience, education)
2. Follow up with quality assessments
3. Finally extract background information

This staged approach can help with complex resumes or when the model has difficulty with the full extraction in one pass.
