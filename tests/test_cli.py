import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pausio.cli import main
from pausio.media import MediaInfo


class TestCLI(unittest.TestCase):
    def test_doctor_reports_binary_state(self):
        with patch("pausio.cli.shutil.which", return_value=None), redirect_stdout(io.StringIO()) as out:
            result = main(["doctor"])
        self.assertEqual(result, 2)
        self.assertFalse(json.loads(out.getvalue())["ready"])

    def test_doctor_warns_if_ffmpeg_lacks_ass_filter(self):
        def binaries(name):
            return "/opt/homebrew/bin/" + name
        with (
            patch("pausio.cli.shutil.which", side_effect=binaries),
            patch("pausio.cli.ffmpeg_has_filter", return_value=False),
            redirect_stdout(io.StringIO()) as out,
        ):
            result=main(["doctor"])
        self.assertEqual(result,2)
        doc=json.loads(out.getvalue())
        self.assertFalse(doc["captions_ass"])
        self.assertFalse(doc["ready"])
        self.assertIn("ffmpeg-full",doc["warnings"][0])

    def test_doctor_requires_ffmpeg_and_ass_to_be_ready(self):
        with (
            patch("pausio.cli.shutil.which", side_effect=lambda name:"/usr/bin/"+name),
            patch("pausio.cli.ffmpeg_has_filter", return_value=True),
            redirect_stdout(io.StringIO()) as out,
        ):
            result=main(["doctor"])
        self.assertEqual(result,0)
        doc=json.loads(out.getvalue())
        self.assertTrue(doc["captions_ass"])
        self.assertTrue(doc["ready"])
        self.assertEqual(doc["warnings"],[])

    def test_plan_is_reviewable_and_source_is_not_changed(self):
        with TemporaryDirectory() as d:
            video = Path(d) / "source.mp4"
            video.write_bytes(b"raw")
            output = Path(d) / "plan.json"
            metadata = MediaInfo(5000, 1080, 1920, True, "h264", "30/1")
            with (
                patch("pausio.cli.probe", return_value=metadata),
                patch("pausio.cli.detect_silences", return_value=[__import__("pausio.domain", fromlist=["Interval"]).Interval(1000, 3000)]),
                redirect_stdout(io.StringIO()),
            ):
                result = main(["plan", str(video), "-o", str(output)])
            self.assertEqual(result, 0)
            data = json.loads(output.read_text())
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["source"], str(video.resolve()))
            self.assertEqual(len(data["segments"]), 2)
            self.assertEqual(video.read_bytes(), b"raw")

    def test_refuses_to_overwrite_existing_plan(self):
        with TemporaryDirectory() as d:
            video = Path(d) / "source.mp4"
            video.touch()
            output = Path(d) / "plan.json"
            output.write_text("protected", encoding="utf-8")
            with patch("pausio.cli.probe", return_value=MediaInfo(1000, 1, 1, False, "h264", "30/1")):
                with redirect_stderr(io.StringIO()):
                    result = main(["plan", str(video), "-o", str(output)])
            self.assertEqual(result, 2)
            self.assertEqual(output.read_text(), "protected")


if __name__ == "__main__":
    unittest.main()
