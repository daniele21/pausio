"""Three isolated Pausio ProjectTape variants sharing the exact same source media.

The portable project format is unchanged. A variant bundle is private Studio
session metadata, never a hidden editing command. Switching active variants
does not replay any AI suggestion or automatically approve a render.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pausio.project_commands import ProjectTape, ProjectFormatError

STYLE_IDS = ("authority", "visual_explainer", "social_impact")
VARIANT_FORMAT = "pausio.local-variants"
VARIANT_VERSION = 1


@dataclass(frozen=True)
class VariantWorkspace:
    active: str
    tapes: dict[str, ProjectTape]

    def __post_init__(self) -> None:
        if type(self.active) is not str or self.active not in STYLE_IDS:
            raise ValueError("Variante attiva sconosciuta.")
        if type(self.tapes) is not dict or set(self.tapes) != set(STYLE_IDS):
            raise ValueError("Occorrono esattamente tre varianti editoriali.")
        media = None
        for key in STYLE_IDS:
            tape = self.tapes[key]
            if not isinstance(tape, ProjectTape):
                raise ValueError("Variante: il progetto non è valido.")
            if media is None:
                media = tape.media
            elif tape.media != media:
                raise ValueError("Le varianti devono condividere il video SHA-256 originale.")

    @classmethod
    def fork(cls, tape: ProjectTape) -> "VariantWorkspace":
        if not isinstance(tape, ProjectTape) or not tape.view.segments:
            raise ValueError("Prepara una timeline prima di creare tre varianti.")
        # Deep-copy command tapes, including each variant's own undo/redo tail.
        return cls(
            active=STYLE_IDS[0],
            tapes={name: ProjectTape.from_dict(tape.as_dict()) for name in STYLE_IDS},
        )

    def switch(self, style_id: str) -> "VariantWorkspace":
        if type(style_id) is not str or style_id not in STYLE_IDS:
            raise ValueError("Variante editoriale non valida.")
        return VariantWorkspace(style_id, dict(self.tapes))

    def with_active_tape(self, tape: ProjectTape) -> "VariantWorkspace":
        if not isinstance(tape, ProjectTape):
            raise ValueError("Progetto della variante non valido.")
        if tape.media != self.tapes[self.active].media:
            raise ValueError("Il video sorgente della variante è cambiato.")
        return VariantWorkspace(
            self.active, {**self.tapes, self.active: tape}
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": VARIANT_FORMAT,
            "schema_version": VARIANT_VERSION,
            "active": self.active,
            "projects": {key: self.tapes[key].as_dict() for key in STYLE_IDS},
        }

    @classmethod
    def from_dict(cls, raw: Any, *, source_tape: ProjectTape | None = None) -> "VariantWorkspace":
        if (not isinstance(raw, dict) or
            set(raw) != {"format", "schema_version", "active", "projects"} or
            raw["format"] != VARIANT_FORMAT or
            type(raw["schema_version"]) is not int or
            raw["schema_version"] != VARIANT_VERSION or
            not isinstance(raw["projects"], dict) or
            set(raw["projects"]) != set(STYLE_IDS)):
            raise ValueError("Bundle di varianti sconosciuto o incompleto.")
        try:
            bundle = cls(
                raw["active"],
                {key: ProjectTape.from_dict(raw["projects"][key]) for key in STYLE_IDS},
            )
        except (ProjectFormatError, TypeError, KeyError) as exc:
            raise ValueError("La variante contiene istruzioni non valide.") from exc
        if source_tape is not None and (
            not isinstance(source_tape, ProjectTape) or
            bundle.tapes[bundle.active].as_dict() != source_tape.as_dict()
        ):
            raise ValueError("La variante attiva non corrisponde all'autosalvataggio.")
        return bundle

    def summary(self) -> list[dict]:
        """Minimal metadata only: never include private transcript or copied captions."""
        return [
            {
                "id": key,
                "active": key == self.active,
                "revision": self.tapes[key].revision,
                "approved": self.tapes[key].view.approved,
                "scene_count": len(self.tapes[key].view.scene_templates),
                "graphic_count": len(self.tapes[key].view.graphic_overlays),
            }
            for key in STYLE_IDS
        ]
