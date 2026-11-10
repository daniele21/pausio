"""Pausio Studio: local-only HTTP workspace for reviewing real edits.

No frontend build, cloud dependency, global data persistence, or shell commands.
Every imported video remains in this server's temporary workspace until exit.
"""

from __future__ import annotations

import json
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
from pausio.closedroom_asr import transcribe_video_with_closedroom
from pausio.domain import EditPlan, Interval
from pausio.media import MediaInfo, detect_silences, probe, render
from pausio.planner import propose_segments

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_JSON_BYTES = 256 * 1024
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

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="pausio-studio-")
        self.directory = Path(self._tmp.name)
        self.lock = threading.RLock()
        self.importing = False
        self.source: Path | None = None
        self.filename: str | None = None
        self.info: MediaInfo | None = None
        self.plan: EditPlan | None = None
        self.suggested_plan: EditPlan | None = None
        self.transcript: dict | None = None
        self.export_ready = False
        self.job: dict = {"status": "idle", "kind": None, "error": None}

    def close(self) -> None:
        self._tmp.cleanup()

    def _ensure_unlocked(self) -> None:
        if self.importing or self.job["status"] == "running":
            raise StudioError("Un'operazione è già in corso. Riprova al termine.")

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "version": __version__,
                "file": self.filename,
                "media": self.info.as_dict() if self.info else None,
                "plan": self.plan.as_dict() if self.plan else None,
                "suggested_plan": self.suggested_plan.as_dict() if self.suggested_plan else None,
                "transcript": self.transcript,
                "export_ready": self.export_ready,
                "importing": self.importing,
                "job": dict(self.job),
            }

    def begin_import(self, name: str) -> tuple[Path, str]:
        label = Path(name).name.strip()
        suffix = Path(label).suffix.lower()
        if not label or suffix not in ALLOWED_VIDEO_EXTENSIONS:
            raise StudioError("Formato non supportato. Usa MP4, MOV, M4V, MKV o WebM.")
        with self.lock:
            self._ensure_unlocked()
            self.importing = True
        return self.directory / f"incoming-{uuid.uuid4().hex}{suffix}", label[:160]

    def finish_import(self, candidate: Path, label: str, info: MediaInfo | None) -> None:
        with self.lock:
            try:
                if info is not None:
                    old_source = self.source
                    self.source = candidate
                    self.filename = label
                    self.info = info
                    self.plan = None
                    self.suggested_plan = None
                    self.transcript = None
                    self.export_ready = False
                    self.job = {"status": "idle", "kind": None, "error": None}
                    if old_source and old_source != candidate:
                        old_source.unlink(missing_ok=True)
                    (self.directory / "export.mp4").unlink(missing_ok=True)
                else:
                    candidate.unlink(missing_ok=True)
            finally:
                self.importing = False

    def save_plan(self, raw_segments: object) -> None:
        with self.lock:
            self._ensure_unlocked()
            if self.source is None or self.info is None:
                raise StudioError("Importa un video prima di modificare il montaggio.")
            if not isinstance(raw_segments, list) or not 1 <= len(raw_segments) <= 200:
                raise StudioError("Inserisci da 1 a 200 intervalli da mantenere.")
            try:
                segments = tuple(Interval(**row) for row in raw_segments)
                plan = EditPlan(
                    source=str(self.source), source_duration_ms=self.info.duration_ms,
                    segments=segments, has_audio=self.info.has_audio,
                )
            except (TypeError, ValueError) as exc:
                raise StudioError(f"Intervalli non validi: {exc}") from exc
            self.plan = plan
            self.export_ready = False
            (self.directory / "export.mp4").unlink(missing_ok=True)

    def start_job(self, kind: str) -> None:
        if kind not in {"analyze", "render", "transcribe"}:
            raise StudioError("Operazione sconosciuta.")
        with self.lock:
            self._ensure_unlocked()
            if self.source is None or self.info is None:
                raise StudioError("Importa prima un video.")
            if kind == "render" and self.plan is None:
                raise StudioError("Analizza e rivedi i tagli prima dell'esportazione.")
            source = self.source
            info = self.info
            plan = self.plan
            if kind == "render":
                self.export_ready = False
            self.job = {"status": "running", "kind": kind, "error": None}

        def worker() -> None:
            try:
                if kind == "analyze":
                    silences = (
                        detect_silences(source, info.duration_ms) if info.has_audio else []
                    )
                    proposal = EditPlan(
                        source=str(source), source_duration_ms=info.duration_ms,
                        has_audio=info.has_audio,
                        segments=propose_segments(info.duration_ms, silences),
                    )
                    with self.lock:
                        self.plan = proposal
                        self.suggested_plan = proposal
                        self.export_ready = False
                        (self.directory / "export.mp4").unlink(missing_ok=True)
                elif kind == "transcribe":
                    result = transcribe_video_with_closedroom(source)
                    with self.lock:
                        self.transcript = result
                else:
                    assert plan is not None
                    render(
                        source, self.directory / "export.mp4", plan.segments,
                        has_audio=plan.has_audio, overwrite=True,
                    )
                    with self.lock:
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
            if path == "/api/jobs":
                self.server.workspace.start_job(self._read_json().get("kind", ""))
                self._json(202, self.server.workspace.snapshot())
                return
            self._failed(404, "Endpoint non trovato.")
        except StudioError as exc:
            self._failed(409 if "in corso" in str(exc) else 400, str(exc))
        except Exception:
            self._failed(500, "Errore interno. Controlla il terminale di Pausio.")

    def _import(self) -> None:
        if self.headers.get("Content-Type") != "application/octet-stream":
            raise StudioError("Caricamento video non valido.")
        size = self._content_length(MAX_UPLOAD_BYTES)
        filename = unquote(self.headers.get("X-Filename", ""))
        destination, label = self.server.workspace.begin_import(filename)
        metadata: MediaInfo | None = None
        try:
            with destination.open("xb") as target:
                remaining = size
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise StudioError("Caricamento interrotto. Riprova.")
                    target.write(chunk)
                    remaining -= len(chunk)
            metadata = probe(destination)
            self.server.workspace.finish_import(destination, label, metadata)
            self._json(200, self.server.workspace.snapshot())
        finally:
            if metadata is None:
                self.server.workspace.finish_import(destination, label, None)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
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
        if path == "/api/media":
            self._media(False, False)
            return
        if path == "/api/export":
            self._media(True, False)
            return
        self._failed(404, "Risorsa non trovata.")

    def do_HEAD(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/api/media", "/api/export"}:
            self._media(path == "/api/export", True)
        else:
            self._failed(404, "Risorsa non trovata.")

    def _media(self, exported: bool, headers_only: bool) -> None:
        with self.server.workspace.lock:
            path = (
                (self.server.workspace.directory / "export.mp4")
                if exported else self.server.workspace.source
            )
            if exported and not self.server.workspace.export_ready:
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
        mime = "video/mp4" if exported or path.suffix.lower() in {".mp4", ".m4v", ".mov"} else "video/webm"
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
    if not 0 <= port <= 65535:
        raise ValueError("port must be 0..65535")
    return StudioServer(("127.0.0.1", port), workspace or StudioWorkspace())


def run_studio(*, port: int = 8765, open_browser: bool = True) -> None:
    server = create_server(port=port)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Pausio Studio • {url}\nTutti i file restano su questo Mac. Ctrl+C per chiudere.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.workspace.close()
