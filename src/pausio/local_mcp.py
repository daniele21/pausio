"""Minimal, local-only MCP stdio bridge to a running Pausio Studio instance.

The external chat model is responsible for editorial decisions. This process
neither runs a model nor connects to a model API. It exposes a deliberately
small subset of Pausio's existing validated Studio operations. A separate,
authenticated remote gateway (not implemented here) is required for browser
chat products that cannot launch a local stdio connector.

This is a feasibility spike, not a public network server.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, TextIO

PROTOCOL_VERSION = "2025-03-26"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
EDIT_TYPES = frozenset({"segment.update", "caption.correct", "caption.configure",
                        "video.transform.add", "video.transform.update",
                        "video.transform.remove",
                        "video.transition.add", "video.transition.update",
                        "video.transition.remove"})

TOOLS: list[dict[str, Any]] = [
    {
        "name": "pausio_get_project",
        "description": "Read the selected local Pausio Studio project's media, edit timeline, captions, revision, and job state. Does not include transcript text or source video bytes.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "pausio_get_transcript",
        "description": "Read the existing Pausio local transcript with its real source timestamps. The chat model interprets the words; Pausio does not generate editorial judgments.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "pausio_get_job_status",
        "description": "Check the currently running/completed Studio job and whether a rendered preview is ready.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "pausio_suggest_visual_fx",
        "description": "Generate non-mutating, deterministic zoom proposals from real KEEP cut boundaries and available timestamped ASR phrases; never applies, renders or approves changes. Read-only technical candidates, not creative AI analysis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "revision": {"type": "integer", "minimum": 0},
                "preset": {"type": "string", "enum": ["naturale","educativo","dinamico","personalizzato"]},
            },
            "required": ["revision","preset"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "pausio_apply_command",
        "description": "Apply ONE existing, reviewed/typed Pausio edit to the active project at the exact expected revision. MVP allows captions, segment.update and validated video.transform.add/update/remove and video.transition.add/update/remove. All writes use the same Studio reducer; no final export. Invalidates approval/preview. Does NOT authorize final export.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "revision": {"type": "integer", "minimum": 0},
                "type": {"type": "string", "enum": sorted(EDIT_TYPES)},
                "payload": {"type": "object"},
            },
            "required": ["revision", "type", "payload"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False},
    },
    {
        "name": "pausio_start_pause_analysis",
        "description": "Ask Pausio to create its existing conservative silence-based cut proposal. This is technical pause detection, NOT creative video analysis; it is never silently approved.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": False},
    },
    {
        "name": "pausio_render_preview",
        "description": "Start asynchronous FFmpeg preview for the current edit plan. Does not export or approve final MP4; poll pausio_get_job_status.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": False},
    },
]


class MCPToolError(ValueError):
    """User-visible tool error without leaking server paths or private data."""


class StudioClient:
    def __init__(self, port: int):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("studio_port must be 1..65535")
        self._base = f"http://127.0.0.1:{port}"
        # A loopback MCP bridge must never obey proxy environment variables.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if method not in {"GET", "POST"} or path not in {
            "/api/state", "/api/command", "/api/jobs", "/api/visual-fx/suggest"
        }:
            raise MCPToolError("Unapproved Studio endpoint")
        if method == "GET" and payload is not None:
            raise MCPToolError("GET payload not allowed")
        if method == "POST" and not isinstance(payload, dict):
            raise MCPToolError("POST requires an object")
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers.update({"Content-Type": "application/json", "X-Pausio-Client": "studio"})
        req = urllib.request.Request(self._base + path, data=data, headers=headers, method=method)
        try:
            with self._opener.open(req, timeout=15) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            # Only bounded, known Studio validation error messages are returned.
            msg = "Studio rejected the request"
            try:
                detail = json.loads(exc.read(4096))
                if isinstance(detail, dict) and isinstance(detail.get("error"), str):
                    msg = detail["error"][:300]
            except (ValueError, UnicodeDecodeError, OSError):
                pass
            raise MCPToolError(msg) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MCPToolError("Pausio Studio is not reachable on the selected loopback port") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise MCPToolError("Studio response exceeds the MCP safety limit")
        try:
            result = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as exc:
            raise MCPToolError("Invalid JSON response from Pausio Studio") from exc
        if not isinstance(result, dict):
            raise MCPToolError("Unexpected Studio response")
        return result


def call_tool(name: str, arguments: dict, studio: StudioClient) -> dict:
    if not isinstance(arguments, dict):
        raise MCPToolError("Tool arguments must be an object")
    if name in {"pausio_get_project", "pausio_get_transcript", "pausio_get_job_status",
                "pausio_start_pause_analysis", "pausio_render_preview"} and arguments:
        raise MCPToolError("This tool does not accept arguments")
    if name == "pausio_get_project":
        state = studio.request("GET", "/api/state")
        # Deliberately exclude the raw transcript; opt-in via a separate tool.
        return {key: value for key, value in state.items() if key != "transcript"}
    if name == "pausio_get_transcript":
        state = studio.request("GET", "/api/state")
        if state.get("transcript") is None:
            raise MCPToolError("No transcript available; transcribe the video in Pausio Studio first")
        return {"media_id": state.get("media_id"), "transcript": state["transcript"]}
    if name == "pausio_get_job_status":
        state = studio.request("GET", "/api/state")
        return {"job": state.get("job"), "preview_ready": state.get("preview_ready"),
                "project_revision": state.get("project_revision")}
    if name == "pausio_suggest_visual_fx":
        if set(arguments) != {"revision", "preset"}:
            raise MCPToolError("Expected revision and visual FX preset")
        if (type(arguments["revision"]) is not int or arguments["revision"] < 0 or
            type(arguments["preset"]) is not str or
            arguments["preset"] not in ("naturale","educativo","dinamico","personalizzato")):
            raise MCPToolError("Invalid visual FX suggestion settings")
        return studio.request("POST", "/api/visual-fx/suggest", arguments)
    if name == "pausio_apply_command":
        if set(arguments) != {"revision", "type", "payload"}:
            raise MCPToolError("Expected exactly revision, type and payload")
        revision, kind, payload = arguments["revision"], arguments["type"], arguments["payload"]
        if type(revision) is not int or revision < 0 or not isinstance(kind, str) or kind not in EDIT_TYPES or not isinstance(payload, dict):
            raise MCPToolError("Unsupported or invalid typed edit command")
        state = studio.request("POST", "/api/command", arguments)
        return {"project_revision": state.get("project_revision"),
                "last_command": state.get("last_command"),
                "approved": state.get("approved"), "preview_ready": state.get("preview_ready")}
    if name == "pausio_start_pause_analysis":
        state = studio.request("POST", "/api/jobs", {"kind": "analyze"})
        return {"job": state.get("job"), "project_revision": state.get("project_revision")}
    if name == "pausio_render_preview":
        state = studio.request("POST", "/api/jobs", {"kind": "preview"})
        return {"job": state.get("job"), "preview_ready": state.get("preview_ready")}
    raise MCPToolError("Unknown Pausio tool")


def response_for(message: Any, studio: StudioClient) -> dict | None:
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid JSON-RPC request"}}
    if "id" not in message:  # notifications must never produce a response
        return None
    ident = message["id"]
    method, params = message.get("method"), message.get("params", {})
    if not isinstance(params, dict):
        return {"jsonrpc": "2.0", "id": ident,
                "error": {"code": -32602, "message": "Invalid params"}}
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "pausio-local-mcp", "version": "0.1.0-spike"},
            "instructions": "This connector is local-only. ChatGPT/Claude handle creative analysis. Pausio edits remain deterministic and require human approval before final export.",
        }
        return {"jsonrpc": "2.0", "id": ident, "result": result}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": ident, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": ident, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        try:
            result = call_tool(name, args, studio)
            return {"jsonrpc": "2.0", "id": ident, "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "structuredContent": result,
                "isError": False,
            }}
        except MCPToolError as exc:
            return {"jsonrpc": "2.0", "id": ident, "result": {
                "content": [{"type": "text", "text": str(exc)}], "isError": True
            }}
    return {"jsonrpc": "2.0", "id": ident,
            "error": {"code": -32601, "message": "Method not found"}}


def serve_stdio(port: int, input_stream: TextIO = sys.stdin,
                output_stream: TextIO = sys.stdout) -> None:
    studio = StudioClient(port)
    # MCP stdio protocol uses one JSON-RPC object per line; stdout is ONLY MCP.
    for line in input_stream:
        if len(line) > 1_000_000:
            output_stream.write(json.dumps({"jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Message too large"}}) + "\n")
            output_stream.flush()
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            output_stream.write(json.dumps({"jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Parse error"}}) + "\n")
            output_stream.flush()
            continue
        reply = response_for(message, studio)
        if reply is not None:
            output_stream.write(json.dumps(reply, ensure_ascii=False, separators=(",", ":")) + "\n")
            output_stream.flush()
