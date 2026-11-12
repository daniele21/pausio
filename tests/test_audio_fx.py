"""Audio FX replay, validation and deterministic rendering contracts."""

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pausio.domain import Interval
from pausio.media import MediaError, render
from pausio.project_commands import ProjectTape, ProjectFormatError


def source_media():
    return {
        "filename": "original.mp4", "sha256": "a" * 64,
        "duration_ms": 10000, "has_audio": True,
    }


def fx_clip():
    return {
        "id": "b" * 32, "asset_sha256": "c" * 64,
        "filename": "my riser.wav", "start_ms": 3000,
        "duration_ms": 2000, "gain_db": -12,
    }


class AudioFxReplayTests(unittest.TestCase):
    def test_add_edit_remove_undo_redo_and_json_roundtrip(self):
        clip = fx_clip()
        first = ProjectTape(source_media())
        added = first.append("audio.add", {"clip": clip})
        self.assertEqual(added.view.audio_clips[0], clip)
        changed = added.append("audio.update", {
            "clip_id": clip["id"], "start_ms": 1500, "gain_db": -18,
        })
        self.assertEqual(changed.view.audio_clips[0]["start_ms"], 1500)
        self.assertEqual(ProjectTape.from_dict(changed.as_dict()).view, changed.view)
        self.assertEqual(changed.undo().view.audio_clips[0], clip)
        self.assertEqual(changed.undo().redo().view, changed.view)
        removed = changed.append("audio.remove", {"clip_id": clip["id"]})
        self.assertEqual(removed.view.audio_clips, ())
        self.assertEqual(removed.undo().view.audio_clips[0]["gain_db"], -18)

    def test_voice_fx_mixer_and_per_clip_mute_are_portable(self):
        source = ProjectTape(source_media())
        self.assertEqual(source.view.audio_mix, {
            "voice_gain_db": 0, "voice_muted": False,
            "fx_gain_db": 0, "fx_muted": False,
        })
        clip = fx_clip()
        added = source.append("audio.add", {"clip": clip})
        # Old projects retain old clip shape until explicit mixer edits.
        self.assertNotIn("muted", added.view.audio_clips[0])
        mixed = added.append("audio.mixer.configure", {
            "voice_gain_db": -9, "voice_muted": True,
            "fx_gain_db": 6, "fx_muted": False,
        })
        changed = mixed.append("audio.clip.mix", {
            "clip_id": clip["id"], "gain_db": -3, "muted": True,
        })
        self.assertTrue(changed.view.audio_mix["voice_muted"])
        self.assertEqual(changed.view.audio_mix["fx_gain_db"], 6)
        self.assertTrue(changed.view.audio_clips[0]["muted"])
        self.assertEqual(changed.view.audio_clips[0]["gain_db"], -3)
        loaded = ProjectTape.from_dict(changed.as_dict())
        self.assertEqual(loaded.view, changed.view)
        self.assertEqual(changed.undo().view.audio_clips[0], clip)
        self.assertEqual(changed.undo().undo().view.audio_mix, source.view.audio_mix)
        self.assertEqual(changed.undo().redo().view, changed.view)

    def test_mixer_validation_rejects_unknown_fields_types_and_range(self):
        base = ProjectTape(source_media()).append("audio.add", {"clip": fx_clip()})
        good = {
            "voice_gain_db": 0, "voice_muted": False,
            "fx_gain_db": 0, "fx_muted": False,
        }
        for delta in (
            {"voice_gain_db": 13}, {"voice_gain_db": True},
            {"fx_gain_db": -37}, {"fx_gain_db": 0.5},
            {"voice_muted": 1}, {"fx_muted": "false"},
            {"not_a_bus": 0},
        ):
            with self.subTest(delta=delta), self.assertRaises(ProjectFormatError):
                base.append("audio.mixer.configure", {**good, **delta})
        with self.assertRaises(ProjectFormatError):
            base.append("audio.mixer.configure", {"fx_muted": True})
        for muted in ("yes", 0, None):
            with self.subTest(muted=muted), self.assertRaises(ProjectFormatError):
                base.append("audio.clip.mix", {
                    "clip_id": fx_clip()["id"], "gain_db": -12, "muted": muted
                })
        with self.assertRaises(ProjectFormatError):
            base.append("audio.clip.mix", {
                "clip_id": "d" * 32, "gain_db": -12, "muted": False
            })
        with self.assertRaises(ProjectFormatError):
            base.append("audio.add", {"clip": {**fx_clip(), "muted": 1}})
        with self.assertRaises(ProjectFormatError):
            base.append("audio.clip.mix", {
                "clip_id": fx_clip()["id"], "gain_db": 20, "muted": False
            })

    def test_reject_untrusted_asset_paths_and_invalid_properties(self):
        good = fx_clip()
        for edit in (
            {"filename": "../bad.wav"},
            {"filename": "not-audio.txt"},
            {"asset_sha256": "z" * 64},
            {"start_ms": True},
            {"start_ms": 10000},
            {"duration_ms": 0},
            {"duration_ms": 180001},
            {"gain_db": 15},
            {"gain_db": 1.5},
        ):
            with self.subTest(edit=edit):
                with self.assertRaises(ProjectFormatError):
                    ProjectTape(source_media()).append("audio.add", {"clip": {**good, **edit}})
        with self.assertRaises(ProjectFormatError):
            ProjectTape(source_media()).append("audio.remove", {"clip_id": "d" * 32})

    def test_approval_is_invalidated_by_fx_edit(self):
        tape = ProjectTape(source_media()).append("timeline.keep_all", {})
        tape = tape.append("timeline.approve", {})
        self.assertTrue(tape.view.approved)
        tape = tape.append("audio.add", {"clip": fx_clip()})
        self.assertFalse(tape.view.approved)
        self.assertTrue(tape.undo().view.approved)


class AudioFxRenderTests(unittest.TestCase):
    def test_preview_and_final_use_same_fx_mix(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            fx = Path(directory) / "sound.wav"
            source.touch()
            fx.touch()
            effects = [(fx, fx_clip())]
            with patch("pausio.media.require_binary", return_value="ffmpeg"):
                standard = render(
                    source, Path(directory) / "final.mp4",
                    (Interval(0, 2500), Interval(3000, 7500)),
                    has_audio=True, dry_run=True, audio_fx=effects,
                )
                preview = render(
                    source, Path(directory) / "preview.mp4",
                    (Interval(0, 2500), Interval(3000, 7500)),
                    has_audio=True, dry_run=True, audio_fx=effects, size=(540, 960),
                )
            std = standard[standard.index("-filter_complex") + 1]
            prv = preview[preview.index("-filter_complex") + 1]
            self.assertIn("adelay=3000:all=1", std)
            self.assertIn("volume=-12dB", std)
            self.assertIn("amix=inputs=2", std)
            self.assertIn("[outa]", std)
            self.assertIn(str(fx), standard)
            self.assertEqual(std.replace("1080:1920", "540:960"), prv)
            self.assertIn("[outa]", standard)

    def test_mix_graph_voice_fx_gains_and_mutes(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            fx = Path(directory) / "sound.wav"
            source.touch()
            fx.touch()
            clip = {**fx_clip(), "muted": True}
            mix = {"voice_gain_db": -6, "voice_muted": False,
                   "fx_gain_db": 8, "fx_muted": False}
            with patch("pausio.media.require_binary", return_value="ffmpeg"):
                a = render(source, Path(directory) / "a.mp4",
                    (Interval(0, 7000),), has_audio=True, dry_run=True,
                    audio_fx=[(fx, clip)], audio_mix=mix)
                b = render(source, Path(directory) / "b.mp4",
                    (Interval(0, 7000),), has_audio=True, dry_run=True,
                    size=(540,960), audio_fx=[(fx, clip)], audio_mix=mix)
                no_fx = render(source, Path(directory) / "c.mp4",
                    (Interval(0, 7000),), has_audio=True, dry_run=True,
                    audio_mix={**mix, "voice_muted": True})
                audible = render(source, Path(directory) / "d.mp4",
                    (Interval(0, 7000),), has_audio=True, dry_run=True,
                    audio_fx=[(fx, {**clip, "muted": False})], audio_mix=mix)
            graph = a[a.index("-filter_complex")+1]
            self.assertIn("volume=-6dB[voice]",graph)
            self.assertIn("volume=0,adelay=3000:all=1",graph)
            self.assertEqual(graph.replace("1080:1920","540:960"),
                             b[b.index("-filter_complex")+1])
            self.assertIn("volume=0[voice]",no_fx[no_fx.index("-filter_complex")+1])
            self.assertIn("volume=-4dB,adelay=3000",audible[audible.index("-filter_complex")+1])
            self.assertIn("-map",no_fx)
            self.assertIn("[outa]",no_fx)
            self.assertIn("[outa]",a)

    def test_missing_fx_file_is_rejected(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "original.mp4"
            source.touch()
            with self.assertRaises(MediaError):
                render(source, Path(directory) / "result.mp4",
                       (Interval(0, 1000),), has_audio=True, dry_run=True,
                       audio_fx=[(Path(directory) / "gone.mp3", fx_clip())])


if __name__ == "__main__":
    unittest.main()
