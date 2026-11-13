"""Agent-visible Pausio tool catalog, restricted to implemented Studio operations.

This is a declaration, not a second editor. Everything that changes a video
passes through the same versioned Studio project command reducer. Small bounded asset uploads use Studio\'s existing validated media-import API;
human timeline approval stays in Studio.
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
    "scene.template.add", "scene.template.update", "scene.template.remove",
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
    "image_overlays", "scene_templates", "visual_sharing_enabled",
    "audio_sharing_enabled", "can_undo", "can_redo", "job", "preview_ready",
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
    _tool("pausio_list_assets",
          "List only images and audio clips already attached to the active project. "
          "Return IDs, digest, start, duration and availability, not local paths, "
          "image pixels or audio samples."),
    _tool("pausio_import_image",
          "Import a small PNG/JPEG/WebP image provided by the chat client as "
          "base64, insert it at the selected edited OUTPUT time, and create "
          "the canonical image.overlay.add event. Requires explicit caller "
          "authorization, declared provenance and revision; <=512 KiB. "
          "No URLs or local paths; origin is not verified by Pausio.",
          {"type":"object","properties":{
              "revision":{"type":"integer","minimum":0},
              "filename":{"type":"string","maxLength":160},
              "origin":{"type":"string","enum":[
                  "created_for_user","user_supplied","licensed_by_user"]},
              "data_base64":{"type":"string","description":
                  "Raw base64 media bytes, max decoded 524288 bytes"},
              "output_start_ms":{"type":"integer","minimum":0}},
           "required":["revision","filename","origin","data_base64","output_start_ms"],
           "additionalProperties":False}, read_only=False),
    _tool("pausio_import_audio",
          "Import a small user-supplied/licensed/generated MP3/WAV/etc audio "
          "file via verified local Studio import, with end position on edited "
          "output timeline. Audio START will be max(0,end-duration). "
          "The input file must be base64 <=512 KiB; no URL fetching.",
          {"type":"object","properties":{
              "revision":{"type":"integer","minimum":0},
              "filename":{"type":"string","maxLength":160},
              "origin":{"type":"string","enum":[
                  "created_for_user","user_supplied","licensed_by_user"]},
              "data_base64":{"type":"string","description":
                  "Raw base64 media bytes, max decoded 524288 bytes"},
              "output_end_ms":{"type":"integer","minimum":0}},
           "required":["revision","filename","origin","data_base64","output_end_ms"],
           "additionalProperties":False}, read_only=False),
    _tool("pausio_place_existing_image",
          "Reuse an already-imported, available project image at another edited "
          "OUTPUT timestamp with exact duration and position. New typed "
          "image.overlay.add instruction, same SHA-256 file, no upload.",
          {"type":"object","properties":{
              "revision":{"type":"integer","minimum":0},
              "source_image_id":{"type":"string"},
              "output_start_ms":{"type":"integer","minimum":0},
              "duration_ms":{"type":"integer","minimum":400,"maximum":12000},
              "x_pct":{"type":"integer","minimum":0,"maximum":100},
              "y_pct":{"type":"integer","minimum":0,"maximum":100},
              "width_pct":{"type":"integer","minimum":20,"maximum":70}},
           "required":["revision","source_image_id","output_start_ms",
                       "duration_ms","x_pct","y_pct","width_pct"],
           "additionalProperties":False}, read_only=False),
    _tool("pausio_place_existing_audio",
          "Reuse an already-imported, available music/FX asset at another "
          "OUTPUT timestamp with gain. Adds one deterministic audio.add "
          "clip referencing the same local bytes; original audio remains.",
          {"type":"object","properties":{
              "revision":{"type":"integer","minimum":0},
              "source_clip_id":{"type":"string"},
              "output_start_ms":{"type":"integer","minimum":0},
              "gain_db":{"type":"integer","minimum":-36,"maximum":12}},
           "required":["revision","source_clip_id","output_start_ms","gain_db"],
           "additionalProperties":False}, read_only=False),
    _tool("pausio_get_visual_context",
          "Return 1–4 actual bounded JPEG frames from the current source "
          "(source time), full FFmpeg preview (edited OUTPUT time), or short "
          "range preview (edited OUTPUT time). The creator MUST first enable "
          "visual sharing in local Pausio Studio; the agent cannot grant "
          "access. Requires current revision and media_id. Shares only "
          "selected stills, never full video or audio.",
          {"type":"object","properties":{
              "revision":{"type":"integer","minimum":0},
              "media_id":{"type":"string","pattern":"^[0-9a-f]{32}$"},
              "scope":{"type":"string","enum":["source","preview","range"]},
              "times_ms":{"type":"array","minItems":1,"maxItems":4,
                          "items":{"type":"integer","minimum":0}}},
           "required":["revision","media_id","scope","times_ms"],
           "additionalProperties":False}),
    _tool("pausio_get_audio_context",
          "Read one genuine 0.5–6 s 16 kHz mono WAV excerpt of the current "
          "source (SOURCE time) or a completed FFmpeg preview/range "
          "(EDITED OUTPUT time), after creator separately enables AUDIO "
          "sharing in local Studio. The agent cannot enable consent. "
          "One excerpt/call, max four calls/minute; includes real RMS "
          "and sample peak dBFS (not LUFS). This may share private speech "
          "with the chat provider.",
          {"type":"object","properties":{
              "revision":{"type":"integer","minimum":0},
              "media_id":{"type":"string","pattern":"^[0-9a-f]{32}$"},
              "scope":{"type":"string","enum":["source","preview","range"]},
              "start_ms":{"type":"integer","minimum":0},
              "duration_ms":{"type":"integer","minimum":500,"maximum":6000}},
           "required":["revision","media_id","scope","start_ms","duration_ms"],
           "additionalProperties":False}),
    _tool("pausio_get_scene_templates",
          "Discover bounded editable full-screen and split-screen scene templates "
          "(statistics, simulated permission, highlighted code and a creator "
          "plus animated dashboard with tasks, progress and budget). "
          "Return exact fields and defaults. Apply with scene.template.* "
          "commands through pausio_apply_command."),
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
        "image_broll": "Image overlays can be imported from <=512 KiB base64 "
                       "provided by the connected client, duplicated from current "
                       "project assets, repositioned and removed. PNG/JPG/WebP. "
                       "Studio UI supports larger images (up to 12 MiB).",
        "graphic_cards": "Typed stat/title/code/tip cards and animations, using "
                         "graphic.overlay.add/update/remove",
        "scene_templates": "Four output-timed scene templates (including creator "
                           "plus animated dashboard split-screen) via "
                           "scene.template.add/update/remove; consult "
                           "pausio_get_scene_templates for validated fields.",
        "audio": "Existing music/FX can be listed, duplicated at another output "
                 "time, mixed or muted. Small licensed/owned/generated audio "
                 "may be imported through bounded base64; large files use Studio UI.",
        "preview": "Whole preview or short OUTPUT-timeline range",
        "visual_observation": "Bounded JPEG frames (source or exact rendered "
                              "preview/range) through pausio_get_visual_context, "
                              "only after the creator opts in in Studio. "
                              "Max 4 frames/call and 12/min, 540x960; "
                              "does not include audio.",
        "audio_observation": "Actual 0.5–6s mono 16kHz WAV samples via "
                             "pausio_get_audio_context for source/real FFmpeg "
                             "preview. Opt in separately in Studio; 4/min; "
                             "RMS and peak dBFS (not integrated LUFS).",
        "final_render": "Requires a separate manual timeline approval inside Studio; "
                        "output stays on Mac",
        "transcription": "Local cached MLX Whisper only; no implicit model downloads",
        "unsupported": [
            "video B-roll files",
            "automatic B-roll asset selection",
            "whole-video/audio transfer or automatic sharing without separate user opt-in",
            "automatic retrieval of ChatGPT-generated file bytes or arbitrary URLs",
            "large (>512 KiB) MCP file import and remote media libraries",
            "unattended final approval",
            "public remote MCP connectivity",
        ],
        "asset_origin": "Required declaration when importing, not license verification. "
                        "External material must be cleared for usage rights.",
        "model_inference": "No internal ChatGPT/Claude/API model: client decides edits",
    }
