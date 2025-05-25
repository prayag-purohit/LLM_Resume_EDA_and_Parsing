import gemini_processor
from gemini_mongo_pipeline import _save_to_mongodb
from datetime import datetime
import os

gemini = gemini_processor.GeminiProcessor(
    model_name="gemini-2.0-flash",
    temperature=0.4,
    api_key=os.getenv("GEMINI_API_KEY"),
    enable_google_search=False,
)

prompt = gemini.load_prompt_template("prompt_engineering_eda.md")

resume_path = "Resume_inputs/HRC resume 10 test2.pdf"
file = gemini.upload_file(document_path=resume_path)

response = gemini.generate_content(
    prompt=prompt
)

output_file_path = os.path.join(
    "text_output",
    f"{gemini.file_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
)

gemini.save_generated_content(response=response, output_path=output_file_path)

_save_to_mongodb(
    llm_raw_text=response.text,
    llm_response=response,
    file_name=gemini.file_name,
    file_path=resume_path,
    db_name="Resume_study",
    collection_name="Class_test",
    model_name=gemini.model_name
)