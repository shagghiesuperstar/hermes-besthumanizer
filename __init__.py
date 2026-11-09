"""besthumanizer for Hermes Agent: three tools, spoken to a remote MCP server.

The plugin is a thin MCP client. Each tool call is one JSON-RPC ``tools/call``
against ``https://besthumanizer.app/mcp``, authenticated with a long-lived API
key, so what Hermes sees here is exactly what any other MCP client sees: no
separate REST dialect, no local scoring code to drift.

Two properties worth knowing, because they shape the tools:

*   **Scoring is deterministic.** Same text in, same number out, no model in the
    path, and it costs no words. ``score_text`` is safe to call freely.
*   **A rewrite never scores lower than its input.** The server measures before
    and after over the whole document and ships whichever of {your text, the
    mechanical pass, the model pass} reads most human. So ``humanize_text`` on
    text that already reads human hands your text back rather than making it
    worse — that is the contract, not a bug.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("besthumanizer.hermes")

PLUGIN = "besthumanizer"
DEFAULT_URL = "https://besthumanizer.app/mcp"
TIMEOUT_S = 300
_PROTOCOL = "2025-06-18"


# ---------------------------------------------------------------- transport


def _url() -> str:
    return os.environ.get("BESTHUMANIZER_URL", DEFAULT_URL).strip() or DEFAULT_URL


def _key() -> str:
    return os.environ.get("BESTHUMANIZER_API_KEY", "").strip()


def _available() -> bool:
    return bool(_key())


def _rpc(method: str, params: dict[str, Any] | None = None, _id: int = 1) -> dict[str, Any]:
    """One JSON-RPC round trip to the MCP endpoint."""
    body = json.dumps(
        {"jsonrpc": "2.0", "id": _id, "method": method, "params": params or {}}
    ).encode()
    req = urllib.request.Request(
        _url(),
        data=body,
        headers={
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "authorization": f"Bearer {_key()}",
            "user-agent": "hermes-besthumanizer/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        raw = resp.read().decode("utf-8", "replace")

    # Streamable HTTP may frame the answer as SSE; take the last data: line.
    if raw.lstrip().startswith(("event:", "data:")):
        payload = ""
        for line in raw.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
        raw = payload or raw
    return json.loads(raw)


def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """initialize + tools/call, returning the parsed tool payload."""
    try:
        _rpc("initialize", {"protocolVersion": _PROTOCOL, "capabilities": {},
                            "clientInfo": {"name": "hermes", "version": "1"}}, _id=1)
        out = _rpc("tools/call", {"name": name, "arguments": arguments}, _id=2)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 401:
            return {"error": "invalid API key",
                    "hint": "set BESTHUMANIZER_API_KEY to the key on https://besthumanizer.app/account"}
        return {"error": f"HTTP {exc.code}", "detail": detail}
    except Exception as exc:  # network, timeout, bad JSON
        return {"error": f"MCP call failed: {exc}"}

    if "error" in out:
        return {"error": out["error"].get("message", "rpc error") if isinstance(out["error"], dict) else out["error"]}

    result = out.get("result") or {}
    blocks = result.get("content") or []
    text = blocks[0].get("text", "") if blocks else ""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {"text": text, "is_error": bool(result.get("isError"))}


# ------------------------------------------------------------------- tools

HUMANIZE_DESCRIPTION = (
    "Rewrite text that reads machine-written so it reads like a person wrote it, and return "
    "honest scores for what went in and what came out. Removes AI tells (inflated significance, "
    "the tell-word lexicon, filler, connective tics, nominalisation), then runs a constrained "
    "model pass and re-scans. Guaranteed not to return text that scores lower than the input. "
    "Debits the input word count from the account's monthly allowance."
)

HUMANIZE_SCHEMA = {
    "name": "humanize_text",
    "description": HUMANIZE_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "text to rewrite (up to 10,000 words)"},
            "mode": {"type": "string", "enum": ["general", "academic"],
                     "description": "register of the output: general prose or academic writing"},
            "premium": {"type": "boolean", "default": False,
                        "description": "second pass on the larger model; slower and metered higher on some plans"},
            "voice_sample": {"type": "string",
                             "description": "optional sample of the author's writing to match cadence against"},
        },
        "required": ["text"],
    },
}

SCORE_DESCRIPTION = (
    "Score how machine-written a passage reads, 0-100 where higher is more human, and list the "
    "specific patterns found with the span that triggered each one. Deterministic: same text, same "
    "number, no model, no words debited. Use before and after any rewrite to prove it helped."
)

SCORE_SCHEMA = {
    "name": "score_text",
    "description": SCORE_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "passage to measure"}},
        "required": ["text"],
    },
}

XSCORE_DESCRIPTION = (
    "Score a public X account's recent original posts for how machine-written they read: median "
    "score, the distribution, and the individual posts that carry the tells. Deterministic, free, "
    "and returns a shareable link that unfurls with the verdict."
)

XSCORE_SCHEMA = {
    "name": "score_x_account",
    "description": XSCORE_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "handle": {"type": "string", "description": "X handle, with or without the leading @"},
            "limit": {"type": "integer", "default": 25, "description": "how many recent posts to score (5-50)"},
        },
        "required": ["handle"],
    },
}


def humanize_text(text: str = "", mode: str = "general", premium: bool = False,
                  voice_sample: str = "", **_: Any) -> dict[str, Any]:
    if not str(text).strip():
        return {"error": "text is required"}
    args: dict[str, Any] = {"text": text, "mode": mode or "general", "premium": bool(premium)}
    if voice_sample:
        args["voice_sample"] = voice_sample
    return _call_tool("humanize", args)


def score_text(text: str = "", **_: Any) -> dict[str, Any]:
    if not str(text).strip():
        return {"error": "text is required"}
    return _call_tool("score_text", {"text": text})


def score_x_account(handle: str = "", limit: int = 25, **_: Any) -> dict[str, Any]:
    handle = str(handle).lstrip("@").strip()
    if not handle:
        return {"error": "handle is required"}
    return _call_tool("score_x_account", {"handle": handle, "limit": int(limit or 25)})


# ---------------------------------------------------------------- manifest

def register(ctx) -> None:
    for name, schema, handler, emoji in (
        ("humanize_text", HUMANIZE_SCHEMA, humanize_text, "✍️"),
        ("score_text", SCORE_SCHEMA, score_text, "🔍"),
        ("score_x_account", XSCORE_SCHEMA, score_x_account, "📊"),
    ):
        ctx.register_tool(name=name, toolset=PLUGIN, schema=schema, handler=handler,
                          check_fn=_available, emoji=emoji)
    try:
        ctx.register_skill(PLUGIN, Path(__file__).with_name("SKILL.md"),
                           description="When to humanize, when to just score, and how to prove a rewrite helped.")
    except Exception as exc:  # a Hermes build without skills must still get the tools
        log.warning("besthumanizer: could not register the skill: %s", exc)
