#!/usr/bin/env python3
"""Offline visual proof of concept: count-up scene, no private video or new runtime.

Run in the Pausio editable checkout:
    python scripts/demo_metric_motion.py --output /tmp/pausio-metric-demo.mp4
Requires FFmpeg with libass, just like existing Pausio burned-in captions.
This is NOT a Studio template or a production video export.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

from pausio.captions import ass_document
from pausio.editorial_cards import _Canvas
from pausio.motion_metric import compose_counter_events
from pausio.scene_templates import _event, _safe

SCENE_STYLE = (
    "Style: Scene,Arial,64,&H00FFFFFF,&H00FFFFFF,&H00000000,"
    "&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,40,40,0,1\n"
)


def create_ass(duration_ms: int = 3200) -> str:
    if type(duration_ms) is not int or not 2400 <= duration_ms <= 7000:
        raise ValueError("La demo richiede una durata di 2400–7000 ms.")
    scene = {"start_ms": 0, "duration_ms": duration_ms, "accent": "orange"}
    canvas = _Canvas(scene, _event, _safe)
    # A custom prototype layout assembled from current Pausio drawing primitives.
    # All label strings are synthetic. No online claim or fake screenshot.
    canvas.panel(0, 0, 1080, 1920, color="#0C1623", shadow=False, radius=2)
    canvas.panel(88, 145, 904, 8, color="#E88852", radius=4, shadow=False)
    canvas.badge("DEMO", 95, 234, 185, color="#E88852", dark=True)
    canvas.type("UN NUMERO, UN MESSAGGIO", 540, 460, 51, "#F8FAFC", delay=110)
    canvas.parts.append(compose_counter_events(
        "1.379", 440, duration_ms, _event, _safe,
        x=540, y=840, size=188, color="#FFB28C",
    ))
    canvas.type("ELEMENTI", 540, 1080, 77, "#FFFFFF", delay=760)
    canvas.panel(122, 1200, 836, 3, color="#344255",
                 radius=1, shadow=False, delay=850)
    canvas.type("Esempio sintetico di componente data-driven",
                540, 1350, 36, "#ADC1D1", delay=980, weight=False)
    canvas.type("PROTOTIPO · DATI ILLUSTRATIVI",
                540, 1670, 26, "#ADC1D1", delay=1000, weight=False)

    base = ass_document([], style="minimal")
    return base.replace("[Events]\n", SCENE_STYLE + "[Events]\n", 1) + canvas.output()


def render(output: Path, duration_ms: int = 3200) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg non disponibile nel PATH.")
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pausio_metric_demo_") as directory:
        ass_path = Path(directory) / "metric.ass"
        ass_path.write_text(create_ass(duration_ms), encoding="utf-8")
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i",
            f"color=c=0x0C1623:s=540x960:r=30:d={duration_ms / 1000}",
            "-vf", f"ass=filename={ass_path.as_posix()}",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(output),
        ]
        subprocess.run(command, check=True, timeout=120)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.output)
    print(f"Motion Graphics prototype: {args.output.resolve()}")


if __name__ == "__main__":
    main()
