import os
import requests
from typing import List, Dict, Any
from app.core.config import settings
import os



class ChatClient:
    def __init__(self, api_url: str, model_name: str):
        self.api_url = api_url
        self.model_name = model_name

    def chat(self, system: str, user: str, temperature: float = 0.2, timeout: int = 900) -> str:
        headers = {"Content-Type": "application/json"}
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
        }

        resp = requests.post(
            self.api_url,
            json=payload,
            headers=headers,
            verify=settings.ssl_verify_path,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class EmbeddingsClient:
    def __init__(self, api_url: str, model_name: str, dims: int = 1024):
        self.api_url = api_url
        self.model_name = model_name
        self.dims = dims

    def embed(self, texts: List[str], input_type: str = "passage", timeout: int = 60) -> List[List[float]]:
        payload = {
            "model": self.model_name,
            "input": texts,
            "input_type": input_type,
            "dimensions": self.dims,
            "modality": "text",
        }
        headers = {"Content-Type": "application/json"}

        resp = requests.post(
            self.api_url,
            json=payload,
            headers=headers,
            verify=settings.ssl_verify_path,
            timeout=timeout,
        )

        if resp.status_code >= 400:
            raise requests.HTTPError(
                f"Embeddings error {resp.status_code}: {resp.text}",
                response=resp
            )

        data = resp.json()

        vecs = []
        for row in data.get("data", data.get("embeddings", [])):
            emb = row["embedding"] if isinstance(row, dict) else row
            vecs.append([float(x) for x in emb[: self.dims]])
        return vecs