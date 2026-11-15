"""Word-level creator emphasis stays typed, portable and source-timed."""
from __future__ import annotations

import copy
import unittest

from pausio.captions import (
    ass_document, default_caption_config, remap_captions,
    validate_caption_config,
)
from pausio.domain import Interval
from pausio.project_commands import ProjectFormatError, ProjectTape


def media():
    return {"filename": "speech.mp4", "sha256": "a" * 64,
            "duration_ms": 4000, "has_audio": True}


def cue(aligned: bool = True):
    row = {"id": "b" * 32, "start_ms": 200, "end_ms": 1700,
           "text": "AI e sicurezza"}
    if aligned:
        row["words"] = [
            {"text": "AI", "start_ms": 200, "end_ms": 600},
            {"text": "e", "start_ms": 650, "end_ms": 850},
            {"text": "sicurezza", "start_ms": 900, "end_ms": 1700},
        ]
    return row


class CaptionEmphasisTests(unittest.TestCase):
    def test_replay_undo_redo_and_legacy_v11_input(self):
        base = ProjectTape(media()).append("timeline.keep_all", {})
        with_cue = base.append("caption.set", {
            "style": "word_focus", "cues": [cue()]
        })
        edited = with_cue.append("caption.emphasize", {
            "caption_id": "b" * 32, "indices": [0, 2]
        })
        self.assertEqual(edited.as_dict()["schema_version"], 12)
        self.assertEqual(edited.view.captions[0]["emphasis_indices"], [0, 2])
        self.assertEqual(edited.undo().view.captions, with_cue.view.captions)
        self.assertEqual(edited.undo().redo().view.captions, edited.view.captions)
        self.assertEqual(ProjectTape.from_dict(edited.as_dict()).view.captions,
                         edited.view.captions)
        old = {**with_cue.as_dict(), "schema_version": 11}
        self.assertEqual(ProjectTape.from_dict(old).view.captions, with_cue.view.captions)
        cleared = edited.append("caption.emphasize", {
            "caption_id": "b" * 32, "indices": []
        })
        self.assertNotIn("emphasis_indices", cleared.view.captions[0])

    def test_strict_selection_bounds_and_text_correction_clear_stale_indices(self):
        base = ProjectTape(media()).append("timeline.keep_all", {})
        base = base.append("caption.set", {"style": "social", "cues": [cue(False)]})
        for bad in ([-1], [3], [True], [1, 1], [2, 1], "1", [0, 1, 2, 3, 4, 5, 6]):
            with self.subTest(bad=bad), self.assertRaises(ProjectFormatError):
                base.append("caption.emphasize", {"caption_id": "b" * 32, "indices": bad})
        with self.assertRaises(ProjectFormatError):
            base.append("caption.emphasize", {"caption_id": "c" * 32, "indices": [0]})
        picked = base.append("caption.emphasize", {
            "caption_id": "b" * 32, "indices": [2]
        })
        corrected = picked.append("caption.correct", {
            "caption_id": "b" * 32, "text": "Una frase differente"
        })
        self.assertNotIn("emphasis_indices", corrected.view.captions[0])

    def test_custom_color_preserves_word_focus_and_actual_asr_clock(self):
        original = default_caption_config("word_focus")
        config = {**original, "preset": "custom", "highlight_color": "#00AAFF",
                  "font_family": "Verdana"}
        self.assertEqual(validate_caption_config(config), config)
        self.assertEqual(config["motion_mode"], "word_focus")
        row = {**cue(), "emphasis_indices": [2]}
        rendered = ass_document([row], settings=config)
        self.assertIn("&H00FFAA00", rendered)
        self.assertIn("Dialogue: 1,0:00:00.20,0:00:00.60", rendered)
        self.assertIn("Dialogue: 1,0:00:00.90,0:00:01.70", rendered)
        self.assertIn("sicurezza", rendered)
        self.assertEqual(rendered.count("Dialogue: 1"), 3)

    def test_selected_words_without_word_timestamps_are_static_not_fabricated(self):
        config = {**default_caption_config("social"), "preset": "custom",
                  "highlight_color": "#FF0000"}
        row = {**cue(False), "emphasis_indices": [2]}
        rendered = ass_document([row], settings=config)
        self.assertIn("&H000000FF", rendered)
        self.assertIn("sicurezza", rendered)
        self.assertNotIn("Dialogue: 1", rendered)

    def test_keep_cut_remaps_selected_word_indices_and_drops_removed_words(self):
        row = {**cue(), "emphasis_indices": [0, 2]}
        mapped = remap_captions([row], (Interval(650, 1800),))
        self.assertEqual(mapped[0]["text"], "e sicurezza")
        self.assertEqual(mapped[0]["emphasis_indices"], [1])
        self.assertEqual(mapped[0]["words"][0]["text"], "e")
        self.assertEqual(mapped[0]["start_ms"], 0)
        self.assertEqual(mapped[0]["end_ms"], 1050)

    def test_legacy_caption_style_configs_are_normalized_safely(self):
        config = default_caption_config("word_focus")
        old = copy.deepcopy(config)
        del old["highlight_color"]
        del old["motion_mode"]
        del old["font_family"]
        self.assertEqual(validate_caption_config(old), config)
        with self.assertRaises(ValueError):
            validate_caption_config({**config, "filtergraph": "eval=secret"})
        with self.assertRaises(ValueError):
            validate_caption_config({**config, "highlight_color": "red"})
        with self.assertRaises(ValueError):
            validate_caption_config({**config, "motion_mode": "eval=evil"})
