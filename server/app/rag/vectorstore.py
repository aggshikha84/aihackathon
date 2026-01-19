from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings as ChromaSettings
from app.core.config import settings

class ChromaVectorStore:
    def __init__(self):
        self.client = chromadb.Client(
            ChromaSettings(
                anonymized_telemetry=False,
                is_persistent=False,  # in-memory for hackathon
            )
        )
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection
        )

    def add_texts(self, ids: List[str], texts: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]]):
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(self, query_embedding: List[float], top_k: int) -> Dict[str, Any]:
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
