"""Typed local image PIP/B-roll references; no external URLs or user filtergraphs.

Image bytes remain in the private Studio workspace. Portable projects keep the
asset's SHA-256, a display filename and exact output-timeline placement only.
"""
from __future__ import annotations

import re
from typing import Any

MAX_IMAGE_OVERLAYS = 4
MAX_IMAGE_BYTES = 12 * 1024 * 1024
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
IMAGE_FIELDS = frozenset({
    "id", "asset_sha256", "filename", "start_ms", "duration_ms",
    "x_pct", "y_pct", "width_pct"
})
_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def validate_image_overlay(raw: Any, output_ms: int) -> dict:
    if type(output_ms) is not int or not 0 < output_ms <= 172_800_000:
        raise ValueError("Durata montata non valida per le immagini.")
    if not isinstance(raw, dict) or set(raw) != IMAGE_FIELDS:
        raise ValueError("Immagine PIP: campi sconosciuti o mancanti.")
    if (not isinstance(raw["id"], str) or not _HEX32.fullmatch(raw["id"]) or
        not isinstance(raw["asset_sha256"], str) or
        not _HEX64.fullmatch(raw["asset_sha256"])):
        raise ValueError("Immagine PIP: ID o digest non valido.")
    filename = raw["filename"]
    if (not isinstance(filename, str) or not 1 <= len(filename) <= 160 or
        "/" in filename or "\\" in filename or filename in {".", ".."} or
        any(ord(ch)<32 or ord(ch)==127 for ch in filename) or
        not any(filename.lower().endswith(ext) for ext in IMAGE_EXTENSIONS)):
        raise ValueError("Immagine PIP: nome o formato non valido.")
    start = raw["start_ms"]
    duration = raw["duration_ms"]
    if not (type(start) is int and type(duration) is int and
            0 <= start < output_ms and 400 <= duration <= 12000 and
            start+duration <= output_ms):
        raise ValueError("Immagine PIP fuori dalla timeline montata (0,4–12 s).")
    for key, lo, hi in (("x_pct",0,100),("y_pct",0,100),("width_pct",20,70)):
        val=raw[key]
        if type(val) is not int or not lo <= val <= hi:
            raise ValueError(f"Immagine PIP: {key} deve essere {lo}..{hi}.")
    return dict(raw)


def validate_image_overlays(items: Any, output_ms: int) -> None:
    if not isinstance(items, list) or len(items) > MAX_IMAGE_OVERLAYS:
        raise ValueError("Sono ammesse al massimo quattro immagini PIP.")
    ids = set()
    for image in items:
        row=validate_image_overlay(image,output_ms)
        if row["id"] in ids:
            raise ValueError("Immagine PIP: ID duplicato.")
        ids.add(row["id"])
