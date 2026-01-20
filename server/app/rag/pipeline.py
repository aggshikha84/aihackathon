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
from app.rag.mock_web_search import mock_web_search

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

def _preview(text: str, n: int = 300) -> str:
    t = (text or "").replace("\n", "\\n")
    return t[:n] + ("..." if len(t) > n else "")

def _needs_escalation(resp: AnalysisResponse) -> bool:
    if resp.status == "need_more_info":
        return True
    # weak plan: no commands
    if not resp.plan_steps:
        return True
    # very low confidence
    if resp.confidence == "low":
        return True
    return False
    

def analyze_log(
    log_text: str,
    store: ChromaVectorStore,
    embedder: EmbeddingsClient,
    llm: ChatClient,
) -> AnalysisResponse:
    # 1) truncate log for prompt safety
    log_text = truncate(log_text, settings.max_log_chars)

    # 2) embed query
    log.info("Embedding query (input_type=query)")
    qvec = embedder.embed([log_text])[0]
    log.info("Embedding done: vec_dim=%d", len(qvec))

    # 3) retrieve
    chroma_res = store.query(qvec, top_k=settings.top_k)
    contexts = _format_contexts(chroma_res)
    log.info("Retrieval: requested_top_k=%d got=%d", settings.top_k, len(contexts))

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
    log.info("Planner call: ctx_count=%d", len(contexts))
    plan_raw = llm.chat(
        system=PLANNER_SYSTEM,
        user=planner_prompt(log_text, contexts),
        temperature=0.2,
    )
    log.info("Planner raw length=%d preview='%s'", len(plan_raw or ""), _preview(plan_raw, 200))

    # 5) parse + validate
    try:
        plan_obj = _parse_json_strict(plan_raw)
        plan = AnalysisResponse.model_validate(plan_obj)
        log.info("Planner parsed: status=%s confidence=%s steps=%d info_requests=%d", plan.status, plan.confidence, len(plan.plan_steps), len(plan.info_requests))
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
    log.info("Critic call")
    critic_raw = llm.chat(
        system=CRITIC_SYSTEM,
        user=critic_prompt(log_text, contexts, plan_raw),
        temperature=0.2,
    )
    log.info("Critic raw length=%d preview='%s'", len(critic_raw or ""), _preview(critic_raw, 200))

    try:
        critic_obj = _parse_json_strict(critic_raw)
        reviewed = AnalysisResponse.model_validate(critic_obj)
        log.info("Critic parsed: status=%s confidence=%s steps=%d info_requests=%d", reviewed.status, reviewed.confidence, len(reviewed.plan_steps), len(reviewed.info_requests))

    except Exception:
        reviewed = plan

    # 7) safety checks
    reviewed = _safe_check(reviewed)

    # 8) OPTIONAL escalation: mock web search → replan once
    if settings.enable_mock_web_search and _needs_escalation(reviewed):
        
        log.warning("Escalating to MOCK WEB SEARCH (reason: weak plan or low evidence)")
        query = log_text[:800]
        log.info("Mock search query preview='%s'", _preview(query, 180))

        web_results = mock_web_search(query=query, top_k=settings.web_mock_top_k)
        log.info("Mock search results: count=%d", len(web_results))

        if web_results:
            # planner v2 with web results
            plan2_raw = llm.chat(
                system=PLANNER_SYSTEM,
                user=planner_prompt(log_text, contexts, web_results=web_results),
                temperature=0.2,
            )

            try:
                plan2_obj = _parse_json_strict(plan2_raw)
                #plan2_obj = _normalize_plan_obj(plan2_obj)  # if you added normalization
                plan2 = AnalysisResponse.model_validate(plan2_obj)
            except Exception:
                plan2 = reviewed  # fallback if v2 fails

            # critic v2
            critic2_raw = llm.chat(
                system=CRITIC_SYSTEM,
                user=critic_prompt(log_text, contexts, plan2_raw, web_results=web_results),
                temperature=0.2,
            )
            try:
                critic2_obj = _parse_json_strict(critic2_raw)
                #critic2_obj = _normalize_plan_obj(critic2_obj)
                reviewed2 = AnalysisResponse.model_validate(critic2_obj)
            except Exception:
                reviewed2 = plan2

            reviewed2 = _safe_check(reviewed2)
            log.info("Planner v2 parsed: status=%s confidence=%s steps=%d info_requests=%d", plan2.status, plan2.confidence, len(plan2.plan_steps), len(plan2.info_requests))


            # If v2 improved, return it; else keep original
            if not _needs_escalation(reviewed2):
                return reviewed2
            
            log.info("Analyze end: final_status=%s steps=%d info_requests=%d confidence=%s",reviewed.status, len(reviewed.plan_steps), len(reviewed.info_requests), reviewed.confidence)


    return reviewed

