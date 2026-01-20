from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    # LLM
    llm_api_url: str = os.getenv("LLM_API_URL", "")
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "")
    # Embeddings
    embed_api_url: str = os.getenv("EMBED_API_URL", "")
    embed_model_name: str = os.getenv("EMBED_MODEL_NAME", "")
    # SSL
    ssl_verify_path: str | bool = os.getenv("SSL_VERIFY_PATH", True)

    # RAG
    top_k: int = int(os.getenv("TOP_K", "5"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "900"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "150"))
    max_log_chars: int = int(os.getenv("MAX_LOG_CHARS", "14000"))
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "12000"))

    # Chroma
    chroma_collection: str = os.getenv("CHROMA_COLLECTION", "kb_hackathon")

    # Server
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8080"))
    
    # Mock web search
    enable_mock_web_search: bool = os.getenv("ENABLE_MOCK_WEB_SEARCH", "true").lower() == "true"
    web_mock_top_k: int = int(os.getenv("WEB_MOCK_TOP_K", "3"))

    debug_pipeline: bool = os.getenv("DEBUG_PIPELINE", "true").lower() == "true"

settings = Settings()
