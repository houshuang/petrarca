"""Durable, queue-free storage for the Petrarca Companion recorder.

This module deliberately owns no curriculum, card, quiz, or scheduling code. A
capture is firsthand material: retain the audio, retain the transcript, and use
the dedicated exact-speech chunker here to make it searchable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import fcntl


MAX_CAPTURE_BYTES = 25 * 1024 * 1024

_AUDIO_TYPES = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".webm": "audio/webm",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}


def audio_file_details(filename: str) -> tuple[str, str]:
    """Return a safe extension and MIME type for a browser audio filename."""
    suffix = Path(filename or "").suffix.casefold()
    if suffix not in _AUDIO_TYPES:
        # Safari's MediaRecorder commonly omits a useful extension. MP4 is the
        # safest default for the existing native and Soniox path.
        suffix = ".m4a"
    return suffix, _AUDIO_TYPES[suffix]


_CONTENT_CAPTURE_RE = re.compile(r"cpc_sha256_([0-9a-f]{64})")
_LEGACY_CAPTURE_RE = re.compile(r"cpc_[0-9]+_[0-9a-f]{8}")

# ``flock`` provides cross-process exclusion on the production Linux host. A
# keyed Python lock is also required: BSD-derived ``flock`` implementations may
# treat locks as process-scoped, which is not enough for ThreadingHTTPServer.
# Retaining these tiny lock objects for the process lifetime avoids a race where
# one thread removes a lock from the map while another thread is waiting on it.
_CAPTURE_THREAD_LOCKS_GUARD = threading.Lock()
_CAPTURE_THREAD_LOCKS: dict[str, threading.Lock] = {}


def capture_id_for_audio(audio_data: bytes) -> str:
    """Return the stable, content-addressed identity for an upload.

    The server derives this value from the bytes rather than trusting a browser
    identifier.  Replaying the exact multipart upload after a lost HTTPS
    response therefore resolves to the same retained audio and transcript.
    """
    if not audio_data:
        raise ValueError("audio upload is empty")
    return f"cpc_sha256_{hashlib.sha256(audio_data).hexdigest()}"


def _thread_lock_for_capture(capture_id: str) -> threading.Lock:
    with _CAPTURE_THREAD_LOCKS_GUARD:
        return _CAPTURE_THREAD_LOCKS.setdefault(capture_id, threading.Lock())


@contextmanager
def capture_processing_lock(lock_dir: Path, capture_id: str):
    """Serialize one capture across server threads and processes.

    The lock file deliberately remains in the runtime directory after release.
    Unlinking a flock file can let a new request lock a different inode while a
    waiter still holds the old one. ``/run`` is cleared on reboot, and one tiny
    file per single-user recording is bounded enough for this service.
    """
    if not (
        _CONTENT_CAPTURE_RE.fullmatch(capture_id)
        or _LEGACY_CAPTURE_RE.fullmatch(capture_id)
    ):
        raise ValueError("capture id is invalid")

    thread_lock = _thread_lock_for_capture(capture_id)
    with thread_lock:
        lock_dir = Path(lock_dir)
        lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        if lock_dir.is_symlink() or not lock_dir.is_dir():
            raise OSError("capture lock path is not a private directory")
        lock_dir.chmod(0o700)

        directory_flags = os.O_RDONLY
        directory_flags |= getattr(os, "O_CLOEXEC", 0)
        directory_flags |= getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(lock_dir, directory_flags)
        lock_fd = None
        try:
            if not stat.S_ISDIR(os.fstat(directory_fd).st_mode):
                raise OSError("capture lock path is not a directory")
            lock_flags = os.O_CREAT | os.O_RDWR
            lock_flags |= getattr(os, "O_CLOEXEC", 0)
            lock_flags |= getattr(os, "O_NOFOLLOW", 0)
            lock_fd = os.open(
                f"{capture_id}.lock",
                lock_flags,
                0o600,
                dir_fd=directory_fd,
            )
            os.fchmod(lock_fd, 0o600)
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            if lock_fd is not None:
                os.close(lock_fd)
            os.close(directory_fd)


def _validate_capture_id(capture_id: str, audio_data: bytes) -> None:
    match = _CONTENT_CAPTURE_RE.fullmatch(capture_id)
    if match:
        if not hmac.compare_digest(match.group(1), hashlib.sha256(audio_data).hexdigest()):
            raise ValueError("capture id does not match audio content")
        return
    # Keep accepting the timestamp form for already-retained pre-Companion
    # recordings and focused storage tests. New requests never generate it.
    if not _LEGACY_CAPTURE_RE.fullmatch(capture_id):
        raise ValueError("capture id is invalid")


def _same_audio(path: Path, audio_data: bytes) -> bool:
    if path.stat().st_size != len(audio_data):
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return hmac.compare_digest(digest.hexdigest(), hashlib.sha256(audio_data).hexdigest())


def persist_audio(
    audio_dir: Path,
    capture_id: str,
    audio_data: bytes,
    original_filename: str,
) -> tuple[Path, str]:
    """Atomically retain one uploaded recording with private permissions."""
    if not audio_data:
        raise ValueError("audio upload is empty")
    if len(audio_data) > MAX_CAPTURE_BYTES:
        raise ValueError("audio upload exceeds size limit")
    _validate_capture_id(capture_id, audio_data)

    suffix, mime_type = audio_file_details(original_filename)
    target_dir = audio_dir / "commonplace"
    target_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        target_dir.chmod(0o700)
    except OSError:
        pass

    # The same browser Blob should retain its filename on retry, but accept a
    # MIME/extension change without creating a second copy. The content-derived
    # identifier makes a differing existing payload an integrity failure.
    existing_paths = [
        path for path in target_dir.glob(f"{capture_id}.*")
        if path.suffix in _AUDIO_TYPES and path.is_file()
    ]
    for existing in existing_paths:
        if not _same_audio(existing, audio_data):
            raise ValueError("retained audio does not match capture id")
        existing.chmod(0o600)
        _existing_suffix, existing_mime = audio_file_details(existing.name)
        return existing, existing_mime

    target = target_dir / f"{capture_id}{suffix}"
    partial = target_dir / f".{capture_id}.{os.getpid()}.{time.time_ns()}.partial"
    try:
        with open(partial, "xb") as handle:
            handle.write(audio_data)
            handle.flush()
            os.fsync(handle.fileno())
        partial.chmod(0o600)
        try:
            # A hard link publishes the fully-fsynced inode atomically and,
            # unlike replace(), never overwrites a concurrent successful retry.
            os.link(partial, target)
        except FileExistsError:
            if not _same_audio(target, audio_data):
                raise ValueError("retained audio does not match capture id")
        target.chmod(0o600)
        try:
            directory_fd = os.open(target_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # The file itself is already fsynced; some filesystems do not
            # support fsync on a directory descriptor.
            pass
    finally:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
    return target, mime_type


def write_capture_status(audio_path: Path, data: dict) -> Path:
    """Atomically write a small recovery sidecar next to retained audio."""
    sidecar = audio_path.with_suffix(audio_path.suffix + ".json")
    partial = sidecar.parent / (
        f".{sidecar.name}.{os.getpid()}.{time.time_ns()}.partial"
    )
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    try:
        with open(partial, "xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        partial.chmod(0o600)
        partial.replace(sidecar)
        sidecar.chmod(0o600)
    finally:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
    return sidecar


def relative_audio_path(audio_path: Path, audio_dir: Path) -> str:
    """Stable data-relative path stored with the transcript row."""
    try:
        return str(Path("audio") / audio_path.relative_to(audio_dir))
    except ValueError:
        return str(audio_path)


def insert_capture_transcript(
    conn,
    *,
    capture_id: str,
    transcript: str,
    audio_bytes: int,
    audio_path: str,
    created_at: int | None = None,
) -> bool:
    """Insert the firsthand transcript only; never create scheduled material."""
    if not transcript.strip():
        raise ValueError("transcript is empty")
    cursor = conn.execute(
        """INSERT OR IGNORE INTO voice_transcripts
           (id, source, node_id, domain_id, node_title, transcript,
            audio_bytes, llm_result, microlearning_triggered, created_at,
            input_mode, audio_path)
           VALUES (?, 'commonplace_capture', NULL, NULL, NULL, ?, ?, NULL,
                   '[]', ?, 'audio', ?)""",
        (
            capture_id,
            transcript.strip(),
            audio_bytes,
            created_at if created_at is not None else int(time.time() * 1000),
            audio_path,
        ),
    )
    return cursor.rowcount > 0


def _authored_segments(transcript: str) -> list[str]:
    """Split exact authored speech deterministically, without paraphrasing it."""
    paragraphs = [part.strip() for part in transcript.split("\n") if part.strip()]
    if len(paragraphs) > 1:
        return [part for part in paragraphs if part]

    words = transcript.strip().split()
    return [" ".join(words[index:index + 80]) for index in range(0, len(words), 80)]


def create_authored_chunks(
    conn,
    *,
    transcript_id: str,
    transcript: str,
    embed_batch=None,
) -> int:
    """Index only exact ``raw_speech`` chunks for a Companion capture.

    This deliberately does not call the general learner-profile chunker: that
    path also creates entity/curriculum links.  Companion recordings are
    searchable firsthand material, not evidence that should alter the learner
    model or review stream.
    """
    existing = conn.execute(
        "SELECT COUNT(*) FROM transcript_chunks WHERE transcript_id = ?",
        (transcript_id,),
    ).fetchone()
    if existing and int(existing[0]) > 0:
        return 0

    segments = _authored_segments(transcript)
    if not segments:
        return 0

    if embed_batch is None:
        from limbic.amygdala import EmbeddingModel

        embed_batch = EmbeddingModel().embed_batch

    import numpy as np

    embeddings = embed_batch(segments)
    if len(embeddings) != len(segments):
        raise ValueError("embedding count does not match authored chunk count")

    for index, (segment, embedding) in enumerate(zip(segments, embeddings)):
        identity = hashlib.sha256(
            f"{transcript_id}:{index}".encode("utf-8")
        ).hexdigest()[:12]
        blob = np.asarray(embedding, dtype=np.float32).tobytes()
        conn.execute(
            """INSERT OR IGNORE INTO transcript_chunks
               (id, transcript_id, chunk_text, chunk_type, embedding)
               VALUES (?, ?, ?, 'raw_speech', ?)""",
            (identity, transcript_id, segment, blob),
        )
    return len(segments)
