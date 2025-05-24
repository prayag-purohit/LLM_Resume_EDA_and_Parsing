import os
from gemini_mongo_pipeline import gemini_pipeline

def local_file_loop(resume_dir: str = "Resume_inputs", prompt_file_path: str = "prompt_engineering_eda.md") -> None:
    """
    Loop through all the resume files in the specified directory and process them using the gemini_pipeline function.
    This function assumes that the files are located in a directory named "Resume_inputs".
    """
    resume_dir = "Resume_inputs"

    for filename in os.listdir(resume_dir):
        file_path = os.path.join(resume_dir, filename)
        if os.path.isfile(file_path):
            gemini_pipeline(
                prompt_file_path=prompt_file_path,
                file_path=file_path,
                mongo_collection="JSONResumes_raw",
                mongo_db="Resume_study",
                google_search_tool=False,
                model_name="gemini-2.0-flash"
            )

if __name__ == "__main__":
    local_file_loop(resume_dir="Resume_inputs", prompt_file_path="prompt_engineering_parsing.md")
    print("Processing completed.")


