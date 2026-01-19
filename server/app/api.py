import logging
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.logging import setup_logging
from app.core.config import settings
from app.llm.clients import ChatClient, EmbeddingsClient
from app.rag.vectorstore import ChromaVectorStore
from app.rag.ingest import ingest_kb
from app.rag.pipeline import analyze_log

log = logging.getLogger("api")

app = FastAPI(title="Hackathon Incident Reasoner Server", version="0.1")

# Global singletons (hackathon-simple)
store = ChromaVectorStore()
embedder = EmbeddingsClient(settings.embed_api_url, settings.embed_model_name)
llm = ChatClient(settings.llm_api_url, settings.llm_model_name)

KB_INGESTED = False

class AnalyzeRequest(BaseModel):
    log_text: str

@app.on_event("startup")
def startup():
    global KB_INGESTED
    setup_logging()

    if not settings.llm_api_url or not settings.embed_api_url:
        log.warning("LLM_API_URL or EMBED_API_URL not set. Server will not work properly.")

    # ingest KB once at startup
    if not KB_INGESTED:
        count = ingest_kb("data/kb", store, embedder)
        KB_INGESTED = True
        log.info("KB ingestion complete. Chunks ingested: %d", count)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/analyze")
async def analyze_file(file: UploadFile = File(...)):
    try:
        raw = await file.read()
        log_text = raw.decode("utf-8", errors="ignore")
        if not log_text.strip():
            raise HTTPException(status_code=400, detail="Empty log file.")
        result = analyze_log(log_text, store, embedder, llm)
        return JSONResponse(content=result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Analyze failed.")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze_text")
def analyze_text(req: AnalyzeRequest):
    try:
        if not req.log_text.strip():
            raise HTTPException(status_code=400, detail="Empty log_text.")
        result = analyze_log(req.log_text, store, embedder, llm)
        return JSONResponse(content=result.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Analyze_text failed.")
        raise HTTPException(status_code=500, detail=str(e))
