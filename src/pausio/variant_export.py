"""All-or-nothing, offline ZIP export of three *approved* Pausio projects.

Reuses the same native FFmpeg compositor, caption remapping, FX, and local
media verification as Studio's single-video export. The ZIP is built in a private staging directory, validated and published
atomically only after all three MP4s are verified.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Callable
from zipfile import ZIP_STORED, ZipFile

from pausio.captions import remap_captions
from pausio.graphic_overlays import remap_graphics
from pausio.media import render, probe
from pausio.project_commands import ProjectTape
from pausio.variant_projects import STYLE_IDS, VariantWorkspace

BATCH_FILENAME = "pausio-three-variants.zip"


def render_three_approved(
    variants: VariantWorkspace, source: Path, media_info,
    target: Path, *,
    audio_asset: Callable[[str], Path],
    image_asset: Callable[[str, str], Path],
    video_asset: Callable[[str, str], Path],
    progress: Callable[[str, int], None] | None = None,
) -> None:
    """Render and atomically commit an entire three-MP4 ZIP, never a partial.

    The caller must serialize other Studio edits while this operation runs.
    All paths are local, and output archive names are a fixed allowlist.
    """
    if not isinstance(variants, VariantWorkspace):
        raise ValueError("Crea prima le tre varianti.")
    if not source.is_file() or source.is_symlink():
        raise ValueError("Video sorgente non disponibile o non sicuro.")
    if not target.parent.is_dir() or target.is_dir():
        raise ValueError("Cartella di esportazione non valida.")
    if any(not variants.tapes[k].view.approved for k in STYLE_IDS):
        raise ValueError("Conferma il montaggio di tutte e tre le varianti.")
    for key in STYLE_IDS:
        variants.tapes[key].require_media(
            sha256=variants.tapes[STYLE_IDS[0]].media["sha256"],
            duration_ms=media_info.duration_ms,
            has_audio=media_info.has_audio,
        )

    with tempfile.TemporaryDirectory(prefix=".pausio-three-export-", dir=target.parent) as staged:
        stage = Path(staged)
        archive = stage / BATCH_FILENAME
        names = set()
        with ZipFile(archive, "w", compression=ZIP_STORED, allowZip64=True) as dest:
            for index, style_id in enumerate(STYLE_IDS):
                tape: ProjectTape = variants.tapes[style_id]
                plan = tape.edit_plan(str(source))
                segment_index = {segment["id"]: i for i, segment in enumerate(tape.view.segments)}
                active_fx = [
                    {
                        "segment_index": segment_index[fx["segment_id"]],
                        **{k: v for k, v in fx.items() if k not in {"id", "segment_id"}},
                    }
                    for fx in tape.view.video_fx
                ]
                transitions = [
                    {
                        "boundary_index": segment_index[item["left_segment_id"]],
                        "kind": item["kind"],
                        "duration_ms": item["duration_ms"],
                    }
                    for item in tape.view.video_transitions
                ]
                audio = []
                for clip in tape.view.audio_clips:
                    path = audio_asset(clip["asset_sha256"])
                    if path.is_symlink() or not path.is_file():
                        raise ValueError("Effetto audio locale mancante o non sicuro.")
                    with path.open("rb") as handle:
                        digest = hashlib.file_digest(handle, "sha256").hexdigest()
                    if digest != clip["asset_sha256"]:
                        raise ValueError("Effetto audio modificato: reimporta l'originale.")
                    audio.append((path, dict(clip)))
                images = [
                    (image_asset(item["asset_sha256"], item["filename"]), dict(item))
                    for item in tape.view.image_overlays
                ]
                videos = [
                    (video_asset(clip["asset_sha256"], clip["filename"]), dict(clip))
                    for clip in tape.view.video_broll
                ]
                output = stage / f"pausio-{style_id.replace('_', '-')}.mp4"
                render(
                    source, output, plan.segments, has_audio=plan.has_audio,
                    size=(1080, 1920),
                    captions=remap_captions(tape.view.captions, plan.segments),
                    caption_style=tape.view.caption_style,
                    caption_config=tape.view.caption_config,
                    audio_fx=audio, audio_mix=dict(tape.view.audio_mix),
                    video_fx=active_fx, video_transitions=transitions,
                    graphic_overlays=remap_graphics(tape.view.graphic_overlays, plan.segments),
                    scene_templates=[dict(x) for x in tape.view.scene_templates],
                    image_overlays=images, video_broll=videos,
                )
                result = probe(output)
                if (not output.is_file() or output.stat().st_size == 0
                    or result.width != 1080 or result.height != 1920
                    or result.has_audio != plan.has_audio):
                    raise ValueError("Verifica MP4 non superata: " + style_id)
                dest.write(output, output.name)
                names.add(output.name)
                # MP4s are already compressed. Reclaim each large staging
                # file immediately instead of keeping 3 copies plus the ZIP.
                output.unlink()
                if progress:
                    progress(style_id, index + 1)
        with ZipFile(archive, "r") as check:
            if set(check.namelist()) != names or check.testzip() is not None:
                raise ValueError("Archivio ZIP incompleto o corrotto.")
        if archive.stat().st_size <= 0:
            raise ValueError("Esportazione multipla vuota.")
        os.replace(archive, target)
