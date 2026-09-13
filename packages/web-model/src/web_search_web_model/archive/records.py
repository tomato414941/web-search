"""Canonical records shared by the outbox, update logs, and snapshots."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import gzip
import hashlib
import io
import json
from typing import Iterable

PREFIX = "links/v1/"
SCHEMA_VERSION = 1
BATCH_PAGES = 5_000
BATCH_BYTES = 16 * 1024 * 1024
FLUSH_SECONDS = 300


def json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def shard_for(src: str) -> str:
    return digest(src.encode("utf-8"))[:2]


@dataclass(frozen=True)
class Observation:
    src: str
    src_host: str
    revision: int
    observed_at: str | None
    outlinks: list[str]

    def encode(self) -> bytes:
        return json_bytes(asdict(self)) + b"\n"

    @classmethod
    def decode(cls, data: bytes | str) -> "Observation":
        value = json.loads(data)
        if not isinstance(value, dict) or set(value) != {
            "src",
            "src_host",
            "revision",
            "observed_at",
            "outlinks",
        }:
            raise ValueError("Invalid link observation fields")
        record = cls(**value)
        if (
            not isinstance(record.src, str)
            or not record.src
            or not isinstance(record.src_host, str)
            or type(record.revision) is not int
            or record.revision < 0
            or not isinstance(record.outlinks, list)
            or any(not isinstance(dst, str) or not dst for dst in record.outlinks)
        ):
            raise ValueError("Invalid link observation")
        if (
            record.outlinks != sorted(set(record.outlinks))
            or record.src in record.outlinks
        ):
            raise ValueError("Outlinks must be sorted, unique, and exclude the source")
        if record.observed_at is None:
            if record.revision != 0:
                raise ValueError("Only legacy observations may have unknown timestamps")
        elif not isinstance(record.observed_at, str) or not record.observed_at.endswith(
            "Z"
        ):
            raise ValueError("Observation timestamps must be UTC")
        else:
            datetime.fromisoformat(record.observed_at)
        return record


def encode_batch(records: Iterable[Observation]) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, filename="", mode="wb", mtime=0) as target:
        for record in records:
            target.write(record.encode())
    return buffer.getvalue()
