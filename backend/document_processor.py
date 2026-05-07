import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter
from backend.config import settings


def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]

    if ext == "pdf":
        import io
        text_parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)

    elif ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")

    else:
        raise ValueError(f"Unsupported file type: .{ext}. Only PDF and TXT are supported.")


def chunk_text(
    text: str,
    chunk_size: int = settings.chunk_size,
    overlap: int = settings.chunk_overlap,
) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_text(text)
    # Filter empty chunks
    return [c.strip() for c in chunks if c.strip()]
