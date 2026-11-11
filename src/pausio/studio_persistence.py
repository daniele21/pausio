"""Crash-safe, opt-in-at-CLI local persistence for the Studio *active session*.

Portable .pausio.json projects remain independent of video bytes. The local
session store additionally retains the imported media inside a private data
directory so work can resume after the browser/server restarts.

Never call this module from the pure edit reducer or from the renderer.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    import fcntl  # POSIX: the file lock releases automatically after a crash.
except ImportError:  # pragma: no cover - Windows compatibility
    fcntl = None
    import msvcrt

from pausio.project_commands import ProjectTape, ProjectFormatError

SESSION_VERSION = 2
LEGACY_SESSION_VERSION = 1
MAX_TRANSCRIPT_BYTES = 4 * 1024 * 1024
STATE_FILE = "active-session.json"
BACKUP_FILE = "previous-session.json"
MAX_STATE_BYTES = 8 * 1024 * 1024
MEDIA_FILE_PATTERN = re.compile(r"^media-[0-9a-f]{64}\.(?:mp4|mov|m4v|mkv|webm)$")


class RecoveryError(ValueError):
    """A saved session could not be safely resumed; leave its files untouched."""


def _session_transcript(raw: object, *, media: dict) -> dict | None:
    """Validate and sanitize a local ASR result before writing or restoring it.

    Raw transcripts are private session state, NOT portable project commands.
    Drop the redundant source path (which can expose a private home directory).
    Original source SHA-256 is bound separately by the enclosing session.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise RecoveryError("La trascrizione salvata non è valida.")
    required = {
        "schema_version", "source_duration_ms", "provider", "backend",
        "model", "language", "text", "segments",
        "word_timestamps_available", "warnings",
    }
    if set(raw) not in (required, required | {"source"}):
        raise RecoveryError("Campi della trascrizione non supportati.")
    if (
        type(raw["schema_version"]) is not int or raw["schema_version"] != 1
        or type(raw["source_duration_ms"]) is not int
        or raw["source_duration_ms"] != media["duration_ms"]
        or raw["provider"] != "pausio-local"
        or raw["backend"] != "mlx-whisper"
    ):
        raise RecoveryError("La trascrizione non corrisponde al video o al formato ASR.")
    if not isinstance(raw["model"], str) or not 1 <= len(raw["model"]) <= 256:
        raise RecoveryError("Il modello della trascrizione non è valido.")
    if raw["language"] is not None and (
        not isinstance(raw["language"], str) or len(raw["language"]) > 30
    ):
        raise RecoveryError("La lingua della trascrizione non è valida.")
    if not isinstance(raw["text"], str) or len(raw["text"]) > 250_000:
        raise RecoveryError("Il testo della trascrizione supera il limite previsto.")
    if type(raw["word_timestamps_available"]) is not bool:
        raise RecoveryError("Il flag dei timestamp non è valido.")
    warnings = raw["warnings"]
    if (
        not isinstance(warnings, list) or len(warnings) > 32
        or any(not isinstance(w, str) or len(w) > 160 for w in warnings)
    ):
        raise RecoveryError("Avvisi della trascrizione non validi.")
    entries = raw["segments"]
    if not isinstance(entries, list) or len(entries) > 10_000:
        raise RecoveryError("Troppi segmenti di trascrizione.")
    segments: list[dict] = []
    previous_start = -1
    words_count = 0
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) not in (
            {"start_ms", "end_ms", "text"},
            {"start_ms", "end_ms", "text", "words"},
        ):
            raise RecoveryError("Struttura di un segmento ASR non valida.")
        start, end, value = entry["start_ms"], entry["end_ms"], entry["text"]
        if (
            type(start) is not int or type(end) is not int
            or not 0 <= start < end <= media["duration_ms"] + 2000
            or start < previous_start
            or not isinstance(value, str) or len(value) > 5000
        ):
            raise RecoveryError("Timestamp o testo del segmento ASR non valido.")
        previous_start = start
        segment = {"start_ms": start, "end_ms": end, "text": value}
        if "words" in entry:
            words = entry["words"]
            if not isinstance(words, list) or len(words) > 1000:
                raise RecoveryError("Parole della trascrizione non valide.")
            cleaned_words: list[dict] = []
            for word in words:
                if not isinstance(word, dict) or set(word) != {
                    "start_ms", "end_ms", "text"
                }:
                    raise RecoveryError("Formato delle parole non valido.")
                a, b, word_text = word["start_ms"], word["end_ms"], word["text"]
                if (
                    type(a) is not int or type(b) is not int
                    or a < max(0, start - 1000) or a >= b
                    or b > end + 1000
                    or not isinstance(word_text, str) or len(word_text) > 500
                ):
                    raise RecoveryError("Timestamp delle parole non valido.")
                cleaned_words.append({"start_ms": a, "end_ms": b, "text": word_text})
            words_count += len(words)
            if words_count > 100_000:
                raise RecoveryError("Troppi timestamp delle parole.")
            segment["words"] = cleaned_words
        segments.append(segment)
    if raw["word_timestamps_available"] != (words_count > 0):
        raise RecoveryError("Indicatore di allineamento della trascrizione incoerente.")
    transcript = {key: copy.deepcopy(raw[key]) for key in required if key != "segments"}
    transcript["segments"] = segments
    size = len(json.dumps(transcript, ensure_ascii=False).encode("utf-8"))
    if size > MAX_TRANSCRIPT_BYTES:
        raise RecoveryError("Trascrizione troppo grande per l'autosalvataggio locale.")
    return transcript


def default_studio_directory() -> Path:
    """User-private persistent data; never the repo, browser or OS temp folder."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Pausio" / "Studio"
    xdg = os.environ.get("XDG_DATA_HOME")
    root = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return root / "pausio" / "studio"


def sha256_file(path: Path) -> str:
    with path.open("rb") as src:
        digest = hashlib.sha256()
        for chunk in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class StudioSessionStore:
    """One auto-saved active project, with a crash-safe previous checkpoint."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self.directory.is_dir() or self.directory.is_symlink():
            raise RecoveryError("La cartella dati di Pausio non è una directory sicura.")
        if os.name == "posix":
            self.directory.chmod(0o700)
        self.active = self.directory / STATE_FILE
        self.previous = self.directory / BACKUP_FILE
        self._lock_fd = os.open(
            self.directory / ".session.lock", os.O_CREAT | os.O_RDWR, 0o600
        )
        try:
            if fcntl is not None:
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:  # pragma: no cover - Windows compatibility
                if os.fstat(self._lock_fd).st_size == 0:
                    os.write(self._lock_fd, b"0")
                os.lseek(self._lock_fd, 0, os.SEEK_SET)
                msvcrt.locking(self._lock_fd, msvcrt.LK_NBLCK, 1)
        except (OSError, BlockingIOError) as exc:
            os.close(self._lock_fd)
            raise RecoveryError(
                "Pausio Studio è già aperto con questa cartella di progetto."
            ) from exc

    def close(self) -> None:
        try:
            if fcntl is not None:
                fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            else:  # pragma: no cover - Windows compatibility
                os.lseek(self._lock_fd, 0, os.SEEK_SET)
                msvcrt.locking(self._lock_fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(self._lock_fd)

    def media_path(self, sha256: str, suffix: str) -> Path:
        filename = f"media-{sha256}{suffix.lower()}"
        if not MEDIA_FILE_PATTERN.fullmatch(filename):
            raise RecoveryError("Formato del file video della sessione non valido.")
        return self.directory / filename

    def _atomic_bytes(self, destination: Path, raw: bytes) -> None:
        fd, temp_name = tempfile.mkstemp(prefix=".pausio-save-", dir=self.directory)
        temp = Path(temp_name)
        try:
            if os.name == "posix":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp, destination)
            if os.name == "posix":
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                dir_fd = os.open(self.directory, flags)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        finally:
            temp.unlink(missing_ok=True)

    def save(
        self, tape: ProjectTape, source: Path, *,
        transcript: dict | None = None
    ) -> None:
        """Commit an entire validated project as one atomic new checkpoint.

        If saving fails, the active on-disk session remains unchanged and
        callers MUST NOT install the unsaved tape in memory.
        """
        if source.parent.resolve() != self.directory:
            raise RecoveryError("Il video da salvare deve essere nella cartella privata.")
        filename = source.name
        if not MEDIA_FILE_PATTERN.fullmatch(filename) or not source.is_file() or source.is_symlink():
            raise RecoveryError("Video della sessione non valido.")
        if filename != self.media_path(tape.media["sha256"], source.suffix).name:
            raise RecoveryError("Hash del video e nome della sessione non corrispondono.")
        private_transcript = _session_transcript(transcript, media=tape.media)
        state = {
            "format": "pausio.local-session",
            "schema_version": SESSION_VERSION,
            "media_file": filename,
            "project": tape.as_dict(),
            "transcript": (
                {"media_sha256": tape.media["sha256"], "data": private_transcript}
                if private_transcript is not None else None
            ),
        }
        raw = (json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(raw) > MAX_STATE_BYTES:
            raise RecoveryError("La sessione è troppo grande per il salvataggio automatico.")
        if self.active.is_symlink() or self.previous.is_symlink():
            raise RecoveryError("Il file di autosalvataggio non può essere un collegamento.")
        if self.active.is_file():
            # Keep previous known-good state; this copy is also atomically written.
            self._atomic_bytes(self.previous, self.active.read_bytes())
        self._atomic_bytes(self.active, raw)

    def _parse(self, path: Path) -> tuple[Path, ProjectTape, dict | None]:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_STATE_BYTES:
            raise RecoveryError("Il file della sessione non è sicuro o supera il limite.")
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RecoveryError("Il file di autosalvataggio non è leggibile.") from exc
        if not isinstance(saved, dict):
            raise RecoveryError("Struttura dell'autosalvataggio non supportata.")
        version = saved.get("schema_version")
        common = {"format", "schema_version", "media_file", "project"}
        if (
            saved.get("format") != "pausio.local-session"
            or type(version) is not int
            or version not in (LEGACY_SESSION_VERSION, SESSION_VERSION)
            or set(saved) != (
                common if version == LEGACY_SESSION_VERSION
                else common | {"transcript"}
            )
        ):
            raise RecoveryError("Versione o struttura dell'autosalvataggio non supportata.")
        media_file = saved["media_file"]
        if not isinstance(media_file, str) or not MEDIA_FILE_PATTERN.fullmatch(media_file):
            raise RecoveryError("Il percorso del video salvato non è valido.")
        try:
            tape = ProjectTape.from_dict(saved["project"])
        except ProjectFormatError as exc:
            raise RecoveryError(f"Le istruzioni salvate non sono valide: {exc}") from exc
        video = self.directory / media_file
        if video.is_symlink() or not video.is_file():
            raise RecoveryError("Il video originale non è più disponibile nella sessione.")
        if video.name != self.media_path(tape.media["sha256"], video.suffix).name:
            raise RecoveryError("Il file video non corrisponde al progetto salvato.")
        if sha256_file(video) != tape.media["sha256"]:
            raise RecoveryError("Il video della sessione non supera la verifica SHA-256.")
        transcript = None
        if version == SESSION_VERSION and saved["transcript"] is not None:
            wrapper = saved["transcript"]
            if (
                not isinstance(wrapper, dict)
                or set(wrapper) != {"media_sha256", "data"}
                or wrapper["media_sha256"] != tape.media["sha256"]
            ):
                raise RecoveryError("La trascrizione appartiene a un altro video.")
            transcript = _session_transcript(wrapper["data"], media=tape.media)
            if transcript is None:
                raise RecoveryError("Dati della trascrizione mancanti.")
        return video, tape, transcript

    def recover(self) -> tuple[Path, ProjectTape, dict | None, bool] | None:
        """Recover active, or fall back to previous checkpoint without data loss."""
        errors: list[str] = []
        for candidate in (self.active, self.previous):
            if not candidate.exists() and not candidate.is_symlink():
                continue
            try:
                video, tape, transcript = self._parse(candidate)
                if candidate == self.previous:
                    # Repair primary before the next save, so a corrupt active
                    # document never overwrites the only known-good backup.
                    self._atomic_bytes(self.active, self.previous.read_bytes())
                return video, tape, transcript, candidate == self.previous
            except RecoveryError as exc:
                errors.append(f"{candidate.name}: {exc}")
        if errors:
            raise RecoveryError("Nessuna sessione recuperabile. " + "; ".join(errors))
        return None

    def drop(self) -> None:
        """Explicit user-controlled removal of stored project and managed media."""
        for filename in (STATE_FILE, BACKUP_FILE):
            (self.directory / filename).unlink(missing_ok=True)
        for path in self.directory.iterdir():
            if path.is_file() and (
                MEDIA_FILE_PATTERN.fullmatch(path.name)
                or re.fullmatch(r"fx-[0-9a-f]{64}", path.name)
                or path.name.startswith("incoming-")
                or path.name == "export.mp4"
                or path.name.startswith(".pausio-save-")
            ):
                path.unlink(missing_ok=True)

    def cleanup_orphans(self, active_video: Path | None) -> None:
        """Prune abandoned imports and media NOT referenced by either checkpoint.

        Keep media from the previous checkpoint too: if the newest autosave
        is corrupted, falling back must never point to an already deleted video.
        """
        protected = {active_video.name} if active_video else set()
        for session_file in (self.active, self.previous):
            if session_file.is_symlink() or not session_file.is_file():
                continue
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                name = data.get("media_file") if isinstance(data, dict) else None
                if isinstance(name, str) and MEDIA_FILE_PATTERN.fullmatch(name):
                    protected.add(name)
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
        for path in self.directory.iterdir():
            if path.name in protected or not path.is_file() or path.is_symlink():
                continue
            if (
                MEDIA_FILE_PATTERN.fullmatch(path.name)
                or re.fullmatch(r"incoming-[0-9a-f]{32}\.(?:mp4|mov|m4v|mkv|webm)", path.name)
                or path.name.startswith(".pausio-save-")
            ):
                path.unlink(missing_ok=True)
