"""Offline evidence-backed editorial planner tests: no invented claims or edits."""
from __future__ import annotations

import copy
import unittest

from pausio.editorial_planner import RULES, propose_editorial_plan
from pausio.project_commands import ProjectTape


def base_inputs(preset="educational"):
    first={"id":"1"*32,"start_ms":0,"end_ms":22000}
    second={"id":"2"*32,"start_ms":26000,"end_ms":40000}
    cues=[
        {"id":"a"*32,"start_ms":3000,"end_ms":5400,
         "text":"Sono stati individuati 1.379 segreti su GitHub"},
        {"id":"b"*32,"start_ms":15000,"end_ms":17200,
         "text":"Controlla il file settings.local.json"},
        {"id":"c"*32,"start_ms":28000,"end_ms":30300,
         "text":"Verifica quello che viene salvato nelle configurazioni"},
    ]
    return dict(segments=[first,second], captions=cues,existing_graphics=[],
                existing_fx=[], transcript=None, preset=preset,
                media_sha256="a"*64,base_revision=7,
                source_duration_ms=40000)


class EditorialPlannerTests(unittest.TestCase):
    def test_literal_numeric_code_and_tip_cues_yield_valid_typed_graphics(self):
        data=base_inputs("dynamic_social")
        before=copy.deepcopy(data)
        result=propose_editorial_plan(**data)
        self.assertEqual(data,before,"read-only suggestions must not mutate inputs")
        self.assertEqual(result["base_revision"],7)
        self.assertTrue(result["approval_required"])
        self.assertLessEqual(len(result["candidates"]),6)
        for candidate in result["candidates"]:
            self.assertIn(candidate["command_type"],
                          ("graphic.overlay.add","video.transform.add"))
            self.assertRegex(candidate["candidate_id"],r"^[0-9a-f]{32}$")
            if candidate["command_type"]=="graphic.overlay.add":
                card=candidate["payload"]["graphic"]
                self.assertIn(card["text"]," ".join(c["text"] for c in data["captions"]))
                self.assertLessEqual(card["end_ms"],40000)
                self.assertTrue(candidate["evidence"]["kind"].startswith("caption_"))
                self.assertEqual(candidate["evidence"]["quoted_text"],card["text"])
        self.assertEqual(result,propose_editorial_plan(**copy.deepcopy(data)))

    def test_denser_profile_can_offer_more_but_limits_and_conflicts_apply(self):
        clean=propose_editorial_plan(**base_inputs("clean_tech"))
        dynamic=propose_editorial_plan(**base_inputs("dynamic_social"))
        n=lambda p:sum(c["command_type"]=="graphic.overlay.add" for c in p["candidates"])
        self.assertGreaterEqual(n(dynamic),n(clean))
        self.assertLessEqual(n(clean),1)
        self.assertLessEqual(n(dynamic),2)
        cards=[c for c in dynamic["candidates"]
               if c["command_type"]=="graphic.overlay.add"]
        if cards:
            previous=cards[0]["payload"]["graphic"]
            input_data=base_inputs("dynamic_social")
            input_data["existing_graphics"]=[previous]
            filtered=propose_editorial_plan(**input_data)
            self.assertTrue(all(
                abs(c["output_time_ms"]-cards[0]["output_time_ms"]) >= 1500
                for c in filtered["candidates"]
                if c["command_type"]=="graphic.overlay.add"
            ))

    def test_no_verified_caption_produces_no_informational_graphics(self):
        data=base_inputs()
        data["captions"]=[]
        result=propose_editorial_plan(**data)
        self.assertFalse(any(c["command_type"]=="graphic.overlay.add"
                             for c in result["candidates"]))
        self.assertIn("reviewed_caption_data",result["missing_signals"])
        self.assertIn("semantic_director",result["missing_signals"])

    def test_reject_malformed_inputs_instead_of_speculating(self):
        for change in ({"preset":"arbitrary"},
                       {"base_revision":True},
                       {"media_sha256":"wrong"},
                       {"segments":[{"id":"wrong","start_ms":0,"end_ms":1000}]},
                       {"captions":[{}]*301}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                propose_editorial_plan(**{**base_inputs(),**change})

    def test_approved_candidate_replays_through_existing_v7_commands(self):
        media={"filename":"clip.mov","sha256":"a"*64,
               "duration_ms":40000,"has_audio":True}
        tape=ProjectTape(media).append("timeline.keep_all",{})
        seg=tape.view.segments[0]
        data=base_inputs()
        data["segments"]=[seg]
        proposal=propose_editorial_plan(**data)
        cards=[c for c in proposal["candidates"]
               if c["command_type"]=="graphic.overlay.add"]
        self.assertTrue(cards)
        chosen=cards[0]
        changed=tape.append(chosen["command_type"],chosen["payload"])
        self.assertEqual(changed.view.graphic_overlays[0],
                         chosen["payload"]["graphic"])
        self.assertEqual(changed.undo().view.graphic_overlays,())
        self.assertEqual(
            ProjectTape.from_dict(changed.as_dict()).view.graphic_overlays,
            changed.view.graphic_overlays
        )
