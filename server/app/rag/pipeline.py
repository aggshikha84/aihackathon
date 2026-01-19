import json
import logging
from typing import Any, Dict, List

from pydantic import ValidationError

from app.core.config import settings
from app.llm.clients import ChatClient, EmbeddingsClient
from app.rag.vectorstore import ChromaVectorStore
from app.rag.prompts import PLANNER_SYSTEM, CRITIC_SYSTEM, planner_prompt, critic_prompt
from app.schemas.models import AnalysisResponse
from app.utils.text import truncate
from app.utils.safety import is_command_dangerous

log = logging.getLogger("pipeline")

def _format_contexts(chroma_result: Dict[str, Any]) -> List[dict]:
    # Chroma query returns lists (batch size 1)
    docs = chroma_result.get("documents", [[]])[0]
    metas = chroma_result.get("metadatas", [[]])[0]
    dists = chroma_result.get("distances", [[]])[0]

    contexts = []
    for doc, meta, dist in zip(docs, metas, dists):
        contexts.append({
            "text": doc,
            "source": meta.get("source", "unknown"),
            "chunk_index": meta.get("chunk_index", -1),
            "distance": dist,
        })
    return contexts

def _safe_check(response: AnalysisResponse) -> AnalysisResponse:
    # If any step has a dangerous command, downgrade and request human review / more info
    for step in response.plan_steps:
        if is_command_dangerous(step.command):
            response.status = "need_more_info"
            response.info_requests.append({
                "title": "Unsafe command detected",
                "command": "N/A",
                "why": f"Generated command looks unsafe: {step.command}. Please review and provide safer constraints.",
            })
            response.plan_steps = []
            return response
    return response

def _parse_json_strict(text: str) -> dict:
    # Many LLMs sometimes wrap JSON with stray text. Minimal hardening:
    t = (text or "").strip()
    # try direct parse first
    try:
        return json.loads(t)
    except Exception:
        # attempt to extract first {...} block
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(t[start:end+1])
        raise

def analyze_log(
    log_text: str,
    store: ChromaVectorStore,
    embedder: EmbeddingsClient,
    llm: ChatClient,
) -> AnalysisResponse:
    # 1) truncate log for prompt safety
    log_text = truncate(log_text, settings.max_log_chars)

    # 2) embed query
    qvec = embedder.embed([log_text])[0]

    # 3) retrieve
    chroma_res = store.query(qvec, top_k=settings.top_k)
    contexts = _format_contexts(chroma_res)

    # Optionally truncate contexts used in prompt
    ctx_chars = 0
    trimmed = []
    for c in contexts:
        t = c["text"]
        if ctx_chars + len(t) > settings.max_context_chars:
            break
        trimmed.append(c)
        ctx_chars += len(t)
    contexts = trimmed

    # 4) planner call
    plan_raw = llm.chat(
        system=PLANNER_SYSTEM,
        user=planner_prompt(log_text, contexts),
        temperature=0.2,
    )

    # 5) parse + validate
    try:
        plan_obj = _parse_json_strict(plan_raw)
        plan = AnalysisResponse.model_validate(plan_obj)
    except (ValidationError, Exception) as e:
        # If planner fails, return need_more_info minimal
        log.exception("Planner output parse/validate failed.")
        return AnalysisResponse(
            status="need_more_info",
            root_cause="Unable to generate a valid plan from the provided log.",
            confidence="low",
            reasoning_summary=f"Planner returned non-parseable output. Error: {type(e).__name__}",
            evidence=[],
            plan_steps=[],
            info_requests=[
                {
                    "title": "Provide more context",
                    "command": "Provide full pod name/namespace and 200 lines around the error, plus 'kubectl describe pod ...'",
                    "why": "Current log excerpt is insufficient or malformed for planning.",
                }
            ],
        )

    # 6) critic call (optional second LLM call)
    critic_raw = llm.chat(
        system=CRITIC_SYSTEM,
        user=critic_prompt(log_text, contexts, plan_raw),
        temperature=0.2,
    )

    try:
        critic_obj = _parse_json_strict(critic_raw)
        reviewed = AnalysisResponse.model_validate(critic_obj)
    except Exception:
        # If critic fails, fall back to planner output
        reviewed = plan

    # 7) safety checks
    reviewed = _safe_check(reviewed)

    return reviewed
