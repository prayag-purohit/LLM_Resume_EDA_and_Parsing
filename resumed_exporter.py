import json
import os
import subprocess
import tempfile
from typing import Any

from mongodb import get_all_file_ids, get_document_by_fileid
from utils import get_logger
 

logger = get_logger(__name__)


def export_jsonresume_to_pdf(json_data: Any,
                              output_path: str,
                              theme: str = 'jsonresume-theme-even') -> None:
    """Export JSON Resume data to a PDF file using the ``resumed`` CLI.

    Parameters
    ----------
    json_data : Any
        Parsed JSON resume data.
    output_path : str
        Destination path for the generated PDF.
    theme : str, optional
        Theme name to use with ``resumed``, by default ``jsonresume-theme-even``.
    """

    
    fd, temp_path = tempfile.mkstemp(suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as tmp:
            json.dump(json_data, tmp)

        subprocess.run(
            ['resumed', 'export', temp_path, '-o', output_path, '-t', theme],
            check=True,
            shell=True
        )
        logger.info(f"Exported PDF to {output_path}")
    except subprocess.CalledProcessError as exc:
        logger.error(f"resumed export failed: {exc}")
        raise
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def export_all_resumes(db_name: str,
                        collection: str,
                        output_dir: str,
                        theme: str = 'jsonresume-theme-even') -> None:
    """Export all resumes stored in MongoDB to PDF files.

    Parameters
    ----------
    db_name : str
        Name of the MongoDB database.
    collection : str
        Collection containing the resumes.
    output_dir : str
        Directory where PDF files will be written.
    theme : str, optional
        ``resumed`` theme to use for PDF generation.
    """
    os.makedirs(output_dir, exist_ok=True)

    file_ids = get_all_file_ids(db_name, collection)
    for file_id in file_ids:
        doc = get_document_by_fileid(db_name, collection, file_id)
        if not doc or 'JSON_Resume' not in doc:
            logger.warning(f"No JSON_Resume data for {file_id}")
            continue

        pdf_path = os.path.join(output_dir, f"{file_id}.pdf")
        export_jsonresume_to_pdf(doc['JSON_Resume'], pdf_path, theme)

export_all_resumes(db_name="Resume_study", collection="JSON_raw", output_dir="Exported_resumes", theme="jsonresume-theme-even")