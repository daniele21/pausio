"""Portable graphical overlay card regression: validated edits, ASS, cut mapping."""
import unittest

from pausio.domain import Interval
from pausio.graphic_overlays import (
    validate_graphic, validate_graphics, remap_graphics, compose_graphics_ass
)
from pausio.project_commands import ProjectTape, ProjectFormatError


class TestGraphicOverlayCards(unittest.TestCase):
    def setUp(self):
        self.media = {"filename": "video.mov", "sha256": "a"*64,
                      "duration_ms": 8000, "has_audio": True}
        self.tape = ProjectTape(self.media).append("timeline.keep_all", {})
        self.segment = self.tape.view.segments[0]["id"]
        self.graphic = {
            "id": "b"*32, "segment_id": self.segment,
            "start_ms": 900, "end_ms": 2900,
            "text": "1.379 segreti su GitHub",
            "kind": "stat", "animation": "slide",
            "x_pct": 50, "y_pct": 22, "font_size": 70,
            "color": "#FFC69F",
        }

    def test_v5_replay_roundtrip_undo_and_redo(self):
        added = self.tape.append("graphic.overlay.add", {"graphic": self.graphic})
        self.assertEqual(added.as_dict()["schema_version"], 6)
        self.assertEqual(added.view.graphic_overlays[0], self.graphic)
        self.assertEqual(added.undo().view.graphic_overlays, ())
        self.assertEqual(added.undo().redo().view.graphic_overlays[0], self.graphic)
        self.assertEqual(ProjectTape.from_dict(added.as_dict()).view.graphic_overlays[0],
                         self.graphic)
        updated = {**self.graphic, "animation": "pop", "font_size": 80}
        tape = added.append("graphic.overlay.update", {"graphic": updated})
        self.assertEqual(tape.view.graphic_overlays[0]["font_size"], 80)
        tape = tape.append("graphic.overlay.remove", {"graphic_id": self.graphic["id"]})
        self.assertFalse(tape.view.graphic_overlays)

    def test_rejects_orphan_bad_text_unknown_kind_and_oversized_graphics(self):
        invalid = [
            {**self.graphic, "segment_id": "c"*32},
            {**self.graphic, "text": "x\nz"},
            {**self.graphic, "kind": "arbitrary_js"},
            {**self.graphic, "animation": "eval"},
            {**self.graphic, "y_pct": 98},
            {**self.graphic, "font_size": 200},
            {**self.graphic, "end_ms": 9000},
            {**self.graphic, "color": "#XX0000"},
            {**self.graphic, "x_pct": True},
            {**self.graphic, "path": "/private/film.mp4"},
        ]
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(ProjectFormatError):
                self.tape.append("graphic.overlay.add", {"graphic": item})
        self.assertEqual(self.tape.view.graphic_overlays, ())
        with self.assertRaises(ProjectFormatError):
            self.tape.append("graphic.overlay.remove", {"graphic_id": "f"*32})

    def test_source_to_output_cut_mapping_is_exact(self):
        original = [{**self.graphic, "start_ms": 2900, "end_ms": 4800}]
        kept = (Interval(0, 3000), Interval(4000, 8000))
        mapped = remap_graphics(original, kept)
        self.assertEqual([(g["start_ms"], g["end_ms"]) for g in mapped],
                         [(3000, 3800)])
        # In the actual project a graphic bound to a single KEEP is validated
        # before remapping, so only the relevant segment is present.
        only_kept = (Interval(4000, 8000),)
        self.assertEqual(remap_graphics(original, only_kept)[0]["start_ms"], 0)

    def test_ass_cards_are_animated_and_untrusted_text_cannot_inject_tags(self):
        cards = [self.graphic, {**self.graphic, "id":"c"*32, "kind":"code",
                               "animation":"pop","text":r"settings.local.json {\blur10}"}]
        document = compose_graphics_ass([], cards)
        self.assertIn("Style: Graphic,Arial", document)
        self.assertIn("Style: GraphicStat,Impact", document)
        self.assertIn("Style: GraphicCode,Courier New", document)
        self.assertIn("Style: GraphicTip,Avenir Next", document)
        self.assertIn("GraphicStat,,0,0,0", document)
        self.assertIn("GraphicCode,,0,0,0", document)
        self.assertIn(r"\move(", document)
        self.assertIn(r"\fscx85\fscy85", document)
        self.assertNotIn(r"\blur10", document)
        self.assertIn("settings.local.json", document)
        self.assertEqual(document.count("Dialogue: 1,"), 2)

    def test_legacy_v4_document_remains_importable(self):
        old = {**self.tape.as_dict(), "schema_version": 4}
        self.assertEqual(ProjectTape.from_dict(old).view.segments,
                         self.tape.view.segments)
