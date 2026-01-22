
import chainlit as cl
import uuid
from vector_store import FaissStore, load_and_chunk_file, DEFAULT_INDEX_DIR
import os
import textwrap
import requests
from typing import List, Dict, Optional
import asyncio
import html

INDEX_DIR = DEFAULT_INDEX_DIR

def _md_inline(s: str) -> str:
    """Sanitize so we don't accidentally open a code fence."""
    if not isinstance(s, str):
        s = str(s)
    s = html.unescape(s)         # decode &lt; &gt; &amp;
    s = s.replace("```", "ʼʼʼ")  # prevent fenced blocks
    return s.strip()

def render_plan_steps(steps):
    if not steps:
        return "_No plan steps provided._"
    out = []
    for step in steps:
        if isinstance(step, str):
            out.append(f"- {_md_inline(step)}")
        elif isinstance(step, dict):
            title = _md_inline(step.get("title") or step.get("name") or "Step")
            desc  = _md_inline(step.get("desc") or step.get("description") or "")
            cmd   = _md_inline(step.get("command") or "")
            line = f"- **{title}**"
            if desc:
                line += f": {desc}"
            if cmd:
                line += f"\n  - 🔧 Command: `{cmd}`"
            out.append(line)
        else:
            out.append(f"- {_md_inline(step)}")
    return "\n".join(out)

def render_info_requests(reqs):
    if not reqs:
        return "_No additional information requested._"
    out = []
    for r in reqs:
        title = _md_inline(r.get("title", "Request"))
        cmd   = _md_inline(r.get("command", ""))
        why   = _md_inline(r.get("why", ""))
        block = f"- **{title}**"
        if cmd:
            block += f"\n  - 🔧 Command: `{cmd}`"
        if why:
            block += f"\n  - 💡 Why: {why}"
        out.append(block)
    return "\n".join(out)

def render_summary(resp: dict) -> str:
    root_cause   = _md_inline(resp.get("root_cause") or "Unknown")
    plan_steps   = resp.get("plan_steps") or []
    info_reqs    = resp.get("info_requests") or []

    return (
        f"🔍 **Root Cause**\n"
        f"{root_cause}\n\n"
        f"🛠️ **Plan Steps**\n"
        f"{render_plan_steps(plan_steps)}\n\n"
        f"📋 **Information Needed**\n"
        f"{render_info_requests(info_reqs)}"
    )


class ChatSession:
    """
    In-memory conversation context for the current run only.
    Builds a compact 'Conversation Context' block and prepends it to the new user message,
    while keeping the FastAPI server API unchanged (still sending a single 'message' field).
    """

    def __init__(
        self,
        server_url: str = "http://10.60.90.11:30346",
        session_id: Optional[str] = None,
        max_turns_in_context: int = 10,      # sliding window of recent turns
        max_context_chars: int = 3500,       # upper bound for context header
        compress_threshold_chars: int = 2000,# when to compress past history
        include_assistant: bool = True,      # include both user & assistant in context
        non_streaming: bool = True,          # default to non-streaming server calls
        send_session_id: bool = True         # include session_id in payload if provided
    ):
        self.server_url = server_url.rstrip("/")
        self.session_id = session_id
        self.max_turns_in_context = max_turns_in_context
        self.max_context_chars = max_context_chars
        self.compress_threshold_chars = compress_threshold_chars
        self.include_assistant = include_assistant
        self.non_streaming = non_streaming
        self.send_session_id = send_session_id
        self.history: List[Dict[str, str]] = []  # [{"role": "user|assistant", "content": "..."}]

    # ---- Public API ---------------------------------------------------------
    
    def send(self, user_text: str) -> str:
        """
        Send a user message, with locally-constructed context prepended.
        Returns assistant reply (string). Mutates local history.
        """
        user_text = user_text.strip()
        if not user_text:
            return ""

        # Build compact context block from local history
        context_block = self._build_context_block()

        # Construct a single 'message' field for the server (unchanged API)
        final_message = self._combine_context_and_user(context_block, user_text)


        payload = {"log_text": final_message}
        if self.send_session_id and self.session_id:
            payload["session_id"] = self.session_id
        if self.non_streaming:
            payload["non_streaming"] = True

        # 1) Append local user message (for subsequent turns)
        self._append_history("user", user_text)

        # 2) Make the existing FastAPI call
        print(f"Sending payload: {payload}")
        resp = requests.post(f"{self.server_url}/analyze_text", json=payload, timeout=60)
        resp.raise_for_status()

        # Handle both streaming-disabled and custom server responses
        data = resp.json() if "application/json" in resp.headers.get("Content-Type", "") else {}
        # assistant_text = data.get("reply") or data.get("message") or data.get("text") or data.get("root_cause") or""
               
        print(f"Server reply: {data}")

        # root_cause = data.get("root_cause") or "Unknown"
        # plan_steps = data.get("plan_steps") or []
        # info_requests = data.get("info_requests") or []

        assistant_text = render_summary(data)

        # assistant_text = f"🔍 Root Cause: {root_cause}\n\n🛠️ Recommended Steps: {', '.join(plan_steps) if plan_steps else 'No plan steps provided.'}"
        print(f"Assistant reply: {assistant_text}")
        # 3) Append assistant reply locally
        if assistant_text:
            self._append_history("assistant", assistant_text)

        return assistant_text

    def reset(self):
        """Clear in-memory history for the current session."""
        self.history.clear()

    # ---- Internals ----------------------------------------------------------

    def _append_history(self, role: str, content: str):
        self.history.append({"role": role, "content": content})

    def _build_context_block(self) -> str:
        """
        Creates a compact context header from recent turns, trimming and compressing as needed.
        This is entirely local to the client and not stored server-side.
        """
        # Take the last N turns
        recent = self._take_recent(self.history, self.max_turns_in_context, include_assistant=self.include_assistant)

        # Format as conversation lines
        lines = []
        for m in recent:
            role = "User" if m["role"] == "user" else "Assistant"
            lines.append(f"{role}: {m['content'].strip()}")

        raw_context = "\n".join(lines).strip()

        if len(raw_context) <= self.compress_threshold_chars:
            compact = raw_context
        else:
            # Lightweight local compression (heuristic, no external LLM calls)
            compact = self._compress_lines(lines, target=self.compress_threshold_chars)

        # Enforce hard cap
        compact = compact[-self.max_context_chars:] if len(compact) > self.max_context_chars else compact

        if not compact:
            return ""

        header = (
            "### Conversation Context (local, current session only) ###\n"
            "The following lines summarize the most recent turns.\n"
            f"{compact}\n"
            "### End Context ###\n"
        )
        return header

    def _combine_context_and_user(self, context_block: str, user_text: str) -> str:
        """
        Concatenate the context block with the new user message in a clear structure,
        so the server (and its model) can utilize the context without any API changes.
        """
        if context_block:
            return f"{context_block}\nUser: {user_text}"
        return user_text

    @staticmethod
    def _take_recent(history: List[Dict[str, str]], max_turns: int, include_assistant: bool) -> List[Dict[str, str]]:
        if not history:
            return []
        if include_assistant:
            return history[-max_turns:]
        # Only user messages if excluding assistant
        user_only = [m for m in history if m["role"] == "user"]
        return user_only[-max_turns:]

    @staticmethod
    def _compress_lines(lines: List[str], target: int) -> str:
        """
        Heuristic compressor:
        1) Keep only the most recent lines first.
        2) Drop filler words and extra whitespace.
        3) Truncate long lines.
        """
        # Keep last K lines and progressively trim
        trimmed: List[str] = []
        max_line_len = 220
        fillers = {"okay", "ok", "thanks", "thank you", "cool", "great", "sure", "sounds good",
                   "got it", "awesome", "nice", "yeah", "yep", "uh", "um"}

        for line in reversed(lines):  # start from most recent
            core = " ".join(line.split())  # collapse whitespace
            low = core.lower()
            if any(low == f or low.endswith(f". {f}") for f in fillers):
                continue
            if len(core) > max_line_len:
                core = core[:max_line_len].rstrip() + "…"
            trimmed.append(core)
            joined = "\n".join(reversed(trimmed))
            if len(joined) >= target:
                break

        return "\n".join(reversed(trimmed))


def get_store():
    if not hasattr(get_store, "_store"):
        get_store._store = FaissStore(index_dir=INDEX_DIR)
    return get_store._store

server = os.getenv("CHAT_SERVER_URL", "http://10.60.90.11:30346")
session = ChatSession(
    server_url=server,
    session_id=os.getenv("CHAT_SESSION_ID", "local-dev"),  # optional
    max_turns_in_context=10,
    max_context_chars=3500,
    compress_threshold_chars=2000,
    include_assistant=True,
    non_streaming=True,
    send_session_id=True
)

@cl.on_chat_start
async def start():

    await cl.Message(content="Hi! Ask your questions.").send()

@cl.on_message
async def handle_message(message: cl.Message):
    q = (message.content or "").strip()
    if not q:
        await cl.Message(content="Please enter a query.").send()
        return

    loading = cl.Message(content="🔎 **Analyzing your request…** This may take a few seconds.")
    await loading.send()
    await asyncio.sleep(0)

    try:
        # Run the sync function in a thread to avoid blocking
        lines = await asyncio.to_thread(session.send, q)

        loading.content = "✅ **Completed.**"
        await loading.update()
        
        # await cl.Message(content=lines).send()

        await cl.Message(content="\n".join(lines) if isinstance(lines, list) else str(lines)).send()

    except Exception as e:
        loading.content = f"⚠️ **Failed:** {e}"
        await loading.update()
