"""Automatic motion proposal engine: deterministic, bounded and non-mutating."""
import copy
import unittest
import uuid
from pausio.visual_fx_auto import propose_visual_fx, PROFILE_RULES


def keep(a,b):
    return {"id":uuid.uuid4().hex,"start_ms":a,"end_ms":b}


def propose(segments, transcript=None, existing=None, preset="naturale", revision=9):
    return propose_visual_fx(segments=segments,transcript=transcript,
                             existing=existing or [],preset=preset,
                             media_sha256="a"*64,base_revision=revision)


class AutomaticVideoFxTests(unittest.TestCase):
    def test_cut_punch_generated_only_after_real_removed_gap(self):
        segs=[keep(0,1700),keep(2200,6000),keep(6500,12200)]
        actual=propose(segs)
        self.assertTrue(actual["candidates"])
        self.assertTrue(all(item["evidence"]["kind"]=="cut_boundary"
                            for item in actual["candidates"]))
        self.assertTrue(all(item["effect"]["kind"]=="punch"
                            for item in actual["candidates"]))
        self.assertLessEqual(len(actual["candidates"]),1) # 12s natural <1/min
        self.assertEqual(actual["media_sha256"],"a"*64)

    def test_no_signal_means_zero_fx_even_in_dynamic_mode(self):
        segs=[keep(0,7000)]
        x=propose(segs,preset="dinamico")
        self.assertEqual(x["candidates"],[])
        self.assertIn("asr_phrases",x["missing_signals"])

    def test_real_asr_phrase_allows_slow_push_not_semantic_claim(self):
        seg=[keep(0,7000)]
        words={"segments":[{"start_ms":1500,"end_ms":3000,"text":"Fatto importante"},
                           {"start_ms":4100,"end_ms":6200,"text":"Altro"}]}
        x=propose(seg,words,preset="educativo")
        self.assertTrue(x["candidates"])
        fx=x["candidates"][0]
        self.assertEqual(fx["effect"]["kind"],"slow_push")
        self.assertEqual(fx["evidence"]["kind"],"asr_phrase_boundary")
        self.assertNotIn("asr_phrases",x["missing_signals"])

    def test_determinism_across_calls_same_source(self):
        items=[keep(0,2000),keep(2500,8000),keep(8400,13000)]
        self.assertEqual(propose(items),propose(copy.deepcopy(items)))

    def test_output_time_gap_not_source_gap(self):
        items=[keep(0,2200),keep(100000,104000),keep(190000,195000)]
        x=propose(items,preset="dinamico")
        times=[c["output_time_ms"] for c in x["candidates"]]
        self.assertTrue(all(b-a>=PROFILE_RULES["dinamico"]["gap_ms"]
                            for a,b in zip(times,times[1:])))
        self.assertTrue(all(t<11200 for t in times))

    def test_protected_manual_fx_not_overwritten(self):
        segs=[keep(0,2200),keep(2700,9000)]
        eligible=propose(segs,preset="dinamico")["candidates"]
        self.assertTrue(eligible)
        taken=eligible[0]["effect"]
        blocked=propose(segs,existing=[taken],preset="dinamico")
        self.assertFalse(any(c["candidate_id"]==taken["id"]
                             for c in blocked["candidates"]))

    def test_invalid_media_revision_preset_and_segments_rejected(self):
        segs=[keep(0,5000),keep(5600,8500)]
        for profile in ("viral-random",None,"\\:"):
            with self.assertRaises(ValueError):
                propose(segs,preset=profile)
        with self.assertRaises(ValueError):
            propose(segs,revision=True)
        with self.assertRaises(ValueError):
            propose_visual_fx(segments=segs,transcript=None,existing=[],preset="naturale",
                              media_sha256="not-a-digest",base_revision=0)
        with self.assertRaises(ValueError):
            propose([{**segs[0],"start_ms":True}])

    def test_custom_profile_is_bounded_and_changes_density(self):
        items=[keep(i*3500,i*3500+2700) for i in range(12)]
        options={"max_per_min":10,"gap_ms":2800,"punch_pct":120,
                 "push_pct":115,"push_ms":1800,"use_audio_energy":False}
        result=propose_visual_fx(segments=items,transcript=None,existing=[],
            preset="personalizzato",media_sha256="a"*64,base_revision=2,
            overrides=options)
        self.assertEqual(result["effective_profile"]["punch_pct"],120)
        self.assertTrue(result["candidates"])
        self.assertTrue(all(x["effect"]["end_scale_pct"]==120
                            for x in result["candidates"]))
        self.assertEqual(result,propose_visual_fx(segments=items,transcript=None,
            existing=[],preset="personalizzato",media_sha256="a"*64,
            base_revision=2,overrides=options))
        for mutation in (
            {"max_per_min":True},{"punch_pct":180},
            {"push_ms":4001},{"gap_ms":100},{"shell":"rm -rf"},
        ):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                propose_visual_fx(segments=items,transcript=None,existing=[],
                    preset="personalizzato",media_sha256="a"*64,base_revision=2,
                    overrides={**options,**mutation})
        with self.assertRaises(ValueError):
            propose_visual_fx(segments=items,transcript=None,existing=[],
                preset="naturale",media_sha256="a"*64,base_revision=2,
                overrides=options)

    def test_optional_measured_audio_onset_is_not_semantic_emphasis(self):
        seg=[keep(0,9000)]
        waveform=[180]*900
        waveform[260]=900
        options={"max_per_min":8,"gap_ms":3800,"punch_pct":117,
                 "push_pct":112,"push_ms":2000,"use_audio_energy":True}
        result=propose_visual_fx(segments=seg,transcript=None,existing=[],
            preset="personalizzato",media_sha256="b"*64,base_revision=0,
            overrides=options,waveform=waveform,source_duration_ms=9000)
        self.assertTrue(result["audio_energy_used"])
        self.assertEqual(result["candidates"][0]["evidence"]["kind"],
                         "measured_waveform_rise")
        self.assertNotIn("semantic_importance",repr(result))
        with self.assertRaises(ValueError):
            propose_visual_fx(segments=seg,transcript=None,existing=[],
                preset="personalizzato",media_sha256="b"*64,base_revision=0,
                overrides=options,waveform=[True]*900,source_duration_ms=9000)

    def test_budget_and_spacing_are_maxima_not_quota(self):
        items=[keep(0,1200)]
        for i in range(1,12):
            items.append(keep(i*4000,i*4000+1800))
        for name,cfg in PROFILE_RULES.items():
            got=propose(items,preset=name)
            self.assertLessEqual(len(got["candidates"]),cfg["max_per_min"]*2)
            times=[c["output_time_ms"] for c in got["candidates"]]
            self.assertTrue(all(b-a>=cfg["gap_ms"] for a,b in zip(times,times[1:])))


from pausio.visual_fx_auto import propose_visual_fx
if __name__=="__main__":
    unittest.main()
