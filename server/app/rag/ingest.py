from pathlib import Path
from typing import List, Dict, Any
import uuid
import logging

from app.core.config import settings
from app.rag.chunker import chunk_text
from app.rag.vectorstore import ChromaVectorStore
from app.llm.clients import EmbeddingsClient

log = logging.getLogger("ingest")

def load_kb_files(kb_dir: Path) -> List[Dict[str, Any]]:
    items = []
    for p in sorted(kb_dir.glob("*.md")):
        items.append({"path": str(p), "text": p.read_text(encoding="utf-8", errors="ignore")})
    return items

def ingest_kb(kb_dir: str, store: ChromaVectorStore, embedder: EmbeddingsClient) -> int:
    kb_path = Path(kb_dir)
    if not kb_path.exists():
        log.warning("KB directory not found: %s", kb_dir)
        return 0

    docs = load_kb_files(kb_path)
    all_chunks = []
    all_ids = []
    all_meta = []

    for d in docs:
        chunks = chunk_text(d["text"], settings.chunk_size, settings.chunk_overlap)
        for i, ch in enumerate(chunks):
            cid = str(uuid.uuid4())
            all_ids.append(cid)
            all_chunks.append(ch)
            all_meta.append({
                "source": d["path"],
                "chunk_index": i,
            })

    if not all_chunks:
        log.warning("No KB chunks found to ingest.")
        return 0

    log.info("Embedding %d KB chunks...", len(all_chunks))
    vectors = embedder.embed(all_chunks)

    log.info("Adding to Chroma collection '%s'...", settings.chroma_collection)
    store.add_texts(all_ids, all_chunks, vectors, all_meta)

    return len(all_chunks)
