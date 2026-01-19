PLANNER_SYSTEM = """You are a senior Kubernetes SRE assistant.
You must produce an actionable incident analysis and a safe execution plan.
Return ONLY valid JSON (no markdown, no extra text)."""

CRITIC_SYSTEM = """You are a strict reviewer of incident response plans.
Check the plan for: correctness, specificity, safety, and whether it is grounded in the provided log/context.
Return ONLY valid JSON (no markdown, no extra text)."""

def planner_prompt(log_text: str, contexts: list[dict]) -> str:
    # contexts: [{text, source, distance}, ...]
    ctx_block = []
    for c in contexts:
        ctx_block.append(
            f"- SOURCE: {c.get('source')}\n"
            f"  DISTANCE: {c.get('distance')}\n"
            f"  TEXT: {c.get('text')}\n"
        )
    ctx_str = "\n".join(ctx_block)

    return f"""
You are given:
1) A log excerpt from a Kubernetes incident
2) Retrieved knowledge base snippets (may include runbooks / common fixes)

TASK:
- Identify likely root cause (RCA)
- Provide confidence: high/medium/low
- Provide an ordered plan with concrete commands (safe + realistic)
- If you cannot provide clear commands, set status="need_more_info" and list what info is needed (commands to collect more evidence)

OUTPUT JSON SCHEMA (STRICT):
{{
  "status": "final" | "need_more_info",
  "root_cause": "...",
  "confidence": "high" | "medium" | "low",
  "reasoning_summary": "...",
  "evidence": [{{"type":"log|kb","snippet":"...","source":"..."}}],
  "plan_steps": [{{"title":"...","command":"...","purpose":"...","expected":"...","risk":"low|med|high"}}],
  "info_requests": [{{"title":"...","command":"...","why":"..."}}]
}}

LOG:
\"\"\"{log_text}\"\"\"

RETRIEVED KB SNIPPETS:
{ctx_str}

Return ONLY JSON.
""".strip()


def critic_prompt(log_text: str, contexts: list[dict], plan_json: str) -> str:
    ctx_block = []
    for c in contexts:
        ctx_block.append(
            f"- SOURCE: {c.get('source')}\n"
            f"  DISTANCE: {c.get('distance')}\n"
            f"  TEXT: {c.get('text')}\n"
        )
    ctx_str = "\n".join(ctx_block)

    return f"""
Review the proposed plan. Verify:
- Is it specific and executable?
- Are commands present and safe?
- Is RCA grounded in log + KB snippets?
- If unclear, change status to "need_more_info" and add 3-8 info_requests with precise commands.
- If commands are dangerous, replace with safer alternatives and set risk accordingly.

Return JSON with SAME schema as planner output.

LOG:
\"\"\"{log_text}\"\"\"

RETRIEVED KB SNIPPETS:
{ctx_str}

PROPOSED PLAN JSON:
{plan_json}

Return ONLY JSON.
""".strip()
