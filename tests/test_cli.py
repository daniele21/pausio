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
