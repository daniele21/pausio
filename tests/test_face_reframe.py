"""Offline safe face proposal: skip on ambiguity, never mutate video."""
import unittest
from pathlib import Path
from unittest.mock import patch
from pausio.face_reframe import _norm_anchor, FaceAnalysisUnavailable, propose_face_anchor


class FaceReframeTests(unittest.TestCase):
    def test_stable_off_center_face_reports_safe_crop_anchor(self):
        boxes=[(.63,.42,.16,.19),(.64,.42,.16,.18),(.62,.41,.15,.18),
               (.64,.41,.17,.19),(.63,.43,.16,.18)]
        result=_norm_anchor(boxes,116)
        self.assertEqual(result["status"],"ready")
        self.assertGreater(result["anchor_x_pct"],60)
        self.assertEqual(result["samples"],5)
        self.assertEqual(result["method"],"local-haar-stable-crop-v1")

    def test_no_face_moving_face_or_uncroppable_face_are_skipped(self):
        self.assertEqual(_norm_anchor([],116)["status"],"skip")
        moving=[(.30,.4,.17,.18),(.50,.4,.17,.18),(.67,.4,.17,.18)]
        self.assertEqual(_norm_anchor(moving,116)["reason"],
                         "moving_face_requires_dynamic_tracking")
        boundary=[(.98,.5,.15,.18)]*4
        self.assertEqual(_norm_anchor(boundary,130)["reason"],
                         "face_not_safely_contained")

    def test_invalid_boxes_and_zoom_are_rejected(self):
        for scale in (False,99,140):
            with self.assertRaises(ValueError):
                _norm_anchor([(.5,.5,.2,.2)]*3,scale)
        with self.assertRaises(ValueError):
            _norm_anchor([(.5,.5,2,.1)]*3,116)

    def test_file_and_time_safety_precedes_optional_opencv_import(self):
        with self.assertRaises(FaceAnalysisUnavailable):
            propose_face_anchor(Path("/no/source.mp4"),start_ms=0,
                                end_ms=3000,zoom_pct=115)
        with patch("pathlib.Path.is_file",return_value=True):
            with self.assertRaises(FaceAnalysisUnavailable):
                propose_face_anchor(Path("/fake/source.mp4"),start_ms=1,
                                    end_ms=100,zoom_pct=115)


if __name__=="__main__":unittest.main()
