import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.rag_engine import RAGEngine
from backend.document_processor import extract_text, chunk_text

app = FastAPI(title="RAG Chatbot API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy-init: don't crash at import time, init on first request
_rag: RAGEngine | None = None

ALLOWED_EXTENSIONS = {"pdf", "txt"}


def get_rag() -> RAGEngine:
    global _rag
    if _rag is None:
        _rag = RAGEngine()
    return _rag


class QueryRequest(BaseModel):
    question: str


@app.get("/")
def health_check():
    return {"status": "running", "message": "RAG Chatbot API"}


@app.post("/upload-document")
async def upload_document(file: UploadFile = File(...)):
    ext = file.filename.lower().rsplit(".", 1)[-1] if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Only PDF and TXT are allowed.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        text = extract_text(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {e}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="No text could be extracted from the file.")

    chunks = chunk_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="Document produced no processable chunks.")

    doc_id = str(uuid.uuid4())

    try:
        result = get_rag().add_document(doc_id=doc_id, filename=file.filename, chunks=chunks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index document: {e}")

    return {
        "doc_id": result["doc_id"],
        "filename": result["filename"],
        "num_chunks": result["num_chunks"],
        "message": "Document uploaded successfully",
    }


@app.post("/query")
def query_documents(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        result = get_rag().query(request.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return result


@app.get("/documents")
def list_documents():
    try:
        docs = get_rag().list_documents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {e}")
    return docs


@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    try:
        deleted = get_rag().delete_document(doc_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Deletion failed: {e}")

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Document '{doc_id}' not found.")

    return {"message": "Document deleted successfully", "doc_id": doc_id}
