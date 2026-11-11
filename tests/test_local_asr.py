"""Pausio standalone MLX ASR contract tests; no model download or network in CI."""

import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pausio.cli import main
from pausio.local_asr import (
    DEFAULT_ASR_MODEL, LocalASRError, _local_model_directory,
    _mlx_transcribe, normalize_local_transcript, transcribe_video_local,
    validate_asr_settings,
)
from pausio.media import MediaError, MediaInfo


def payload():
    return {
        "text": "Ciao AI",
        "language": "it",
        "segments": [{
            "start": 0.25, "end": 1.75, "text": "Ciao AI",
            "words": [
                {"start": 0.25, "end": 0.65, "word": "Ciao"},
                {"start": 0.80, "end": 1.75, "word": "AI"},
            ],
        }],
    }


class TestStandaloneLocalASR(unittest.TestCase):
    def test_default_never_allows_download(self):
        self.assertEqual(validate_asr_settings()["allow_model_download"], False)
        for invalid in (
            {"model": DEFAULT_ASR_MODEL, "language": "it"},
            {"model": "malicious/remote", "language": "it", "allow_model_download": True},
            {"model": DEFAULT_ASR_MODEL, "language": "it", "allow_model_download": 1},
            {"model": DEFAULT_ASR_MODEL, "language": "xx", "allow_model_download": False},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_asr_settings(invalid)

    def test_cache_only_vs_explicit_download_is_forwarded_to_hf(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "config.json").write_text("{}", encoding="utf-8")
            (folder / "weights.safetensors").touch()
            calls = []

            def fake_download(**kwargs):
                calls.append(kwargs)
                return str(folder)

            hf = types.SimpleNamespace(snapshot_download=fake_download)
            with patch.dict(sys.modules, {"huggingface_hub": hf}):
                resolved = _local_model_directory(DEFAULT_ASR_MODEL, allow_download=False)
                self.assertEqual(resolved, folder.resolve())
                _local_model_directory(DEFAULT_ASR_MODEL, allow_download=True)
            self.assertEqual(calls[0], {
                "repo_id": DEFAULT_ASR_MODEL, "local_files_only": True
            })
            self.assertEqual(calls[1], {
                "repo_id": DEFAULT_ASR_MODEL, "local_files_only": False
            })

    def test_cache_miss_fails_without_model_download(self):
        def missing(**kwargs):
            self.assertTrue(kwargs["local_files_only"])
            raise FileNotFoundError("cache miss")
        with patch.dict(sys.modules, {"huggingface_hub":
              types.SimpleNamespace(snapshot_download=missing)}):
            with self.assertRaisesRegex(LocalASRError, "cache"):
                _local_model_directory(DEFAULT_ASR_MODEL, allow_download=False)

    def test_normalize_milliseconds_and_actual_words(self):
        result = normalize_local_transcript(
            payload(), source=Path("video.mp4"), duration_ms=3000,
            model=DEFAULT_ASR_MODEL
        )
        self.assertEqual(result["provider"], "pausio-local")
        self.assertEqual(result["backend"], "mlx-whisper")
        self.assertEqual(result["segments"][0]["start_ms"], 250)
        self.assertEqual(result["segments"][0]["words"][1]["end_ms"], 1750)
        self.assertTrue(result["word_timestamps_available"])
        self.assertNotIn("upstream_api", result)

    def test_missing_word_timestamps_are_not_invented(self):
        raw = payload()
        del raw["segments"][0]["words"]
        result = normalize_local_transcript(raw, source=Path("video.mp4"),
                                            duration_ms=3000, model=DEFAULT_ASR_MODEL)
        self.assertFalse(result["word_timestamps_available"])
        self.assertEqual(result["warnings"], ["word_alignment_unavailable"])
        self.assertNotIn("words", result["segments"][0])

    def test_malformed_timestamps_rejected(self):
        for value in (None, -1, "oops", float("nan"), True):
            with self.subTest(value=value):
                raw = payload()
                raw["segments"][0]["start"] = value
                with self.assertRaises(LocalASRError):
                    normalize_local_transcript(
                        raw, source=Path("video.mp4"), duration_ms=3000,
                        model=DEFAULT_ASR_MODEL
                    )
        raw = payload()
        raw["segments"].append({"start": 0.1, "end": 0.2, "text": "out of order"})
        with self.assertRaises(LocalASRError):
            normalize_local_transcript(
                raw, source=Path("video.mp4"), duration_ms=3000, model=DEFAULT_ASR_MODEL
            )

    def test_mlx_whisper_uses_existing_local_model_path(self):
        calls = []
        module = types.SimpleNamespace(transcribe=lambda audio, **kwargs:
            (calls.append((audio, kwargs)), payload())[1])
        with patch.dict(sys.modules, {"mlx_whisper": module}):
            got = _mlx_transcribe(
                Path("/tmp/audio.wav"), Path("/tmp/model"), language="it"
            )
        self.assertEqual(got["text"], "Ciao AI")
        self.assertEqual(calls[0][1]["path_or_hf_repo"], "/tmp/model")
        self.assertTrue(calls[0][1]["word_timestamps"])
        self.assertFalse(calls[0][1]["condition_on_previous_text"])

    def test_no_audio_and_cleanup_on_success_and_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original.mp4"
            source.write_bytes(b"unmodified")
            extracted = []

            def fake_run(args, **kwargs):
                wav = Path(args[-1])
                extracted.append(wav)
                wav.write_bytes(b"fake wav")

            with (
                patch("pausio.local_asr._check_local_runtime"),
                patch("pausio.local_asr._local_model_directory", return_value=Path(directory)),
                patch("pausio.local_asr.probe", return_value=MediaInfo(
                    3000, 1080, 1920, False, "h264", "30/1"
                )),
                patch("pausio.local_asr._run") as run,
            ):
                with self.assertRaises(MediaError):
                    transcribe_video_local(source)
                run.assert_not_called()

            for raised in (False, True):
                with (
                    patch("pausio.local_asr._check_local_runtime"),
                    patch("pausio.local_asr._local_model_directory", return_value=Path(directory)),
                    patch("pausio.local_asr.probe", return_value=MediaInfo(
                        3000, 1080, 1920, True, "h264", "30/1"
                    )),
                    patch("pausio.local_asr.require_binary", return_value="ffmpeg"),
                    patch("pausio.local_asr._run", side_effect=fake_run),
                    patch("pausio.local_asr._mlx_transcribe",
                          side_effect=LocalASRError("ASR failed") if raised else None,
                          return_value=payload()),
                ):
                    if raised:
                        with self.assertRaises(LocalASRError):
                            transcribe_video_local(source)
                    else:
                        transcript = transcribe_video_local(source)
                        self.assertEqual(transcript["text"], "Ciao AI")
                self.assertFalse(extracted[-1].exists())
            self.assertEqual(source.read_bytes(), b"unmodified")

    def test_cli_persists_sidecar_without_closedroom(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"video.mp4"
            source.write_bytes(b"unchanged")
            output=Path(d)/"transcript.json"
            transcript=normalize_local_transcript(
                payload(), source=source, duration_ms=3000, model=DEFAULT_ASR_MODEL
            )
            with (
                patch("pausio.cli.transcribe_video_local", return_value=transcript) as runner,
                redirect_stdout(io.StringIO())
            ):
                self.assertEqual(main(["transcribe", str(source), "-o", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["provider"], "pausio-local")
            self.assertFalse(runner.call_args.kwargs["allow_model_download"])
            self.assertEqual(source.read_bytes(), b"unchanged")
            with (
                patch("pausio.cli.transcribe_video_local") as runner,
                redirect_stderr(io.StringIO())
            ):
                self.assertEqual(main(["transcribe", str(source), "-o", str(output)]), 2)
                runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
