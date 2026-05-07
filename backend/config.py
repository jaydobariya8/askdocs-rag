import os
from pydantic_settings import BaseSettings
from pydantic import Field


def _get_groq_key() -> str:
    # Try env var first (local .env or Streamlit Cloud secrets injected as env)
    key = os.environ.get("GROQ_API_KEY", "")
    if key:
        return key
    # Fallback: read directly from Streamlit secrets (when running on Cloud)
    try:
        import streamlit as st
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return ""


class Settings(BaseSettings):
    groq_api_key: str = Field(default_factory=_get_groq_key)

    # Model config
    groq_model: str = "llama-3.1-8b-instant"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Chunking
    chunk_size: int = 500
    chunk_overlap: int = 50

    # Retrieval
    top_k: int = 5
    relevance_threshold: float = 0.35

    # Storage — use /tmp on cloud (always writable), local fallback
    chroma_persist_dir: str = "/tmp/chroma_db"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
