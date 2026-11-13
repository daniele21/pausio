"""Source-anchored visual transition events and import/replay invariants."""
import unittest,uuid
from pausio.project_commands import ProjectTape,ProjectFormatError


def media():
    return {"filename":"test.mp4","sha256":"a"*64,"duration_ms":12000,
            "has_audio":False}
def keep(start,end):
    return {"id":uuid.uuid4().hex,"start_ms":start,"end_ms":end}
def dip(left,right,duration=300):
    return {"id":uuid.uuid4().hex,"left_segment_id":left["id"],
            "right_segment_id":right["id"],"kind":"dip_black",
            "duration_ms":duration}

class TransitionCommandsTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b,self.c=keep(0,2400),keep(3500,5600),keep(7200,11000)
        self.tape=ProjectTape(media()).append(
            "timeline.replace",{"segments":[self.a,self.b,self.c]})

    def test_add_update_remove_portable_undo_and_audio_timebase(self):
        fade=dip(self.a,self.b)
        tape=self.tape.append("video.transition.add",{"transition":fade})
        self.assertEqual(tape.view.video_transitions,(fade,))
        changed={**fade,"duration_ms":400}
        tape=tape.append("video.transition.update",{"transition":changed})
        self.assertEqual(tape.view.video_transitions,(changed,))
        self.assertEqual(tape.undo().view.video_transitions,(fade,))
        self.assertEqual(ProjectTape.from_dict(tape.as_dict()).view.video_transitions,(changed,))
        gone=tape.append("video.transition.remove",{"transition_id":fade["id"]})
        self.assertEqual(gone.view.video_transitions,())
        self.assertEqual(gone.undo().view.video_transitions,(changed,))

    def test_invalid_nonadjacent_short_or_wrong_pair_rejected(self):
        base=dip(self.a,self.b)
        for changes in (
            {"right_segment_id":self.c["id"]},
            {"duration_ms":1000},{"duration_ms":True},
            {"kind":"xfade"},{"filter":"run command"},
            {"left_segment_id":"f"*32},
        ):
            with self.subTest(changes=changes),self.assertRaises(ProjectFormatError):
                self.tape.append("video.transition.add",{"transition":{**base,**changes}})
        with self.assertRaises(ProjectFormatError):
            self.tape.append("video.transition.add",{"transition":base}).append(
                "video.transition.add",{"transition":dip(self.a,self.b)})
        self.assertEqual(self.tape.view.video_transitions,())

    def test_cut_change_fails_rather_than_moves_transition(self):
        base=dip(self.a,self.b)
        tape=self.tape.append("video.transition.add",{"transition":base})
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.remove",{"segment_id":self.b["id"]})
        with self.assertRaises(ProjectFormatError):
            tape.append("segment.update",{"segment_id":self.a["id"],
                "start_ms":1400,"end_ms":2400})
        self.assertEqual(tape.view.video_transitions,(base,))

if __name__=="__main__":unittest.main()
