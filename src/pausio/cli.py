"""One simple local CLI; adapters and editing decisions remain separately testable."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from pausio import __version__
from pausio.local_asr import LocalASRError, DEFAULT_ASR_MODEL, transcribe_video_local
from pausio.domain import EditPlan, Interval
from pausio.media import MediaError, detect_silences, probe, render, select_ffmpeg_for_filter
from pausio.planner import AI_NATURAL, propose_segments
from pausio.studio import run_studio
from pausio.local_mcp import serve_stdio


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pausio", description="Reviewable, local-first video editing for natural speech."
    )
    parser.add_argument("--version", action="version", version=f"pausio {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="Check FFmpeg/FFprobe and libass subtitle support")
    studio_cmd = commands.add_parser("studio", help="Open the local Pausio Studio UI")
    studio_cmd.add_argument(
        "--port", type=int, default=8765,
        help="Porta TCP iniziale (default: 8765); se occupata prova +1, +2, ..."
    )
    studio_cmd.add_argument("--no-open", action="store_true")
    studio_cmd.add_argument("--data-dir", type=Path, help="Private local Studio autosave folder")

    mcp_cmd = commands.add_parser("mcp", help="Run local-only MCP stdio bridge to an already running Pausio Studio")
    mcp_cmd.add_argument("--studio-port", type=int, default=8765, help="Actual Studio loopback port (auto-selected port may differ)")

    inspect_cmd = commands.add_parser("inspect", help="Inspect an input video with ffprobe")
    inspect_cmd.add_argument("input", type=Path)

    plan_cmd = commands.add_parser("plan", help="Propose a conservative, editable JSON edit plan")
    plan_cmd.add_argument("input", type=Path)
    plan_cmd.add_argument("--output", "-o", type=Path, required=True)
    plan_cmd.add_argument("--noise-db", type=int, default=-35)
    plan_cmd.add_argument("--overwrite", action="store_true")

    transcript_cmd = commands.add_parser(
        "transcribe", help="Transcribe with standalone MLX Whisper, without ClosedRoom"
    )
    transcript_cmd.add_argument("input", type=Path)
    transcript_cmd.add_argument("--output", "-o", type=Path, required=True)
    transcript_cmd.add_argument("--language", default="it")
    transcript_cmd.add_argument("--model", default=DEFAULT_ASR_MODEL)
    transcript_cmd.add_argument(
        "--allow-model-download", action="store_true",
        help="Explicitly authorize downloading a missing MLX model from Hugging Face"
    )
    transcript_cmd.add_argument("--overwrite", action="store_true")

    render_cmd = commands.add_parser("render", help="Render an approved plan with FFmpeg")
    render_cmd.add_argument("plan", type=Path)
    render_cmd.add_argument("--output", "-o", type=Path, required=True)
    render_cmd.add_argument("--overwrite", action="store_true")
    render_cmd.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "studio":
            run_studio(port=args.port, open_browser=not args.no_open, data_dir=args.data_dir)
            return 0
        if args.command == "mcp":
            serve_stdio(port=args.studio_port)
            return 0
        if args.command == "doctor":
            found = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
            details = []
            captions_binary = select_ffmpeg_for_filter("ass") if found["ffmpeg"] else None
            subtitles_ready = captions_binary is not None
            if not subtitles_ready:
                details.append(
                    "Il filtro ass manca: su macOS usa 'brew install ffmpeg-full' "
                    "e riavvia Pausio. Verificheremo automaticamente la build libass "
                    "di Homebrew anche se non è la prima nel PATH. libass da sola non basta."
                )
            ready = all(found.values()) and subtitles_ready
            print(_json({
                "version": __version__, "binaries": found,
                "captions_ffmpeg": captions_binary,
                "captions_ass": subtitles_ready, "ready": ready,
                "warnings": details,
            }), end="")
            return 0 if ready else 2
        if args.command == "inspect":
            print(_json(probe(args.input.resolve()).as_dict()), end="")
            return 0
        if args.command == "plan":
            source = args.input.resolve()
            metadata = probe(source)
            if args.output.resolve() == source:
                raise ValueError("do not overwrite the source video")
            if args.output.exists() and not args.overwrite:
                raise ValueError("plan already exists; use --overwrite")
            silence = (
                detect_silences(source, metadata.duration_ms, noise_db=args.noise_db)
                if metadata.has_audio else []
            )
            segments = propose_segments(metadata.duration_ms, silence, AI_NATURAL)
            plan = EditPlan(
                source=str(source), source_duration_ms=metadata.duration_ms,
                has_audio=metadata.has_audio, segments=segments,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(_json(plan.as_dict()), encoding="utf-8")
            print(_json({
                "plan_file": str(args.output), "detected_silences": len(silence),
                "keep_segments": len(segments), "original_ms": metadata.duration_ms,
                "proposed_ms": plan.output_duration_ms,
                "review_required": True,
                "note": "Silence-based suggestions only; inspect the JSON before rendering.",
            }), end="")
            return 0
        if args.command == "transcribe":
            source = args.input.resolve()
            output = args.output.resolve()
            if source == output:
                raise ValueError("source video and transcript output must differ")
            if output.exists() and not args.overwrite:
                raise ValueError("transcript already exists; pass --overwrite")
            transcript = transcribe_video_local(
                source, language=args.language, model=args.model,
                allow_model_download=args.allow_model_download
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".pausio-", dir=output.parent) as temp:
                staged = Path(temp) / "transcript.json"
                staged.write_text(_json(transcript), encoding="utf-8")
                if output.exists() and not args.overwrite:
                    raise ValueError("transcript appeared during processing")
                staged.replace(output)
            print(_json({
                "transcript_file": str(output),
                "segments": len(transcript["segments"]),
                "word_timestamps_available": transcript["word_timestamps_available"],
                "provider": transcript["provider"],
                "review_required": True,
            }), end="")
            return 0
        if args.command == "render":
            raw = json.loads(args.plan.read_text(encoding="utf-8"))
            plan = EditPlan.from_dict(raw)
            source = plan.resolved_source(args.plan.resolve())
            # Guard against a plan edited to span beyond the actual video.
            metadata = probe(source)
            if plan.source_duration_ms > metadata.duration_ms + 100:
                raise ValueError("plan duration exceeds current source; regenerate the plan")
            if plan.has_audio != metadata.has_audio:
                raise ValueError("source audio changed; regenerate the plan")
            command = render(
                source, args.output.resolve(), plan.segments, has_audio=plan.has_audio,
                overwrite=args.overwrite, dry_run=args.dry_run,
            )
            print(_json({
                "mode": "dry-run" if args.dry_run else "rendered",
                "output": str(args.output), "duration_ms": plan.output_duration_ms,
                **({"command": command} if args.dry_run else {}),
            }), end="")
            return 0
        raise ValueError(f"unknown command: {args.command}")
    except (MediaError, LocalASRError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"pausio: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
