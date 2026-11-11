"""Pausio Studio: local-only HTTP workspace for reviewing real edits.

No frontend build, cloud dependency, global data persistence, or shell commands.
Every imported video remains in this server's temporary workspace until exit.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import sys
import re
import shutil
import tempfile
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pausio import __version__
from pausio.local_asr import transcribe_video_local, validate_asr_settings
from pausio.domain import EditPlan, Interval
from pausio.captions import CAPTION_STYLES, CAPTION_PRESETS, propose_captions, remap_captions
from pausio.media import MediaInfo, detect_silences, probe, render, waveform_envelope
from pausio.planner import CUT_PRESETS, validate_cut_settings, policy_from_cut_settings, propose_segments
from pausio.project_commands import ProjectTape, ProjectFormatError, UI_COMMANDS
from pausio.studio_persistence import StudioSessionStore, RecoveryError, default_studio_directory

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
ALLOWED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".mkv", ".webm"})
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
STATIC_DIR = Path(__file__).resolve().parent / "studio_static"


class StudioError(ValueError):
    """A user-recoverable Studio action error."""


class StudioWorkspace:
    """Single-user, ephemeral project with mutually exclusive mutating jobs."""

    def __init__(self, *, data_dir: Path | None = None) -> None:
        self.store = StudioSessionStore(data_dir) if data_dir is not None else None
        self._tmp = None if self.store else tempfile.TemporaryDirectory(prefix="pausio-studio-")
        self.directory = self.store.directory if self.store else Path(self._tmp.name)
        self.lock = threading.RLock()
        self.importing = False
        self.approved = False
        self.tape: ProjectTape | None = None
        self.media_sha256: str | None = None
        self.media_id: str | None = None
        self.source: Path | None = None
        self.filename: str | None = None
        self.info: MediaInfo | None = None
        self.plan: EditPlan | None = None
        self.suggested_plan: EditPlan | None = None
        self.transcript: dict | None = None
        self.export_ready = False
        self.preview_ready = False
        self.waveform: list[int] | None = None
        self.waveform_status = "idle"
        self.waveform_error: str | None = None
        self.recovered = False
        self.recovery_warning: str | None = None
        self.job: dict = {"status": "idle", "kind": None, "error": None}

        if self.store:
            try:
                recovered = self.store.recover()
                if recovered:
                    source, tape, transcript, from_backup = recovered
                    info = probe(source)
                    tape.require_media(
                        sha256=tape.media["sha256"],
                        duration_ms=info.duration_ms, has_audio=info.has_audio,
                    )
                    self.source = source
                    self.filename = tape.media["filename"]
                    self.media_sha256 = tape.media["sha256"]
                    self.media_id = uuid.uuid4().hex
                    self.info = info
                    self._install_tape(tape, persist=False)
                    self.transcript = transcript
                    self.recovered = True
                    if from_backup:
                        self.recovery_warning = (
                            "Recuperata una copia precedente: l'ultimo salvataggio era incompleto."
                        )
                    self.store.cleanup_orphans(self.source)
                    self._start_waveform()
            except (RecoveryError, OSError, ValueError) as exc:
                # Never erase damaged recovery files automatically.
                self.recovery_warning = str(exc)[:350]

    def close(self) -> None:
        # Persistent media is deleted only by explicit "Elimina dati locali",
        # not implicitly when the user closes the browser/server.
        if self._tmp is not None:
            self._tmp.cleanup()
        if self.store:
            self.store.close()

    def _ensure_unlocked(self) -> None:
        if self.importing or self.job["status"] == "running":
            raise StudioError("Un'operazione è già in corso. Riprova al termine.")

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "version": __version__,
                "file": self.filename,
                "media_id": self.media_id,
                "approved": self.approved,
                "autosaved": self.store is not None,
                "recovered": self.recovered,
                "recovery_warning": self.recovery_warning,
                "project_revision": self.tape.revision if self.tape else 0,
                "editor_segments": [dict(s) for s in self.tape.view.segments] if self.tape else [],
                "command_count": len(self.tape.commands) if self.tape else 0,
                "history_cursor": self.tape.history_cursor if self.tape else 0,
                "can_undo": self.tape.can_undo if self.tape else False,
                "can_redo": self.tape.can_redo if self.tape else False,
                "last_command": self.tape.active_command["type"] if self.tape and self.tape.active_command else None,
                "media": self.info.as_dict() if self.info else None,
                "plan": self.plan.as_dict() if self.plan else None,
                "suggested_plan": self.suggested_plan.as_dict() if self.suggested_plan else None,
                "cut_presets": CUT_PRESETS,
                "analysis_settings": self.tape.view.analysis_settings if self.tape else None,
                "detected_silences": self.tape.view.detected_silences if self.tape else None,
                "transcript": self.transcript,
                "captions": [dict(c) for c in self.tape.view.captions] if self.tape else [],
                "caption_style": self.tape.view.caption_style if self.tape else "social",
                "caption_config": self.tape.view.caption_config if self.tape else CAPTION_PRESETS["social"],
                "caption_presets": CAPTION_PRESETS,
                "output_captions": remap_captions(
                    self.tape.view.captions, self.plan.segments
                ) if self.tape and self.plan and self.tape.view.captions else [],
                "export_ready": self.export_ready,
                "preview_ready": self.preview_ready,
                "waveform_status": self.waveform_status,
                "waveform_error": self.waveform_error,
                "importing": self.importing,
                "job": dict(self.job),
            }

    def begin_import(self, name: str) -> tuple[Path, str]:
        label = Path(name).name.strip()
        suffix = Path(label).suffix.lower()
        if not label or "\\" in label or suffix not in ALLOWED_VIDEO_EXTENSIONS:
            raise StudioError("Formato non supportato. Usa MP4, MOV, M4V, MKV o WebM.")
        with self.lock:
            self._ensure_unlocked()
            self.importing = True
        return self.directory / f"incoming-{uuid.uuid4().hex}{suffix}", label[:160]

    def abort_import(self, candidate: Path) -> None:
        with self.lock:
            candidate.unlink(missing_ok=True)
            self.importing = False

    def finish_import(
        self, candidate: Path, label: str, info: MediaInfo | None, sha256: str | None = None
    ) -> None:
        with self.lock:
            try:
                if info is None:
                    candidate.unlink(missing_ok=True)
                    return
                if sha256 is None:
                    with candidate.open("rb") as file:
                        sha256 = hashlib.file_digest(file, "sha256").hexdigest()
                tape = ProjectTape({
                    "filename": label, "sha256": sha256,
                    "duration_ms": info.duration_ms, "has_audio": info.has_audio,
                })
                new_source = candidate
                if self.store is not None:
                    # Commit point is the atomic JSON checkpoint, NOT in-memory state.
                    # Leave the old session intact until the new checkpoint succeeds.
                    new_source = self.store.media_path(sha256, candidate.suffix)
                    os.replace(candidate, new_source)
                    if os.name == "posix":
                        new_source.chmod(0o600)
                    self.store.save(tape, new_source)

                old_source = self.source
                self.source = new_source
                self.filename = label
                self.media_id = uuid.uuid4().hex
                self.media_sha256 = sha256
                self.info = info
                self.tape = tape
                self.plan = None
                self.suggested_plan = None
                self.approved = False
                self.transcript = None
                self.export_ready = False
                self.preview_ready = False
                self.waveform = None
                self.waveform_status = "idle"
                self.waveform_error = None
                self.recovered = False
                self.recovery_warning = None
                self.job = {"status": "idle", "kind": None, "error": None}
                self._start_waveform()
                if self.store:
                    self.store.cleanup_orphans(new_source)
                elif old_source and old_source != new_source:
                    old_source.unlink(missing_ok=True)
                (self.directory / "export.mp4").unlink(missing_ok=True)
                (self.directory / "preview.mp4").unlink(missing_ok=True)
            finally:
                self.importing = False

    def _install_tape(self, tape: ProjectTape, *, persist: bool = True) -> None:
        """Only expose the new derived state after successful autosave."""
        assert self.source is not None
        new_plan = tape.edit_plan(str(self.source))
        proposal = tape.view.suggested
        suggested_plan = (
            EditPlan(
                source=str(self.source), source_duration_ms=tape.media["duration_ms"],
                has_audio=tape.media["has_audio"],
                segments=tuple(Interval(s["start_ms"], s["end_ms"]) for s in proposal),
            )
            if proposal is not None else None
        )
        if persist and self.store:
            self.store.save(tape, self.source, transcript=self.transcript)
        self.tape = tape
        self.plan = new_plan
        self.suggested_plan = suggested_plan
        self.approved = tape.view.approved
        self.export_ready = False
        self.preview_ready = False
        (self.directory / "export.mp4").unlink(missing_ok=True)
        (self.directory / "preview.mp4").unlink(missing_ok=True)

    def clear_session(self) -> None:
        """Forget explicitly, including managed cached media and recovery backups."""
        with self.lock:
            self._ensure_unlocked()
            if self.store:
                self.store.drop()
            elif self.source:
                self.source.unlink(missing_ok=True)
            (self.directory / "export.mp4").unlink(missing_ok=True)
            (self.directory / "preview.mp4").unlink(missing_ok=True)
            self.source = None
            self.filename = None
            self.info = None
            self.media_sha256 = None
            self.media_id = None
            self.tape = None
            self.plan = None
            self.suggested_plan = None
            self.approved = False
            self.transcript = None
            self.export_ready = False
            self.preview_ready = False
            self.waveform = None
            self.waveform_status = "idle"
            self.waveform_error = None
            self.recovered = False
            self.recovery_warning = None
            self.job = {"status": "idle", "kind": None, "error": None}

    def _start_waveform(self) -> None:
        """Start non-blocking waveform extraction for the current source.

        The media_id token prevents an old background worker from overwriting
        the waveform of a newly imported/cleared video.
        """
        if self.source is None or self.info is None:
            return
        source, info, token = self.source, self.info, self.media_id
        if not info.has_audio:
            self.waveform = []
            self.waveform_status = "ready"
            return
        self.waveform = None
        self.waveform_error = None
        self.waveform_status = "running"

        def worker() -> None:
            try:
                values = waveform_envelope(source, info.duration_ms, has_audio=info.has_audio)
            except Exception as exc:
                with self.lock:
                    if self.media_id == token:
                        self.waveform_status = "failed"
                        self.waveform_error = str(exc)[:250]
            else:
                with self.lock:
                    if self.media_id == token:
                        self.waveform = values
                        self.waveform_status = "ready"

        threading.Thread(target=worker, name="pausio-waveform", daemon=True).start()

    def get_waveform(self) -> dict:
        with self.lock:
            if self.waveform_status != "ready" or self.info is None:
                raise StudioError(self.waveform_error or "Waveform non ancora disponibile.")
            return {
                "media_id": self.media_id,
                "duration_ms": self.info.duration_ms,
                "values": list(self.waveform or []),
            }

    def generate_captions(self, raw: dict) -> None:
        """Turn the *current* in-memory ASR draft into a portable edit event."""
        with self.lock:
            self._ensure_unlocked()
            if self.tape is None or self.info is None or self.transcript is None:
                raise StudioError("Trascrivi prima il parlato per creare sottotitoli.")
            if not isinstance(raw, dict) or set(raw) != {"revision", "style"}:
                raise StudioError("Generazione sottotitoli: parametri non validi.")
            if type(raw["revision"]) is not int or raw["revision"] != self.tape.revision:
                raise StudioError("Versione progetto non aggiornata. Ricarica e riprova.")
            if raw["style"] not in CAPTION_STYLES:
                raise StudioError("Stile sottotitoli non valido.")
            try:
                proposals = propose_captions(
                    self.transcript, source_duration_ms=self.info.duration_ms
                )
                if not proposals:
                    raise ValueError("La trascrizione non contiene parole da sottotitolare.")
                cues = [{"id": uuid.uuid4().hex, **row} for row in proposals]
                next_tape = self.tape.append(
                    "caption.set", {"style": raw["style"], "cues": cues}
                )
            except (ValueError, ProjectFormatError) as exc:
                raise StudioError(str(exc)) from exc
            self._install_tape(next_tape)

    def command(self, raw: dict) -> None:
        """Execute a version-checked typed command requested by the Studio UI."""
        with self.lock:
            self._ensure_unlocked()
            if self.tape is None:
                raise StudioError("Importa un video prima di modificarlo.")
            if not isinstance(raw, dict) or set(raw) != {"revision", "type", "payload"}:
                raise StudioError("Il comando richiede revision, type e payload.")
            rev = raw["revision"]
            if not isinstance(rev, int) or isinstance(rev, bool) or rev != self.tape.revision:
                raise StudioError("Versione del progetto non aggiornata. Ricarica e riprova.")
            kind = raw["type"]
            if not isinstance(kind, str) or kind not in (UI_COMMANDS | {"history.undo", "history.redo"}):
                raise StudioError("Comando UI non supportato.")
            payload = raw["payload"]
            if not isinstance(payload, dict):
                raise StudioError("Parametri del comando non validi.")
            if kind in {"history.undo", "history.redo"}:
                if payload:
                    raise StudioError("Undo/Redo non accetta parametri.")
                try:
                    next_tape = self.tape.undo() if kind == "history.undo" else self.tape.redo()
                except ProjectFormatError as exc:
                    raise StudioError(str(exc)) from exc
                self._install_tape(next_tape)
                return
            if kind == "segment.insert":
                if set(payload) != {"start_ms", "end_ms"}:
                    raise StudioError("Aggiungi intervallo richiede start_ms ed end_ms.")
                payload = {"segment": {
                    "id": uuid.uuid4().hex,
                    "start_ms": payload["start_ms"],
                    "end_ms": payload["end_ms"],
                }}
            try:
                next_tape = self.tape.append(kind, payload)
            except ProjectFormatError as exc:
                raise StudioError(str(exc)) from exc
            self._install_tape(next_tape)

    def save_plan(self, raw_segments: object) -> None:
        """Compatibility endpoint: still records an explicit timeline.replace event."""
        with self.lock:
            self._ensure_unlocked()
            if self.source is None or self.info is None or self.tape is None:
                raise StudioError("Importa un video prima di modificare il montaggio.")
            if not isinstance(raw_segments, list) or not 1 <= len(raw_segments) <= 200:
                raise StudioError("Inserisci da 1 a 200 intervalli da mantenere.")
            try:
                intervals = tuple(Interval(**row) for row in raw_segments)
                EditPlan(
                    source=str(self.source), source_duration_ms=self.info.duration_ms,
                    segments=intervals, has_audio=self.info.has_audio,
                )
            except (TypeError, ValueError) as exc:
                raise StudioError(f"Intervalli non validi: {exc}") from exc
            old_segments = self.tape.view.segments
            rows = [{
                "id": old_segments[i]["id"] if i < len(old_segments) else uuid.uuid4().hex,
                "start_ms": interval.start_ms, "end_ms": interval.end_ms,
            } for i, interval in enumerate(intervals)]
            try:
                next_tape = self.tape.append("timeline.replace", {"segments": rows})
            except ProjectFormatError as exc:
                raise StudioError(str(exc)) from exc
            self._install_tape(next_tape)

    def approve_plan(self) -> None:
        with self.lock:
            self._ensure_unlocked()
            if self.tape is None:
                raise StudioError("Analizza un video prima di confermare il montaggio.")
            try:
                self._install_tape(self.tape.append("timeline.approve", {}))
            except ProjectFormatError as exc:
                raise StudioError(str(exc)) from exc

    def export_project(self) -> dict:
        with self.lock:
            if self.tape is None:
                raise StudioError("Importa un video prima di esportare il progetto.")
            return self.tape.as_dict()

    def import_project(self, raw: dict) -> None:
        with self.lock:
            self._ensure_unlocked()
            if self.tape is None or self.info is None or self.media_sha256 is None:
                raise StudioError("Importa prima il video originale da collegare al progetto.")
            try:
                incoming = ProjectTape.from_dict(raw)
                incoming.require_media(
                    sha256=self.media_sha256,
                    duration_ms=self.info.duration_ms, has_audio=self.info.has_audio,
                )
            except ProjectFormatError as exc:
                raise StudioError(str(exc)) from exc
            self._install_tape(incoming)

    def start_job(
        self, kind: str, *, settings: object | None = None, asr: object | None = None
    ) -> None:
        if kind not in {"analyze", "render", "transcribe", "preview"}:
            raise StudioError("Operazione sconosciuta.")
        if kind != "analyze" and settings is not None:
            raise StudioError("Le impostazioni di taglio sono valide solo per Analizza.")
        if kind != "transcribe" and asr is not None:
            raise StudioError("Le impostazioni ASR sono valide solo per Trascrivi.")
        try:
            cut_settings = validate_cut_settings(settings) if kind == "analyze" else None
            asr_options = validate_asr_settings(asr) if kind == "transcribe" else None
        except ValueError as exc:
            raise StudioError(str(exc)) from exc
        with self.lock:
            self._ensure_unlocked()
            if self.source is None or self.info is None:
                raise StudioError("Importa prima un video.")
            if kind == "render" and (self.plan is None or not self.approved):
                raise StudioError("Conferma il montaggio prima dell'esportazione.")
            if kind == "preview" and self.plan is None:
                raise StudioError("Analizza o prepara un montaggio prima dell'anteprima.")
            source = self.source
            info = self.info
            plan = self.plan
            if kind == "render":
                self.export_ready = False
            if kind == "preview":
                self.preview_ready = False
            self.job = {"status": "running", "kind": kind, "error": None}

        def worker() -> None:
            try:
                if kind == "analyze":
                    assert cut_settings is not None
                    policy = policy_from_cut_settings(cut_settings)
                    silences = (
                        detect_silences(
                            source, info.duration_ms,
                            noise_db=int(cut_settings["noise_db"]),
                            min_detection_ms=min(550, policy.min_silence_ms),
                        ) if info.has_audio else []
                    )
                    proposal = EditPlan(
                        source=str(source), source_duration_ms=info.duration_ms,
                        has_audio=info.has_audio,
                        segments=propose_segments(info.duration_ms, silences, policy),
                    )
                    with self.lock:
                        assert self.tape is not None
                        next_tape = self.tape.append("analysis.propose", {
                            "segments": [
                                {"id": uuid.uuid4().hex,
                                 "start_ms": segment.start_ms, "end_ms": segment.end_ms}
                                for segment in proposal.segments
                            ],
                            "engine": "ffmpeg.silencedetect",
                            "policy": "ai-natural",
                            "noise_db": cut_settings["noise_db"],
                            "settings": cut_settings,
                            "detected_silences": len(silences),
                        })
                        self._install_tape(next_tape)
                elif kind == "transcribe":
                    assert asr_options is not None
                    result = transcribe_video_local(source, **asr_options)
                    with self.lock:
                        # Publish only after the private checkpoint is durable:
                        # a disk-write error must not claim ASR was saved.
                        if self.store:
                            assert self.tape is not None and self.source is not None
                            self.store.save(self.tape, self.source, transcript=result)
                        self.transcript = result
                elif kind in {"render", "preview"}:
                    assert plan is not None
                    with self.lock:
                        assert self.tape is not None
                        current_captions = self.tape.view.captions
                        current_style = self.tape.view.caption_style
                        current_config = self.tape.view.caption_config
                    mapped = remap_captions(current_captions, plan.segments)
                    render(
                        source, self.directory / ("preview.mp4" if kind == "preview" else "export.mp4"),
                        plan.segments, has_audio=plan.has_audio, overwrite=True,
                        size=(540, 960) if kind == "preview" else (1080, 1920),
                        captions=mapped, caption_style=current_style,
                        caption_config=current_config,
                    )
                    with self.lock:
                        if kind == "preview":
                            self.preview_ready = True
                        else:
                            self.export_ready = True
                with self.lock:
                    self.job = {"status": "completed", "kind": kind, "error": None}
            except Exception as exc:
                with self.lock:
                    self.job = {"status": "failed", "kind": kind, "error": str(exc)[:350]}

        threading.Thread(target=worker, name=f"pausio-{kind}", daemon=True).start()


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], workspace: StudioWorkspace):
        self.workspace = workspace
        super().__init__(address, StudioHandler)


class StudioHandler(BaseHTTPRequestHandler):
    server: StudioServer
    protocol_version = "HTTP/1.1"

    def handle_one_request(self) -> None:
        """Close idle/aborted browser connections without a server traceback.

        Browsers may cancel or reset an HTTP/1.1 keep-alive socket while Studio
        is waiting for its next request or writing a response. These are
        transport-level disconnects, not application errors; all other
        exceptions still propagate for diagnosis.
        """
        try:
            super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        # Do not print full video paths, transcript text or other private content.
        if self.path.startswith("/api/"):
            return
        super().log_message(format, *args)

    def _headers(self, code: int, size: int, mime: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; script-src 'self'; "
            "style-src 'self'; img-src 'self' data:; media-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )

    def _send_bytes(self, code: int, data: bytes, mime: str) -> None:
        self._headers(code, len(data), mime)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, value: object) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self._send_bytes(code, data, "application/json; charset=utf-8")

    def _failed(self, code: int, message: str) -> None:
        self._json(code, {"error": message})

    def _check_post_security(self) -> None:
        if self.headers.get("X-Pausio-Client") != "studio":
            raise StudioError("Richiesta non autorizzata.")
        origin = self.headers.get("Origin")
        valid = f"http://127.0.0.1:{self.server.server_port}"
        if origin is not None and origin != valid:
            raise StudioError("Origine non autorizzata.")
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in {"application/json", "application/octet-stream"}:
            raise StudioError("Formato della richiesta non supportato.")

    def _content_length(self, maximum: int) -> int:
        try:
            size = int(self.headers.get("Content-Length", ""))
        except ValueError as exc:
            raise StudioError("Content-Length richiesto.") from exc
        if not 0 < size <= maximum:
            raise StudioError("File o richiesta vuota oppure troppo grande.")
        return size

    def _read_json(self) -> dict:
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            raise StudioError("È richiesto JSON.")
        raw = self.rfile.read(self._content_length(MAX_JSON_BYTES))
        try:
            result = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StudioError("JSON non valido.") from exc
        if not isinstance(result, dict):
            raise StudioError("È richiesto un oggetto JSON.")
        return result

    def do_POST(self) -> None:
        try:
            self._check_post_security()
            path = urlsplit(self.path).path
            if path == "/api/import":
                self._import()
                return
            if path == "/api/plan":
                self.server.workspace.save_plan(self._read_json().get("segments"))
                self._json(200, self.server.workspace.snapshot())
                return
            if path == "/api/command":
                self.server.workspace.command(self._read_json())
                self._json(200, self.server.workspace.snapshot())
                return
            if path == "/api/captions/generate":
                self.server.workspace.generate_captions(self._read_json())
                self._json(200, self.server.workspace.snapshot())
                return
            if path == "/api/project/import":
                self.server.workspace.import_project(self._read_json())
                self._json(200, self.server.workspace.snapshot())
                return
            if path == "/api/session/clear":
                self.server.workspace.clear_session()
                self._json(200, self.server.workspace.snapshot())
                return
            if path == "/api/approve":
                self.server.workspace.approve_plan()
                self._json(200, self.server.workspace.snapshot())
                return
            if path == "/api/jobs":
                request = self._read_json()
                if set(request) - {"kind", "settings", "asr"}:
                    raise StudioError("Parametri job sconosciuti.")
                self.server.workspace.start_job(
                    request.get("kind", ""), settings=request.get("settings"),
                    asr=request.get("asr")
                )
                self._json(202, self.server.workspace.snapshot())
                return
            self._failed(404, "Endpoint non trovato.")
        except StudioError as exc:
            self._failed(409 if "in corso" in str(exc) or "Versione" in str(exc) else 400, str(exc))
        except Exception:
            self._failed(500, "Errore interno. Controlla il terminale di Pausio.")

    def _import(self) -> None:
        if self.headers.get("Content-Type") != "application/octet-stream":
            raise StudioError("Caricamento video non valido.")
        size = self._content_length(MAX_UPLOAD_BYTES)
        filename = unquote(self.headers.get("X-Filename", ""))
        destination, label = self.server.workspace.begin_import(filename)
        metadata: MediaInfo | None = None
        digest = hashlib.sha256()
        completed = False
        try:
            fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as target:
                remaining = size
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise StudioError("Caricamento interrotto. Riprova.")
                    target.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                target.flush()
                os.fsync(target.fileno())
            metadata = probe(destination)
            self.server.workspace.finish_import(destination, label, metadata, digest.hexdigest())
            completed = True
            self._json(200, self.server.workspace.snapshot())
        finally:
            if not completed:
                self.server.workspace.abort_import(destination)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/favicon.ico":
            # Browsers request this even without a declared icon. A deliberately
            # empty response avoids a misleading 404 without adding new assets.
            self._headers(204, 0, "image/x-icon")
            self.end_headers()
            return
        if path in ASSETS:
            file_name, mime = ASSETS[path]
            try:
                self._send_bytes(200, (STATIC_DIR / file_name).read_bytes(), mime)
            except OSError:
                self._failed(500, "Asset UI non disponibile.")
            return
        if path == "/api/state":
            self._json(200, self.server.workspace.snapshot())
            return
        if path == "/api/waveform":
            try:
                self._json(200, self.server.workspace.get_waveform())
            except StudioError as exc:
                self._failed(409, str(exc))
            return
        if path == "/api/project/export":
            try:
                content = json.dumps(
                    self.server.workspace.export_project(), ensure_ascii=False, indent=2
                ).encode("utf-8")
            except StudioError as exc:
                self._failed(400, str(exc))
                return
            self._headers(200, len(content), "application/json; charset=utf-8")
            self.send_header(
                "Content-Disposition", 'attachment; filename="pausio-project.pausio.json"'
            )
            self.end_headers()
            self.wfile.write(content)
            return
        if path == "/api/media":
            self._media(False, False)
            return
        if path == "/api/export":
            self._media(True, False)
            return
        if path == "/api/preview":
            self._media(False, False, preview=True)
            return
        self._failed(404, "Risorsa non trovata.")

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        if path == "/favicon.ico":
            self._headers(204, 0, "image/x-icon")
            self.end_headers()
            return
        if path in {"/api/media", "/api/export", "/api/preview"}:
            self._media(path == "/api/export", True, preview=path == "/api/preview")
        else:
            self._failed(404, "Risorsa non trovata.")

    def _media(self, exported: bool, headers_only: bool, *, preview: bool = False) -> None:
        with self.server.workspace.lock:
            path = (
                self.server.workspace.directory / "preview.mp4" if preview
                else self.server.workspace.directory / "export.mp4" if exported
                else self.server.workspace.source
            )
            if (exported and not self.server.workspace.export_ready) or (
                preview and not self.server.workspace.preview_ready
            ):
                path = None
            if path is None or not path.is_file():
                self._failed(404, "Video non disponibile.")
                return
            total = path.stat().st_size
        if total <= 0:
            self._failed(404, "Video vuoto.")
            return
        begin, end = 0, total - 1
        requested = self.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested.strip())
            if not match or not any(match.groups()):
                self._range_error(total)
                return
            raw_start, raw_end = match.groups()
            if raw_start:
                begin = int(raw_start)
                end = int(raw_end) if raw_end else total - 1
            else:
                length = int(raw_end)
                if length <= 0:
                    self._range_error(total)
                    return
                begin = max(0, total - length)
            if begin >= total or end < begin:
                self._range_error(total)
                return
            end = min(end, total - 1)
        size = end - begin + 1
        mime = "video/mp4" if preview or exported or path.suffix.lower() in {".mp4", ".m4v", ".mov"} else "video/webm"
        self._headers(206 if requested else 200, size, mime)
        self.send_header("Accept-Ranges", "bytes")
        if requested:
            self.send_header("Content-Range", f"bytes {begin}-{end}/{total}")
        if exported:
            self.send_header("Content-Disposition", 'attachment; filename="pausio-final.mp4"')
        self.end_headers()
        if not headers_only:
            try:
                with path.open("rb") as source:
                    source.seek(begin)
                    remaining = size
                    while remaining:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _range_error(self, total: int) -> None:
        self._headers(416, 0, "text/plain")
        self.send_header("Content-Range", f"bytes */{total}")
        self.end_headers()


def create_server(*, port: int = 8765, workspace: StudioWorkspace | None = None) -> StudioServer:
    """Bind directly to the first free loopback TCP port at or above `port`.

    Bind itself is the availability check: a separate probe followed by bind
    would have a race. Port 0 deliberately retains its ephemeral-port meaning
    for tests. Only EADDRINUSE permits retry; permission and other socket errors
    must be surfaced rather than hidden.
    """
    if not 0 <= port <= 65535:
        raise ValueError("port must be 0..65535")
    active_workspace = workspace if workspace is not None else StudioWorkspace()
    candidates = (0,) if port == 0 else range(port, 65536)
    for candidate in candidates:
        try:
            return StudioServer(("127.0.0.1", candidate), active_workspace)
        except OSError as exc:
            if exc.errno != errno.EADDRINUSE:
                raise
    raise OSError(
        errno.EADDRINUSE, f"Nessuna porta disponibile tra {port} e 65535."
    )


def run_studio(
    *, port: int = 8765, open_browser: bool = True, data_dir: Path | None = None
) -> None:
    workspace = StudioWorkspace(data_dir=data_dir or default_studio_directory())
    try:
        server = create_server(port=port, workspace=workspace)
    except BaseException:
        workspace.close()
        raise
    url = f"http://127.0.0.1:{server.server_port}"
    if port != 0 and server.server_port != port:
        print(
            f"Porta {port} già occupata: avvio sulla prima porta libera "
            f"({server.server_port})."
        )
    print(
        f"Pausio Studio • {url}\n"
        f"Sessione salvata localmente in: {workspace.directory}\n"
        "Per eliminare i media locali usa «Elimina dati locali»."
    )
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.workspace.close()
