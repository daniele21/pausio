"""Captions: segment/word timestamps, cut remapping, ASS escaping and safety."""

import unittest

from pausio.captions import (
    ass_document, propose_captions, remap_captions,
    CAPTION_PRESETS, validate_caption_config, default_caption_config
)
from pausio.domain import Interval


class TestCaptionPipeline(unittest.TestCase):
    def test_real_word_alignment_creates_short_readable_cues(self):
        source = {
            "word_timestamps_available": True,
            "segments": [{
                "start_ms": 100, "end_ms": 5500,
                "text": "Tre consigli che ti faranno aumentare la produttività.",
                "words": [
                    {"start_ms": i * 550 + 100, "end_ms": i * 550 + 540,
                     "text": word}
                    for i, word in enumerate([
                        "Tre", "consigli", "che", "ti", "faranno",
                        "aumentare", "la", "produttività."
                    ])
                ],
            }],
        }
        cues = propose_captions(source, source_duration_ms=5500)
        self.assertGreater(len(cues), 1)
        self.assertTrue(all(len(c["text"]) <= 46 for c in cues))
        self.assertEqual(cues[0]["start_ms"], 100)
        self.assertEqual(cues[-1]["end_ms"], 4390)
        self.assertEqual(
            " ".join(c["text"] for c in cues),
            "Tre consigli che ti faranno aumentare la produttività."
        )

    def test_segment_fallback_preserves_true_boundary(self):
        tr = {"segments": [{"start_ms": 150, "end_ms": 2650,
            "text": "Voglio un sottotitolo unico"}], "word_timestamps_available": False}
        self.assertEqual(propose_captions(tr, source_duration_ms=3000), [{
            "start_ms": 150, "end_ms": 2650, "text": "Voglio un sottotitolo unico"
        }])

    def test_output_timeline_clips_and_splits_cues_across_removed_silence(self):
        cues = [
            {"id": "a" * 32, "start_ms": 500, "end_ms": 1800,
             "text": "Prima"},
            {"id": "b" * 32, "start_ms": 2100, "end_ms": 3400,
             "text": "Dopo"},
        ]
        mapped = remap_captions(
            cues, (Interval(0, 1000), Interval(2000, 3500))
        )
        self.assertEqual([(c["start_ms"], c["end_ms"], c["text"]) for c in mapped], [
            (500, 1000, "Prima"),
            (1100, 2400, "Dopo"),
        ])
        self.assertEqual(remap_captions(cues, (Interval(4000, 5000),)), [])
        # A long word covering the cut is split, not shifted into silence.
        across = [{"id": "c" * 32, "start_ms": 700, "end_ms": 2300, "text": "CIAO"}]
        self.assertEqual(
            [(c["start_ms"], c["end_ms"]) for c in
             remap_captions(across, (Interval(0, 1000), Interval(2000, 3000)))],
            [(700, 1000), (1000, 1300)],
        )

    def test_ass_document_is_unicode_safe_and_injection_safe(self):
        cues = [{"id":"d"*32,"start_ms":250,"end_ms":1530,
                 "text":"L'AI migliora produttività. {\\alpha}"}]
        raw = ass_document(cues)
        self.assertIn("Dialogue: 0,0:00:00.25,0:00:01.53",raw)
        self.assertIn("L'AI migliora produttività. alpha",raw)
        self.assertNotIn("{\\alpha}",raw)
        self.assertIn("PlayResX: 1080",raw)
        self.assertIn("Fontsize",raw)
        self.assertIn("Arial,48",ass_document(cues,style="minimal"))
        with self.assertRaises(ValueError):
            ass_document(cues,style="untrusted")

    def test_style_preset_color_position_and_box_in_ass(self):
        cues=[{"id":"a"*32, "start_ms":100,"end_ms":1300,"text":"Ciao! 👋"}]
        config=default_caption_config("boxed")
        ass=ass_document(cues,style="boxed",settings=config)
        self.assertIn('pos(540,1459)', ass)
        self.assertIn(",Arial,56,",ass)
        self.assertIn(",3,3,1,5,",ass)  # BorderStyle=3 opaque box
        custom={**config,"preset":"custom","x_pct":65,"y_pct":45,
                "font_size":84,"text_color":"#FFCC00",
                "outline_color":"#101010","background":False}
        actual=ass_document(cues,settings=custom)
        self.assertIn('pos(702,864)', actual)
        self.assertIn("Arial,84,&H0000CCFF",actual)
        self.assertIn("&H00101010",actual)
        self.assertIn(",1,3,1,5,",actual)
        self.assertEqual(validate_caption_config(custom),custom)
        for change in ({"x_pct":0},{"y_pct":100},{"font_size":False},
                       {"outline_size":11},{"background":"false"},
                       {"text_color":"red"},{"background_color":"#12"}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_caption_config({**custom,**change})
        with self.assertRaises(ValueError):
            validate_caption_config({**custom,"preset":"social"})

    def test_no_guessing_or_silent_caption_drops_for_malformed_asr(self):
        for value in (-1, True, 5000):
            with self.subTest(value=value):
                tr={"segments":[{"start_ms":value,"end_ms":1000,"text":"ciao"}]}
                with self.assertRaises(ValueError):
                    propose_captions(tr,source_duration_ms=3000)


if __name__ == "__main__":
    unittest.main()
