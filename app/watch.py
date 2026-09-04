from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app import db
from app.config import (
    AUDIO_DIR,
    INBOX_ARCHIVE,
    INBOX_ARCHIVE_DIR,
    INBOX_ARCHIVE_NAME,
    INBOX_DIR,
    INBOX_MAX_BYTES,
    INBOX_POLL_SECONDS,
)
from app.pipeline import process_capture

logger = logging.getLogger(__name__)

AUDIO_SUFFIXES = {
    ".3gp",
    ".3gpp",
    ".aac",
    ".amr",
    ".flac",
    ".m4a",
    ".mp3",
    ".mp4",
    ".oga",
    ".ogg",
    ".opus",
    ".wav",
    ".webm",
    ".wma",
}

MIME_BY_SUFFIX = {
    ".3gp": "audio/3gpp",
    ".3gpp": "audio/3gpp",
    ".aac": "audio/aac",
    ".amr": "audio/amr",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".oga": "audio/ogg",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".wma": "audio/x-ms-wma",
}


def capture_id_for(name: str, size: int, mtime_ns: int) -> str:
    """Samme fil skal give samme id, så en ekstra scanning ikke laver en dublet."""
    return hashlib.md5(f"{name}|{size}|{mtime_ns}".encode("utf-8")).hexdigest()


def iso_from_mtime(mtime: float) -> str:
    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


class FolderWatcher:
    """Overvåger den mappe telefonen synker til, og lægger nye klip i indbakken."""

    def __init__(
        self,
        folder: Path | str,
        *,
        archive: bool = INBOX_ARCHIVE,
        archive_dir: Path | str | None = None,
        max_bytes: int = INBOX_MAX_BYTES,
        on_capture: Callable[[str], None] = process_capture,
    ) -> None:
        self.folder = Path(folder)
        self.archive = archive
        self.archive_dir = Path(archive_dir) if archive_dir else self.folder / INBOX_ARCHIVE_NAME
        self.max_bytes = max_bytes
        self.on_capture = on_capture
        self._fingerprints: dict[str, tuple[int, int]] = {}
        self._done: set[str] = set()
        self._too_big: set[str] = set()
        self._stop = threading.Event()

    def candidates(self) -> list[Path]:
        try:
            entries = list(self.folder.iterdir())
        except OSError:
            return []
        files = [item for item in entries if item.is_file() and item.suffix.lower() in AUDIO_SUFFIXES]
        return sorted(files, key=lambda item: item.name)

    def scan_once(self) -> list[str]:
        ingested: list[str] = []
        seen: set[str] = set()
        for path in self.candidates():
            try:
                stat = path.stat()
            except OSError:
                continue
            seen.add(path.name)
            # 0 byte betyder enten OneDrive-pladsholder eller en fil midt i en overførsel.
            if stat.st_size <= 0:
                continue
            if stat.st_size > self.max_bytes:
                if path.name not in self._too_big:
                    self._too_big.add(path.name)
                    logger.warning("Springer %s over: %s bytes er for stor", path.name, stat.st_size)
                continue
            fingerprint = (stat.st_size, stat.st_mtime_ns)
            # Filen skal se ens ud to runder i træk, ellers skriver synkroniseringen stadig på den.
            if self._fingerprints.get(path.name) != fingerprint:
                self._fingerprints[path.name] = fingerprint
                continue
            capture_id = capture_id_for(path.name, stat.st_size, stat.st_mtime_ns)
            if capture_id in self._done:
                continue
            if db.get_capture(capture_id) is not None:
                self._done.add(capture_id)
                self._archive(path)
                continue
            try:
                self._ingest(path, stat, capture_id)
            except Exception:
                logger.exception("Kunne ikke hente %s ind", path.name)
                continue
            ingested.append(capture_id)
        for name in set(self._fingerprints) - seen:
            self._fingerprints.pop(name, None)
            self._too_big.discard(name)
        return ingested

    def run(self) -> None:
        logger.info("Overvåger %s", self.folder)
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception:
                logger.exception("Scanning af %s fejlede", self.folder)
            self._stop.wait(INBOX_POLL_SECONDS)

    def stop(self) -> None:
        self._stop.set()

    def _ingest(self, path: Path, stat: os.stat_result, capture_id: str) -> None:
        suffix = path.suffix.lower()
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        dest = AUDIO_DIR / f"{capture_id}{suffix}"
        shutil.copy2(path, dest)
        db.create_capture(
            capture_id=capture_id,
            source="sync",
            audio_path=str(dest),
            audio_mime=MIME_BY_SUFFIX.get(suffix, "audio/mp4"),
            duration_sec=None,
        )
        # Indbakken sorteres efter created_at, så den skal vise hvornår du talte.
        db.update_capture(capture_id, created_at=iso_from_mtime(stat.st_mtime))
        self._done.add(capture_id)
        logger.info("Hentede %s ind som %s", path.name, capture_id)
        self._archive(path)
        self.on_capture(capture_id)

    def _archive(self, path: Path) -> None:
        if not self.archive:
            return
        try:
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(_free_name(self.archive_dir / path.name)))
        except OSError:
            logger.exception("Kunne ikke flytte %s til %s", path.name, self.archive_dir)


def _free_name(target: Path) -> Path:
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    for index in range(2, 1000):
        candidate = target.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    return target.with_name(f"{stem}-{os.getpid()}{suffix}")


def start() -> FolderWatcher:
    watcher = FolderWatcher(INBOX_DIR, archive_dir=INBOX_ARCHIVE_DIR)
    threading.Thread(target=watcher.run, daemon=True, name="inbox-watcher").start()
    return watcher
