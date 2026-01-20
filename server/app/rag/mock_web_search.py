from pathlib import Path
from typing import List, Dict, Any
import re

DEFAULT_WEB_MOCK_DIR = Path("data/web_mock")

def _tokenize(q: str) -> List[str]:
    q = (q or "").lower()
    q = re.sub(r"[^a-z0-9\s\-/_.:]", " ", q)
    toks = [t for t in q.split() if len(t) >= 3]
    return toks[:25]

def _score(text: str, tokens: List[str]) -> int:
    t = (text or "").lower()
    score = 0
    for tok in tokens:
        # count token occurrences (simple + stable for hackathon)
        score += t.count(tok)
    return score

def mock_web_search(query: str, top_k: int = 3, web_dir: Path = DEFAULT_WEB_MOCK_DIR) -> List[Dict[str, Any]]:
    """
    Offline 'web search' over local markdown files.
    Returns list of dicts: {title, snippet, source, score}
    """
    tokens = _tokenize(query)
    if not tokens:
        return []

    results = []
    if not web_dir.exists():
        return []

    for p in sorted(web_dir.glob("*.md")):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        s = _score(txt, tokens)
        if s <= 0:
            continue

        title = p.stem.replace("_", " ")
        snippet = txt.strip().splitlines()
        snippet = "\n".join(snippet[:12])[:800]  # short snippet

        results.append({
            "title": title,
            "snippet": snippet,
            "source": str(p),
            "score": s,
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
