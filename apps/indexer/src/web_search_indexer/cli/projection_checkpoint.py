"""Durable progress for a rebuild against one source and physical index."""

from dataclasses import asdict, dataclass
import fcntl
import json
import os
from pathlib import Path
import tempfile


@dataclass(slots=True)
class ProjectionProgress:
    last_url: str | None = None
    scanned: int = 0
    indexed: int = 0
    complete: bool = False


class ProjectionCheckpoint:
    def __init__(self, path: Path):
        self.path = path
        self._lock_fd: int | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(self.path.name + ".lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(lock_fd)
            raise
        self._lock_fd = lock_fd
        return self

    def __exit__(self, *_):
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None

    def load(self, identity: dict) -> ProjectionProgress:
        if not self.path.exists():
            return ProjectionProgress()
        payload = json.loads(self.path.read_text())
        if payload.get("version") != 1 or payload.get("identity") != identity:
            raise ValueError("Checkpoint source, index, or projection does not match")
        progress = ProjectionProgress(**payload["progress"])
        if (
            not (progress.last_url is None or isinstance(progress.last_url, str))
            or type(progress.scanned) is not int
            or type(progress.indexed) is not int
            or not 0 <= progress.indexed <= progress.scanned
            or type(progress.complete) is not bool
            or (progress.scanned > 0 and not progress.last_url)
        ):
            raise ValueError("Invalid rebuild checkpoint progress")
        return progress

    def save(self, identity: dict, progress: ProjectionProgress) -> None:
        payload = {"version": 1, "identity": identity, "progress": asdict(progress)}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix="." + self.path.name + ".",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
