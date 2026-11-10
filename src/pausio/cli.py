"""One simple local CLI; adapters and editing decisions remain separately testable."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from pausio import __version__
from pausio.domain import EditPlan, Interval
from pausio.media import MediaError, detect_silences, probe, render
from pausio.planner import AI_NATURAL, propose_segments


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pausio", description="Reviewable, local-first video editing for natural speech."
    )
    parser.add_argument("--version", action="version", version=f"pausio {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("doctor", help="Check FFmpeg/FFprobe availability")

    inspect_cmd = commands.add_parser("inspect", help="Inspect an input video with ffprobe")
    inspect_cmd.add_argument("input", type=Path)

    plan_cmd = commands.add_parser("plan", help="Propose a conservative, editable JSON edit plan")
    plan_cmd.add_argument("input", type=Path)
    plan_cmd.add_argument("--output", "-o", type=Path, required=True)
    plan_cmd.add_argument("--noise-db", type=int, default=-35)
    plan_cmd.add_argument("--overwrite", action="store_true")

    render_cmd = commands.add_parser("render", help="Render an approved plan with FFmpeg")
    render_cmd.add_argument("plan", type=Path)
    render_cmd.add_argument("--output", "-o", type=Path, required=True)
    render_cmd.add_argument("--overwrite", action="store_true")
    render_cmd.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            found = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
            print(_json({"version": __version__, "binaries": found, "ready": all(found.values())}), end="")
            return 0 if all(found.values()) else 2
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
    except (MediaError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"pausio: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
