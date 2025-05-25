import os
from gemini_mongo_pipeline import gemini_pipeline
from docx2pdf import convert

def local_file_loop(resume_dir: str = "Resume_inputs", prompt_file_path: str = "prompt_engineering_eda.md") -> None:
    """
    Loop through all the resume files in the specified directory and process them using the gemini_pipeline function.
    This function assumes that the files are located in a directory named "Resume_inputs".
    If the input is a .docx file, it converts it to .pdf before processing.
    The processed files are moved to a directory named "Processed_resumes".
    The original .docx files are moved to a subdirectory named "docx_converted_to_pdf".
    """
    resume_dir = "Resume_inputs"

    for filename in os.listdir(resume_dir):
        file_path = os.path.join(resume_dir, filename)
        if filename.endswith(".docx"):
            # Convert .docx to .pdf
            pdf_file_path = os.path.splitext(file_path)[0] + ".pdf"
            convert(file_path, pdf_file_path)
            # Move the original .docx to docx_converted_to_pdf directory
            converted_dir = os.path.join(resume_dir, "base_docx_pre-conversion")
            os.makedirs(converted_dir, exist_ok=True)
            dest_docx_path = os.path.join(converted_dir, filename)
            os.rename(file_path, dest_docx_path)
            file_path = pdf_file_path  # Update file_path to the new PDF file path
        if os.path.isfile(file_path):
            gemini_pipeline(
                prompt_file_path=prompt_file_path,
                file_path=file_path,
                mongo_collection="EDA_data",
                mongo_db="Resume_study",
                google_search_tool=False,
                model_name="gemini-2.0-flash"
            )
            # Move the processed file to Processed_resumes directory
            processed_dir = "Processed_resumes"
            os.makedirs(processed_dir, exist_ok=True)
            dest_path = os.path.join(processed_dir, filename)
            os.rename(file_path, dest_path)

if __name__ == "__main__":
    local_file_loop(resume_dir="Resume_inputs", prompt_file_path="prompt_engineering_eda.md")
    print("Processing completed.")

