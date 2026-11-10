"""Crash-safe, opt-in-at-CLI local persistence for the Studio *active session*.

Portable .pausio.json projects remain independent of video bytes. The local
session store additionally retains the imported media inside a private data
directory so work can resume after the browser/server restarts.

Never call this module from the pure edit reducer or from the renderer.
"""

from __future__ import annotations

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

SESSION_VERSION = 1
STATE_FILE = "active-session.json"
BACKUP_FILE = "previous-session.json"
MAX_STATE_BYTES = 8 * 1024 * 1024
MEDIA_FILE_PATTERN = re.compile(r"^media-[0-9a-f]{64}\.(?:mp4|mov|m4v|mkv|webm)$")


class RecoveryError(ValueError):
    """A saved session could not be safely resumed; leave its files untouched."""


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

    def save(self, tape: ProjectTape, source: Path) -> None:
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
        state = {
            "format": "pausio.local-session",
            "schema_version": SESSION_VERSION,
            "media_file": filename,
            "project": tape.as_dict(),
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

    def _parse(self, path: Path) -> tuple[Path, ProjectTape]:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_STATE_BYTES:
            raise RecoveryError("Il file della sessione non è sicuro o supera il limite.")
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RecoveryError("Il file di autosalvataggio non è leggibile.") from exc
        if not isinstance(saved, dict) or set(saved) != {
            "format", "schema_version", "media_file", "project"
        }:
            raise RecoveryError("Struttura dell'autosalvataggio non supportata.")
        if saved["format"] != "pausio.local-session" or type(saved["schema_version"]) is not int or saved["schema_version"] != SESSION_VERSION:
            raise RecoveryError("Versione dell'autosalvataggio non supportata.")
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
        return video, tape

    def recover(self) -> tuple[Path, ProjectTape, bool] | None:
        """Recover active, or fall back to previous checkpoint without data loss."""
        errors: list[str] = []
        for candidate in (self.active, self.previous):
            if not candidate.exists() and not candidate.is_symlink():
                continue
            try:
                video, tape = self._parse(candidate)
                if candidate == self.previous:
                    # Repair primary before the next save, so a corrupt active
                    # document never overwrites the only known-good backup.
                    self._atomic_bytes(self.active, self.previous.read_bytes())
                return video, tape, candidate == self.previous
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
