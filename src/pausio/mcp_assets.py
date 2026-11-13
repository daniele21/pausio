"""Agent asset operations, layered on existing Studio media import and edit reducer.

Only resources already attached to this project can be reused. New bytes
travel through Studio's existing bounded/validated import endpoints; no
arbitrary URL, local path, FFmpeg expression, file write or subprocess.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import re
import uuid
from typing import Any

MAX_AGENT_BYTES = 512 * 1024
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_AUDIO_SUFFIXES = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")
_NAME = re.compile(r"^[^/\\\x00-\x1f\x7f]{1,160}$")
_RIGHTS = frozenset({"created_for_user", "user_supplied", "licensed_by_user"})


class AssetToolError(ValueError):
    """Untrusted MCP asset request is rejected before touching Studio."""


def _number(value: Any, minimum: int, maximum: int, name: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise AssetToolError(f"{name} must be an integer in {minimum}..{maximum}")
    return value


def _fields(arguments: Any, required: set[str]) -> dict:
    if not isinstance(arguments, dict) or set(arguments) != required:
        raise AssetToolError("Missing or unknown media asset parameters")
    return arguments


def inventory(state: dict) -> dict:
    """Only media bound to current project, no raw bytes or private paths."""
    return {
        "media_id": state.get("media_id"),
        "project_revision": state.get("project_revision"),
        "images": [{
            "id": a["id"], "asset_sha256": a["asset_sha256"],
            "filename": a["filename"], "start_ms": a["start_ms"],
            "duration_ms": a["duration_ms"], "available": a.get("available", False),
            "x_pct": a["x_pct"], "y_pct": a["y_pct"], "width_pct": a["width_pct"],
        } for a in state.get("image_overlays") or []],
        "audio": [{
            "id": a["id"], "asset_sha256": a["asset_sha256"],
            "filename": a["filename"], "start_ms": a["start_ms"],
            "duration_ms": a["duration_ms"], "gain_db": a["gain_db"],
            "available": a.get("available", False),
        } for a in state.get("audio_clips") or []],
        "note": "Assets are project-local; thumbnails, audio samples, "
                "deleted items and external music catalogs are not exposed yet.",
    }


def decode_media(arguments: dict, kind: str) -> tuple[bytes, str]:
    """Transport-size cap below the MCP stdio line budget (~1MB)."""
    name = arguments["filename"]
    if (type(name) is not str or not _NAME.fullmatch(name) or
        not name.lower().endswith(_IMAGE_SUFFIXES if kind == "image" else _AUDIO_SUFFIXES)):
        raise AssetToolError("Invalid media filename or extension")
    if type(arguments["origin"]) is not str or arguments["origin"] not in _RIGHTS:
        raise AssetToolError("Declare generated, user-owned or licensed asset provenance")
    raw = arguments["data_base64"]
    if type(raw) is not str or not 4 <= len(raw) <= 4*((MAX_AGENT_BYTES+2)//3):
        raise AssetToolError("Media payload is empty or exceeds the 512 KiB MCP limit")
    try:
        payload = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AssetToolError("Invalid base64 media payload") from exc
    if not payload or len(payload)>MAX_AGENT_BYTES:
        raise AssetToolError("Media bytes exceed the 512 KiB MCP limit")
    return payload, name


def import_media(studio: Any, arguments: dict, kind: str) -> dict:
    if kind == "image":
        _fields(arguments, {"revision","filename","origin","data_base64","output_start_ms"})
        anchor=_number(arguments["output_start_ms"],0,172_800_000,"output_start_ms")
    elif kind == "audio":
        _fields(arguments, {"revision","filename","origin","data_base64","output_end_ms"})
        anchor=_number(arguments["output_end_ms"],0,172_800_000,"output_end_ms")
    else:
        raise AssetToolError("Unknown media type")
    revision=_number(arguments["revision"],0,2_147_483_647,"revision")
    payload,filename=decode_media(arguments,kind)
    digest=hashlib.sha256(payload).hexdigest()
    response=studio.import_binary(kind, payload, filename, revision, anchor)
    rows=response.get("image_overlays" if kind=="image" else "audio_clips") or []
    item=next((row for row in rows if row.get("asset_sha256")==digest),None)
    return {
        "kind":kind,"project_revision":response.get("project_revision"),
        "asset_sha256":digest,"asset_id":item.get("id") if item else None,
        "inserted":response.get("project_revision")==revision+1,
        "origin_declared":arguments["origin"],
        "note":"Imported through the same Studio media checks. Rights were "
               "declared by the caller, not independently verified.",
    }


def duplicate_media(studio: Any, arguments: dict, kind: str) -> dict:
    if kind=="image":
        _fields(arguments,{"revision","source_image_id","output_start_ms",
                           "duration_ms","x_pct","y_pct","width_pct"})
    elif kind=="audio":
        _fields(arguments,{"revision","source_clip_id","output_start_ms","gain_db"})
    else:
        raise AssetToolError("Unknown media type")
    revision=_number(arguments["revision"],0,2_147_483_647,"revision")
    state=studio.request("GET","/api/state")
    if not state.get("plan") or not state.get("media"):
        raise AssetToolError("Import and analyze a video in Studio first")
    if revision!=state.get("project_revision"):
        raise AssetToolError("Stale revision: refresh project and retry")
    if kind=="image":
        source_id=arguments["source_image_id"]
        rows=state.get("image_overlays") or []
        source=next((x for x in rows if x["id"]==source_id),None)
        if not source or source.get("available") is not True:
            raise AssetToolError("Referenced image is not available in this project")
        total=sum(s["end_ms"]-s["start_ms"] for s in state["plan"]["segments"])
        start=_number(arguments["output_start_ms"],0,total-1,"output_start_ms")
        duration=_number(arguments["duration_ms"],400,12000,"duration_ms")
        if start+duration>total:
            raise AssetToolError("Image exceeds edited output duration")
        image={key:source[key] for key in (
            "asset_sha256","filename","x_pct","y_pct","width_pct")}
        image.update({
            "id":uuid.uuid4().hex,"start_ms":start,"duration_ms":duration,
            "x_pct":_number(arguments["x_pct"],0,100,"x_pct"),
            "y_pct":_number(arguments["y_pct"],0,100,"y_pct"),
            "width_pct":_number(arguments["width_pct"],20,70,"width_pct"),
        })
        command="image.overlay.add"
        payload={"image":image}
        identity=image["id"]
    else:
        source_id=arguments["source_clip_id"]
        rows=state.get("audio_clips") or []
        source=next((x for x in rows if x["id"]==source_id),None)
        if not source or source.get("available") is not True:
            raise AssetToolError("Referenced audio is not available in this project")
        duration=state["media"]["duration_ms"]
        start=_number(arguments["output_start_ms"],0,duration-1,"output_start_ms")
        gain=_number(arguments["gain_db"],-36,12,"gain_db")
        clip={key:source[key] for key in ("asset_sha256","filename","duration_ms")}
        clip.update({"id":uuid.uuid4().hex,"start_ms":start,"gain_db":gain})
        command="audio.add"
        payload={"clip":clip}
        identity=clip["id"]
    changed=studio.request("POST","/api/command",{
        "revision":revision,"type":command,"payload":payload
    })
    return {
        "kind":kind,"asset_id":identity,
        "project_revision":changed.get("project_revision"),
        "last_command":changed.get("last_command"),
        "approved":changed.get("approved"),"preview_ready":changed.get("preview_ready"),
    }
