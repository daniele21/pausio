"""ClosedRoom ASR contract tests: no real model or network required."""

import io
import json
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from pausio.cli import main
from pausio.closedroom_asr import (
    ClosedRoomError, _endpoint, _request_closedroom,
    normalize_transcription, transcribe_video_with_closedroom,
)
from pausio.media import MediaError, MediaInfo


def sample_segments():
    return {
        "text": "Ciao AI",
        "language": "it",
        "asr_provider": "local",
        "model": "mlx-community/whisper-large-v3-turbo",
        "backend": "mlx-whisper",
        "segments": [{
            "start": 0.25, "end": 1.75, "text": "Ciao AI",
            "words": [
                {"start": 0.25, "end": 0.65, "word": "Ciao"},
                {"start": 0.80, "end": 1.75, "word": "AI"},
            ],
        }],
    }


class TestClosedRoomContract(unittest.TestCase):
    def test_loopback_only_rejects_unsafe_endpoints(self):
        self.assertEqual(
            _endpoint("http://127.0.0.1:1236"),
            "http://127.0.0.1:1236/v1/audio/transcriptions/path",
        )
        for url in (
            "https://127.0.0.1:1236", "http://example.com:1236",
            "http://localhost:1236", "http://127.0.0.1:1236/redirect",
            "http://127.0.0.1:1236?x=y", "http://user@127.0.0.1:1236",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                _endpoint(url)

    def test_timestamp_normalization_and_provenance(self):
        result = normalize_transcription(sample_segments(), source=Path("video.mp4"), duration_ms=3000)
        self.assertEqual(result["provider"], "closedroom-local")
        self.assertEqual(result["segments"][0]["start_ms"], 250)
        self.assertEqual(result["segments"][0]["words"][1]["end_ms"], 1750)
        self.assertTrue(result["word_timestamps_available"])
        self.assertEqual(result["text"], "Ciao AI")

    def test_missing_word_timestamps_never_invented(self):
        payload = sample_segments()
        del payload["segments"][0]["words"]
        result = normalize_transcription(payload, source=Path("video.mp4"), duration_ms=3000)
        self.assertFalse(result["word_timestamps_available"])
        self.assertEqual(result["warnings"], ["word_alignment_unavailable"])
        self.assertNotIn("words", result["segments"][0])

    def test_cloud_provider_not_accepted(self):
        payload = sample_segments()
        payload["asr_provider"] = "speechmatics"
        with self.assertRaises(ClosedRoomError):
            normalize_transcription(payload, source=Path("video.mp4"), duration_ms=3000)

    def test_bad_timestamp_and_segment_order_rejected(self):
        for bad in (float("nan"), -0.25, "oops", None):
            payload = sample_segments()
            payload["segments"][0]["start"] = bad
            with self.subTest(bad=bad), self.assertRaises(ClosedRoomError):
                normalize_transcription(payload, source=Path("x.mp4"), duration_ms=3000)
        payload = sample_segments()
        payload["segments"].append({"start": 0.1, "end": 0.2, "text": "out of order"})
        with self.assertRaises(ClosedRoomError):
            normalize_transcription(payload, source=Path("x.mp4"), duration_ms=3000)

    def test_request_forces_local_provider_and_verbose_json(self):
        payload = sample_segments()

        class FakeResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return None
            def read(self, size):
                return json.dumps(payload).encode("utf-8")

        class FakeOpener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return FakeResponse()

        opener = FakeOpener()
        with patch("pausio.closedroom_asr.urllib.request.build_opener", return_value=opener):
            result = _request_closedroom(
                Path("/tmp/audio.wav"), url="http://127.0.0.1:1236", language="it", model=None
            )
        self.assertEqual(result["text"], "Ciao AI")
        body = json.loads(opener.request.data)
        self.assertEqual(body["asr_provider"], "local")
        self.assertEqual(body["response_format"], "verbose_json")
        self.assertEqual(body["diarization_provider"], "disabled")
        self.assertTrue(body["word_timestamps"])
        self.assertNotIn("model", body)

    def test_no_audio_rejected_before_contacting_closedroom(self):
        with patch("pausio.closedroom_asr.probe", return_value=MediaInfo(
            3000, 1080, 1920, False, "h264", "30/1"
        )), patch("pausio.closedroom_asr._request_closedroom") as request:
            with self.assertRaises(MediaError):
                transcribe_video_with_closedroom(Path("video.mp4"))
            request.assert_not_called()

    def test_extraction_temp_deleted_after_request(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            source.touch()
            extracted = []

            def fake_request(wav, **kwargs):
                self.assertTrue(wav.parent.exists())
                extracted.append(wav.parent)
                return sample_segments()

            with (
                patch("pausio.closedroom_asr.probe", return_value=MediaInfo(
                    3000, 1080, 1920, True, "h264", "30/1"
                )),
                patch("pausio.closedroom_asr.require_binary", return_value="ffmpeg"),
                patch("pausio.closedroom_asr._run"),
                patch("pausio.closedroom_asr._request_closedroom", side_effect=fake_request),
            ):
                result = transcribe_video_with_closedroom(source)
            self.assertEqual(result["text"], "Ciao AI")
            self.assertFalse(extracted[0].exists())

    def test_cli_transcript_is_local_sidecar_and_protects_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            source.write_bytes(b"source")
            output = Path(directory) / "video.transcript.json"
            transcript = normalize_transcription(sample_segments(), source=source, duration_ms=3000)
            with patch("pausio.cli.transcribe_video_with_closedroom", return_value=transcript):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["transcribe", str(source), "-o", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["provider"], "closedroom-local")
            self.assertEqual(source.read_bytes(), b"source")
            with patch("pausio.cli.transcribe_video_with_closedroom") as caller:
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["transcribe", str(source), "-o", str(output)]), 2)
                caller.assert_not_called()


if __name__ == "__main__":
    unittest.main()
