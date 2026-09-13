"""Verified immutable R2 objects and conditional publication of archive manifests."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from web_search_web_model.archive.records import (
    PREFIX,
    SCHEMA_VERSION,
    digest,
    encode_batch,
    json_bytes,
    utc_text,
)
from web_search_web_model.archive.outbox import Batch


class ArchiveConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class R2Settings:
    bucket: str
    endpoint_url: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    region: str = "auto"

    @classmethod
    def from_env(cls) -> "R2Settings":
        names = (
            "R2_BUCKET",
            "R2_ENDPOINT_URL",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
        )
        missing = [name for name in names if not os.getenv(name, "").strip()]
        if missing:
            raise ValueError("Missing archive settings: " + ", ".join(missing))
        settings = cls(
            *(os.environ[name] for name in names), os.getenv("R2_REGION", "auto")
        )
        endpoint = urlsplit(settings.endpoint_url)
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or not endpoint.hostname.endswith(".r2.cloudflarestorage.com")
            or endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
            or endpoint.path not in ("", "/")
        ):
            raise ValueError("R2_ENDPOINT_URL must be an HTTPS R2 S3 endpoint")
        if settings.region != "auto":
            raise ValueError("R2_REGION must be auto")
        return settings


class ObjectStore:
    def __init__(self, client: Any, bucket: str):
        self.client, self.bucket = client, bucket

    @classmethod
    def from_env(cls) -> "ObjectStore":
        settings = R2Settings.from_env()
        return cls(
            boto3.client(
                "s3",
                endpoint_url=settings.endpoint_url,
                region_name=settings.region,
                aws_access_key_id=settings.access_key_id,
                aws_secret_access_key=settings.secret_access_key,
                config=Config(
                    signature_version="s3v4",
                    connect_timeout=10,
                    read_timeout=60,
                    retries={"mode": "standard", "max_attempts": 3},
                    s3={"addressing_style": "path"},
                    request_checksum_calculation="when_required",
                    response_checksum_validation="when_required",
                ),
            ),
            settings.bucket,
        )

    @staticmethod
    def _key(key: str) -> str:
        if not key.startswith(PREFIX) or ".." in key.split("/"):
            raise ValueError("Object key is outside the link archive")
        return key

    def get(self, key: str) -> tuple[bytes, str] | None:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise
        try:
            return response["Body"].read(), response["ETag"]
        finally:
            response["Body"].close()

    def get_json(self, key: str) -> tuple[dict[str, Any], str] | None:
        result = self.get(key)
        if result is None:
            return None
        value = json.loads(result[0])
        if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported archive manifest")
        return value, result[1]

    def put(self, key: str, body: bytes, *, etag: str | None = None) -> None:
        """Create once, or replace a pointer only if its ETag still matches."""
        condition = {"IfMatch": etag} if etag is not None else {"IfNoneMatch": "*"}
        try:
            self.client.put_object(
                Bucket=self.bucket, Key=self._key(key), Body=body, **condition
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in (
                "PreconditionFailed",
                "ConditionalRequestConflict",
                "412",
                "409",
            ):
                raise
            existing = self.get(key)
            if existing is None or existing[0] != body:
                raise ArchiveConflict(
                    "Archive object changed during publication"
                ) from exc
        verified = self.get(key)
        if verified is None or verified[0] != body:
            raise ArchiveConflict("Archive object failed read-back verification")

    def put_json(
        self, key: str, value: dict[str, Any], *, etag: str | None = None
    ) -> None:
        self.put(key, json_bytes(value), etag=etag)

    def download(self, key: str, path: Path, *, sha256: str) -> None:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        checksum = hashlib.sha256()
        try:
            with path.open("wb") as target:
                for chunk in response["Body"].iter_chunks(chunk_size=1024 * 1024):
                    checksum.update(chunk)
                    target.write(chunk)
        finally:
            response["Body"].close()
        if checksum.hexdigest() != sha256:
            path.unlink(missing_ok=True)
            raise ArchiveConflict("Archive file checksum mismatch")

    def put_file(self, key: str, path: Path) -> dict[str, Any]:
        with path.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
            source.seek(0)
            try:
                self.client.put_object(
                    Bucket=self.bucket, Key=self._key(key), Body=source, IfNoneMatch="*"
                )
            except ClientError as exc:
                if exc.response["Error"]["Code"] not in ("PreconditionFailed", "412"):
                    raise
        verification = path.with_suffix(path.suffix + ".verify")
        try:
            self.download(key, verification, sha256=checksum)
        finally:
            verification.unlink(missing_ok=True)
        return {"key": key, "sha256": checksum, "bytes": path.stat().st_size}

    def list(self, prefix: str) -> Iterator[dict[str, Any]]:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=self._key(prefix)):
            yield from page.get("Contents", [])

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))


def publish_batch(store: ObjectStore, batch: Batch) -> dict[str, Any]:
    data = encode_batch(batch.records)
    created_at = batch.created_at.astimezone(UTC)
    key = f"{PREFIX}updates/{created_at:%Y/%m/%d}/{batch.batch_id}.jsonl.gz"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch.batch_id,
        "created_at": utc_text(batch.created_at),
        "data_key": key,
        "sha256": digest(data),
        "pages": len(batch.records),
        "edges": sum(len(record.outlinks) for record in batch.records),
        "normalization": "crawler-url-admission-v1",
    }
    store.put(key, data)
    store.put_json(f"{PREFIX}commits/{batch.batch_id}.json", manifest)
    return manifest


def committed_batches(store: ObjectStore) -> dict[str, dict[str, Any]]:
    batches = {}
    for item in store.list(f"{PREFIX}commits/"):
        result = store.get_json(item["Key"])
        if result is None:
            raise ArchiveConflict("Committed batch disappeared during read")
        manifest, _ = result
        batch_id = manifest["batch_id"]
        if item["Key"] != f"{PREFIX}commits/{batch_id}.json":
            raise ArchiveConflict("Batch identity does not match its commit key")
        expected = (
            f"{PREFIX}updates/{manifest_time(manifest):%Y/%m/%d}/{batch_id}.jsonl.gz"
        )
        if manifest["data_key"] != expected:
            raise ArchiveConflict("Batch payload is outside its expected object key")
        batches[batch_id] = manifest
    return batches


def read_current(store: ObjectStore) -> tuple[dict[str, Any] | None, str | None]:
    result = store.get_json(f"{PREFIX}current.json")
    return result if result is not None else (None, None)


def manifest_time(manifest: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(manifest["created_at"])
