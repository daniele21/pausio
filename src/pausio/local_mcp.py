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
from urllib.parse import quote
from typing import Any, TextIO

from pausio.mcp_tool_catalog import (EDIT_TYPES, TOOLS, capabilities_report,
                                      project_projection)
from pausio.scene_templates import catalog as scene_template_catalog
from pausio.mcp_assets import (AssetToolError, MAX_AGENT_BYTES, inventory,
                               import_media, duplicate_media)

PROTOCOL_VERSION = "2025-03-26"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


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
            "/api/state", "/api/command", "/api/jobs",
            "/api/visual-fx/suggest", "/api/editorial/suggest"
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

    def import_binary(self, kind: str, payload: bytes, filename: str,
                      revision: int, start_ms: int) -> dict:
        """Only the existing Studio's strictly bounded image/audio endpoints."""
        if (kind not in {"image", "audio"} or
            not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_AGENT_BYTES or
            type(revision) is not int or type(start_ms) is not int):
            raise MCPToolError("Unsafe media import request")
        path = "/api/image/import" if kind == "image" else "/api/audio/import"
        request = urllib.request.Request(
            self._base + path, data=payload, method="POST",
            headers={
                "Content-Type": "application/octet-stream",
                "Accept": "application/json",
                "X-Pausio-Client": "studio",
                "X-Filename": quote(filename, safe=""),
                "X-Pausio-Revision": str(revision),
                "X-Pausio-Start-Ms": str(start_ms),
            })
        try:
            with self._opener.open(request, timeout=90) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            try:
                message = json.loads(exc.read(4096)).get("error", "")
            except (ValueError, UnicodeDecodeError, OSError, AttributeError):
                message = ""
            raise MCPToolError(str(message)[:300] or "Studio rejected media import") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MCPToolError("Local Studio media import failed") from exc
        if len(raw) > MAX_RESPONSE_BYTES:
            raise MCPToolError("Studio response exceeds MCP safety limit")
        try:
            result = json.loads(raw)
        except (UnicodeDecodeError, ValueError) as exc:
            raise MCPToolError("Invalid Studio media response") from exc
        if not isinstance(result, dict):
            raise MCPToolError("Unexpected Studio media response")
        return result


def call_tool(name: str, arguments: dict, studio: StudioClient) -> dict:
    if not isinstance(arguments, dict):
        raise MCPToolError("Tool arguments must be an object")
    if name in {"pausio_get_scene_templates", "pausio_list_assets", "pausio_get_capabilities", "pausio_get_project",
                "pausio_get_transcript", "pausio_get_job_status",
                "pausio_start_pause_analysis", "pausio_start_transcription",
                "pausio_render_preview", "pausio_render_approved_video"} and arguments:
        raise MCPToolError("This tool does not accept arguments")
    if name == "pausio_get_capabilities":
        return capabilities_report()
    if name == "pausio_get_scene_templates":
        return {"templates": scene_template_catalog(), "timebase": "output",
                "min_duration_ms": 2500, "max_duration_ms": 12000,
                "max_scenes": 9, "audio": "Original voice and existing mix remain."}
    if name == "pausio_list_assets":
        return inventory(studio.request("GET", "/api/state"))
    if name == "pausio_import_image":
        return import_media(studio, arguments, "image")
    if name == "pausio_import_audio":
        return import_media(studio, arguments, "audio")
    if name == "pausio_place_existing_image":
        return duplicate_media(studio, arguments, "image")
    if name == "pausio_place_existing_audio":
        return duplicate_media(studio, arguments, "audio")
    if name == "pausio_get_project":
        state = studio.request("GET", "/api/state")
        # Deliberately exclude the raw transcript; opt-in via a separate tool.
        return project_projection(state)
    if name == "pausio_get_transcript":
        state = studio.request("GET", "/api/state")
        if state.get("transcript") is None:
            raise MCPToolError("No transcript available; transcribe the video in Pausio Studio first")
        return {"media_id": state.get("media_id"), "transcript": state["transcript"]}
    if name == "pausio_get_job_status":
        state = studio.request("GET", "/api/state")
        return {"job": state.get("job"), "preview_ready": state.get("preview_ready"),
                "preview_range_ready": state.get("preview_range_ready"),
                "preview_range_window": state.get("preview_range_window"),
                "export_ready": state.get("export_ready"),
                "approved": state.get("approved"),
                "media_id": state.get("media_id"),
                "project_revision": state.get("project_revision")}
    if name == "pausio_suggest_visual_fx":
        if set(arguments) != {"revision", "preset"}:
            raise MCPToolError("Expected revision and visual FX preset")
        if (type(arguments["revision"]) is not int or arguments["revision"] < 0 or
            type(arguments["preset"]) is not str or
            arguments["preset"] not in ("naturale","educativo","dinamico","personalizzato")):
            raise MCPToolError("Invalid visual FX suggestion settings")
        return studio.request("POST", "/api/visual-fx/suggest", arguments)
    if name == "pausio_suggest_editorial":
        if set(arguments) != {"revision", "preset"}:
            raise MCPToolError("Expected revision and editorial preset")
        if (type(arguments["revision"]) is not int or arguments["revision"] < 0 or
            type(arguments["preset"]) is not str or
            arguments["preset"] not in ("clean_tech", "educational", "dynamic_social")):
            raise MCPToolError("Invalid editorial suggestion settings")
        return studio.request("POST", "/api/editorial/suggest", arguments)
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
    if name == "pausio_start_transcription":
        # Studio validates defaults: local model cache only; no network opt-in.
        state = studio.request("POST", "/api/jobs", {"kind": "transcribe"})
        return {"job": state.get("job"), "project_revision": state.get("project_revision")}
    if name == "pausio_render_preview":
        state = studio.request("POST", "/api/jobs", {"kind": "preview"})
        return {"job": state.get("job"), "preview_ready": state.get("preview_ready")}
    if name == "pausio_preview_range":
        if set(arguments) != {"range_start_ms", "range_duration_ms"}:
            raise MCPToolError("Expected output timeline range in milliseconds")
        start, duration = arguments["range_start_ms"], arguments["range_duration_ms"]
        if (type(start) is not int or type(duration) is not int or
            start < 0 or not 250 <= duration <= 10_000):
            raise MCPToolError("Range must be 250..10000 ms inside edited output")
        state = studio.request("POST", "/api/jobs", {
            "kind": "preview_range", "range_start_ms": start,
            "range_duration_ms": duration,
        })
        return {"job": state.get("job"),
                "preview_range_ready": state.get("preview_range_ready"),
                "preview_range_window": state.get("preview_range_window"),
                "project_revision": state.get("project_revision")}
    if name == "pausio_render_approved_video":
        # This is NOT an approval shortcut: Studio start_job requires approved.
        state = studio.request("GET", "/api/state")
        if state.get("approved") is not True:
            raise MCPToolError("Conferma prima il montaggio dentro Pausio Studio.")
        result = studio.request("POST", "/api/jobs", {"kind": "render"})
        return {"job": result.get("job"), "export_ready": result.get("export_ready"),
                "message": "Il file finale resta sul Mac; scaricalo da Pausio Studio."}
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
        except (MCPToolError, AssetToolError) as exc:
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
