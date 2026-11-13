"""Agent-visible Pausio tool catalog, restricted to implemented Studio operations.

This is a declaration, not a second editor. Everything that changes a video
passes through the same versioned Studio project command reducer. File uploads
and human timeline approval deliberately remain in the Studio UI.
"""
from __future__ import annotations

from typing import Any

# A safe subset of existing UI commands. Never expose timeline.approve here.
# audio.add and image.overlay.add require physical asset import/relink in Studio.
EDIT_TYPES = frozenset({
    "segment.update", "segment.insert", "segment.remove",
    "timeline.keep_all", "timeline.restore_suggestion",
    "caption.set", "caption.correct", "caption.retime", "caption.style",
    "caption.configure", "caption.clear",
    "audio.update", "audio.remove", "audio.mixer.configure", "audio.clip.mix",
    "image.overlay.update", "image.overlay.remove",
    "graphic.overlay.add", "graphic.overlay.update", "graphic.overlay.remove",
    "video.transform.add", "video.transform.update", "video.transform.remove",
    "video.transition.add", "video.transition.update", "video.transition.remove",
})

# Explicit projection: Studio may add private internal fields in the future.
# Agent MCP reads only the fields needed for editing, never autosave paths.
PROJECT_FIELDS = frozenset({
    "version", "file", "media_id", "media", "approved", "project_revision",
    "editor_segments", "plan", "suggested_plan", "detected_silences",
    "analysis_settings", "captions", "caption_config", "audio_clips",
    "audio_mix", "video_fx", "video_transitions", "graphic_overlays",
    "image_overlays", "can_undo", "can_redo", "job", "preview_ready",
    "preview_range_ready", "preview_range_window", "export_ready",
})


def project_projection(state: dict[str, Any]) -> dict[str, Any]:
    """Copy only known editing metadata, not future private Studio internals."""
    return {key: state[key] for key in PROJECT_FIELDS if key in state}


_EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}


def _tool(name: str, description: str, schema: dict | None = None,
          *, read_only: bool = True) -> dict[str, Any]:
    return {"name": name, "description": description,
            "inputSchema": schema or _EMPTY,
            "annotations": {"readOnlyHint": read_only, "destructiveHint": False}}


TOOLS: list[dict[str, Any]] = [
    _tool("pausio_get_capabilities",
          "Discover exactly which local editing operations this MCP connector supports, "
          "what must be prepared in Studio and what is not implemented."),
    _tool("pausio_get_project",
          "Read the current Studio project: source SHA, revision, cuts, captions, "
          "video FX, graphic/image overlays, audio mix, approval and jobs. "
          "Excludes raw transcript. No video pixels or media files."),
    _tool("pausio_get_transcript",
          "Read the actual stored transcript with source timestamps, only when "
          "needed. This shares the transcript text with the connected chat client."),
    _tool("pausio_get_job_status",
          "Read asynchronous job status, preview/clip/export readiness and "
          "project revision. No media download."),
    _tool("pausio_suggest_visual_fx",
          "Read-only technical zoom suggestions from existing cut/ASR signals; "
          "does not apply any edit.",
          {"type": "object", "properties": {
              "revision": {"type": "integer", "minimum": 0},
              "preset": {"type": "string", "enum": [
                  "naturale", "educativo", "dinamico", "personalizzato"]}},
           "required": ["revision", "preset"], "additionalProperties": False}),
    _tool("pausio_suggest_editorial",
          "Read-only candidates for text graphics and camera moves from existing "
          "reviewed captions and real technical signals. Never auto-applies.",
          {"type": "object", "properties": {
              "revision": {"type": "integer", "minimum": 0},
              "preset": {"type": "string", "enum": [
                  "clean_tech", "educational", "dynamic_social"]}},
           "required": ["revision", "preset"], "additionalProperties": False}),
    _tool("pausio_apply_command",
          "Apply ONE reviewed deterministic project edit at exact revision. "
          "Includes cut edits, subtitle edits, camera movement, transitions, "
          "graphics, image position and audio mix. Only declared commands; "
          "Studio validates payload, media and project. Changes are undoable; "
          "NO automatic final approval or arbitrary file import.",
          {"type": "object", "properties": {
              "revision": {"type": "integer", "minimum": 0},
              "type": {"type": "string", "enum": sorted(EDIT_TYPES)},
              "payload": {"type": "object"}},
           "required": ["revision", "type", "payload"],
           "additionalProperties": False}, read_only=False),
    _tool("pausio_start_pause_analysis",
          "Run conservative technical silence analysis of imported video. "
          "The result needs human review.", read_only=False),
    _tool("pausio_start_transcription",
          "Start on-device Italian MLX Whisper transcription, cached weights ONLY; "
          "no implicit model downloads. Requires supported Apple Silicon setup.",
          read_only=False),
    _tool("pausio_render_preview",
          "Start whole edited-video FFmpeg preview (not final export); "
          "poll pausio_get_job_status.", read_only=False),
    _tool("pausio_preview_range",
          "Render exactly 250–10000 milliseconds of edited OUTPUT timeline using "
          "canonical FFmpeg effects, without prior full preview. Poll job status. "
          "This is not source time.",
          {"type": "object", "properties": {
              "range_start_ms": {"type": "integer", "minimum": 0},
              "range_duration_ms": {"type": "integer", "minimum": 250,
                                    "maximum": 10000}},
           "required": ["range_start_ms", "range_duration_ms"],
           "additionalProperties": False}, read_only=False),
    _tool("pausio_render_approved_video",
          "Render a local final MP4 ONLY AFTER the creator approved the timeline "
          "inside Pausio Studio. Does not approve edits, upload files or return "
          "video bytes. Download via Studio after job completes.", read_only=False),
]


def capabilities_report() -> dict[str, Any]:
    """Truthful current capabilities; never claim browser ChatGPT is connected."""
    return {
        "transport": "local_stdio_only",
        "tool_names": [item["name"] for item in TOOLS],
        "allowed_edit_commands": sorted(EDIT_TYPES),
        "source_video_import": "Studio UI only",
        "image_broll": "Existing imported PNG/JPG/WebP can be repositioned or removed "
                       "through typed commands; upload and relink via Studio UI",
        "graphic_cards": "Typed stat/title/code/tip cards and animations, using "
                         "graphic.overlay.add/update/remove",
        "audio": "Gain, mute and existing clip timing via typed commands; "
                 "import new music/FX in Studio UI",
        "preview": "Whole preview or short OUTPUT-timeline range",
        "final_render": "Requires a separate manual timeline approval inside Studio; "
                        "output stays on Mac",
        "transcription": "Local cached MLX Whisper only; no implicit model downloads",
        "unsupported": [
            "video B-roll files",
            "automatic B-roll asset selection",
            "direct raw-video/frame transfer from this connector to ChatGPT",
            "file upload from chat to Pausio",
            "unattended final approval",
            "public remote MCP connectivity",
        ],
        "model_inference": "No internal ChatGPT/Claude/API model: client decides edits",
    }
