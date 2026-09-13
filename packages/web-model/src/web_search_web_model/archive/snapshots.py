"""Bounded-memory Parquet snapshots, latest-state reads, and safe collection."""

from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterator
from uuid import uuid4

import duckdb

from web_search_web_model.archive.locks import archive_lock
from web_search_web_model.archive.outbox import pending_batch_ids
from web_search_web_model.archive.records import (
    PREFIX,
    SCHEMA_VERSION,
    Observation,
    shard_for,
    utc_text,
)
from web_search_web_model.archive.store import (
    ArchiveConflict,
    ObjectStore,
    committed_batches,
    manifest_time,
    read_current,
)

COLUMNS = "src VARCHAR, src_host VARCHAR, revision BIGINT, observed_at TIMESTAMPTZ, outlinks VARCHAR[]"
FIELDS = "src, src_host, revision, observed_at, outlinks"
JSON_COLUMNS = """{src: 'VARCHAR', src_host: 'VARCHAR', revision: 'BIGINT',
    observed_at: 'TIMESTAMPTZ', outlinks: 'VARCHAR[]'}"""
RETENTION_GRACE = timedelta(hours=24)


@contextmanager
def workspace() -> Iterator[tuple[Any, Path]]:
    with TemporaryDirectory(prefix="link-archive-") as directory:
        root = Path(directory)
        con = duckdb.connect(
            config={
                "memory_limit": "256MB",
                "threads": "1",
                "temp_directory": str(root / "spill"),
                "preserve_insertion_order": "false",
            }
        )
        try:
            # Large list columns can outgrow the memory budget before a default
            # 122,880-row group is flushed. Keep the temporary database groups small.
            path = str(root / "work.duckdb").replace("'", "''")
            con.execute(f"ATTACH '{path}' AS archive_work (ROW_GROUP_SIZE 2048)")
            con.execute("USE archive_work")
            con.execute("SET TimeZone = 'UTC'")
            yield con, root
        finally:
            con.close()


def load_updates(
    root: Path, store: ObjectStore, batches: dict[str, dict[str, Any]]
) -> None:
    path = root / "update.jsonl.gz"
    # Partition in one streaming pass. Each SQL operation then reads only its
    # shard, without sorting or scanning the full graph 256 times.
    with ExitStack() as streams:
        writers = {}
        for manifest in batches.values():
            store.download(manifest["data_key"], path, sha256=manifest["sha256"])
            pages = edges = 0
            with gzip.open(path, "rb") as source:
                for line in source:
                    record = Observation.decode(line)
                    pages += 1
                    edges += len(record.outlinks)
                    shard = shard_for(record.src)
                    if shard not in writers:
                        writers[shard] = streams.enter_context(
                            gzip.open(
                                root / f"updates-{shard}.jsonl.gz",
                                "wb",
                                compresslevel=1,
                            )
                        )
                    writers[shard].write(line)
            if pages != manifest["pages"] or edges != manifest["edges"]:
                raise ArchiveConflict(
                    "Update batch record counts do not match its manifest"
                )
            path.unlink()


def snapshot_manifest(store: ObjectStore, key: str) -> dict[str, Any]:
    result = store.get_json(key)
    if result is None:
        raise ArchiveConflict("Snapshot manifest is missing")
    manifest = result[0]
    if key != f"{PREFIX}snapshots/{manifest['generation']}/manifest.json":
        raise ArchiveConflict("Snapshot identity does not match its key")
    for item in manifest["files"]:
        if (
            item["key"]
            != f"{PREFIX}snapshots/{manifest['generation']}/shard={item['shard']}/part-00000.parquet"
        ):
            raise ArchiveConflict("Snapshot file is outside its generation")
    return manifest


def prepare_shard(
    con: Any,
    root: Path,
    store: ObjectStore,
    shard: str,
    previous: dict[str, Any] | None,
) -> None:
    con.execute(f"CREATE OR REPLACE TABLE candidates ({COLUMNS})")
    if previous is not None:
        path = root / "previous.parquet"
        store.download(previous["key"], path, sha256=previous["sha256"])
        con.execute(
            f"INSERT INTO candidates SELECT {FIELDS} FROM read_parquet(?)", [str(path)]
        )
        path.unlink()
    path = root / f"updates-{shard}.jsonl.gz"
    if path.exists():
        con.execute(
            f"INSERT INTO candidates SELECT {FIELDS} FROM read_json(?, format='newline_delimited', columns={JSON_COLUMNS})",
            [str(path)],
        )
    conflict = con.execute("""SELECT 1 FROM candidates GROUP BY src, revision
        HAVING count(DISTINCT (src_host, observed_at, outlinks)) > 1 LIMIT 1""").fetchone()
    if conflict:
        raise ArchiveConflict(
            "The same source and revision have different observations"
        )
    # Select the page version BEFORE expanding outlinks. Empty lists must survive.
    con.execute(f"""CREATE OR REPLACE TABLE latest AS SELECT {FIELDS}
        FROM candidates QUALIFY row_number() OVER (PARTITION BY src ORDER BY revision DESC) = 1""")
    con.execute("CHECKPOINT")


def compact(store: ObjectStore, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    with archive_lock(maintenance=True), workspace() as (con, root):
        current, etag = read_current(store)
        previous = (
            snapshot_manifest(store, current["manifest_key"]) if current else None
        )
        batches = committed_batches(store)
        covered = set(previous["included_batches"]) if previous else set()
        updates = {key: value for key, value in batches.items() if key not in covered}
        load_updates(root, store, updates)
        generation = str(uuid4())
        files, pages, edges = [], 0, 0
        previous_files = (
            {item["shard"]: item for item in previous["files"]} if previous else {}
        )
        for number in range(256):
            shard = f"{number:02x}"
            prepare_shard(con, root, store, shard, previous_files.get(shard))
            page_count, edge_count = con.execute(
                "SELECT count(*), coalesce(sum(len(outlinks)), 0) FROM latest"
            ).fetchone()
            if not page_count:
                continue
            path = root / "snapshot.parquet"
            con.execute(
                f"COPY (SELECT {FIELDS} FROM latest ORDER BY src) TO ? (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 3, ROW_GROUP_SIZE 2048)",
                [str(path)],
            )
            key = f"{PREFIX}snapshots/{generation}/shard={shard}/part-00000.parquet"
            item = store.put_file(key, path)
            item.update(shard=shard, pages=page_count, edges=edge_count)
            files.append(item)
            pages += page_count
            edges += edge_count
            path.unlink()
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "generation": generation,
            "created_at": utc_text(now),
            "files": files,
            "pages": pages,
            "edges": edges,
            # Keep exact IDs only for still-existing commits, never a sequence watermark.
            "included_batches": sorted(batches),
        }
        key = f"{PREFIX}snapshots/{generation}/manifest.json"
        store.put_json(key, manifest)
        store.put_json(
            f"{PREFIX}current.json",
            {
                "schema_version": SCHEMA_VERSION,
                "manifest_key": key,
                "previous_manifest_key": current["manifest_key"] if current else None,
                "created_at": utc_text(now),
            },
            etag=etag,
        )
        return manifest


def iter_latest(
    store: ObjectStore, *, src: str | None = None, manifest_key: str | None = None
) -> Iterator[Observation]:
    """Pin files against collection while reading a snapshot or snapshot + updates."""
    with archive_lock(), workspace() as (con, root):
        current, _ = read_current(store)
        key = manifest_key or (current["manifest_key"] if current else None)
        snapshot = snapshot_manifest(store, key) if key else None
        if manifest_key is None:
            covered = set(snapshot["included_batches"]) if snapshot else set()
            batches = {
                key: value
                for key, value in committed_batches(store).items()
                if key not in covered
            }
            load_updates(root, store, batches)
        files = {item["shard"]: item for item in snapshot["files"]} if snapshot else {}
        shards = (
            [shard_for(src)]
            if src is not None
            else [f"{number:02x}" for number in range(256)]
        )
        for shard in shards:
            prepare_shard(con, root, store, shard, files.get(shard))
            sql = f"SELECT {FIELDS} FROM latest"
            cursor = con.execute(
                sql + " WHERE src = ?" if src is not None else sql,
                [src] if src is not None else [],
            )
            while rows := cursor.fetchmany(1_000):
                for source, host, revision, observed_at, outlinks in rows:
                    yield Observation(
                        source,
                        host,
                        revision,
                        utc_text(observed_at) if observed_at else None,
                        outlinks,
                    )


def collect(store: ObjectStore, *, now: datetime | None = None) -> int:
    """Keep two published generations; remove only covered or abandoned objects."""
    now = now or datetime.now(UTC)
    cutoff = now - RETENTION_GRACE
    deleted = 0
    with archive_lock(exclusive=True, maintenance=True):
        current, _ = read_current(store)
        retained_keys = (
            [
                current[key]
                for key in ("manifest_key", "previous_manifest_key")
                if current.get(key)
            ]
            if current
            else []
        )
        retained = [snapshot_manifest(store, key) for key in retained_keys]
        covered = (
            (
                set(retained[0]["included_batches"])
                & set(retained[1]["included_batches"])
            )
            if len(retained) == 2
            else set()
        )
        pending = pending_batch_ids()
        batches = committed_batches(store)
        for batch_id, manifest in batches.items():
            if (
                batch_id in covered
                and batch_id not in pending
                and manifest_time(manifest) < cutoff
            ):
                # Remove the marker first. Both retained snapshots already cover it.
                store.delete(f"{PREFIX}commits/{batch_id}.json")
                store.delete(manifest["data_key"])
                deleted += 2
        live_updates = {
            manifest["data_key"]
            for batch_id, manifest in batches.items()
            if batch_id not in covered
            or batch_id in pending
            or manifest_time(manifest) >= cutoff
        }
        for item in store.list(f"{PREFIX}updates/"):
            batch_id = item["Key"].rsplit("/", 1)[-1].removesuffix(".jsonl.gz")
            if (
                item["Key"] not in live_updates
                and batch_id not in pending
                and item["LastModified"] < cutoff
            ):
                store.delete(item["Key"])
                deleted += 1
        keep = set(retained_keys)
        keep.update(item["key"] for manifest in retained for item in manifest["files"])
        for item in store.list(f"{PREFIX}snapshots/"):
            if item["Key"] not in keep and item["LastModified"] < cutoff:
                store.delete(item["Key"])
                deleted += 1
    return deleted
