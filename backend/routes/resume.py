from fastapi import APIRouter, UploadFile, File, HTTPException
from services.pdf_extractor import extract_text_from_pdf
import shutil, os, uuid

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    extracted_text = extract_text_from_pdf(file_path)

    os.remove(file_path)

    return {
        "status": "success",
        "filename": file.filename,
        "char_count": len(extracted_text),
        "extracted_text": extracted_text
    }
