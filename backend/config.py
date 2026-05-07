from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    groq_api_key: str = Field(..., env="GROQ_API_KEY")

    # Model config
    groq_model: str = "llama-3.1-8b-instant"
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    # Chunking
    chunk_size: int = 500
    chunk_overlap: int = 50

    # Retrieval
    top_k: int = 5
    relevance_threshold: float = 0.35

    # Storage
    chroma_persist_dir: str = "./chroma_db"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
