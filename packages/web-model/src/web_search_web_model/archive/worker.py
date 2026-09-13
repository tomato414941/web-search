"""Automatic outbox upload, daily compaction, and covered-object collection."""

from datetime import UTC, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import signal
import threading
import time

from web_search_web_model.archive.locks import archive_lock
from web_search_web_model.archive.outbox import acknowledge, claim_batch, status
from web_search_web_model.archive.records import PREFIX
from web_search_web_model.archive.snapshots import collect, compact
from web_search_web_model.archive.store import (
    ObjectStore,
    manifest_time,
    publish_batch,
    read_current,
)

logger = logging.getLogger(__name__)
HEARTBEAT = Path("/tmp/link-archive-health.json")


def flush_once(store: ObjectStore, *, force: bool = False) -> int:
    with archive_lock(uploader=True):
        batch = claim_batch(force=force)
        if batch is None:
            return 0
        publish_batch(store, batch)
        acknowledge(batch)
        return len(batch.records)


def _maintenance(
    store: ObjectStore, stop: threading.Event, state: dict[str, bool]
) -> None:
    last_collection = 0.0
    while not stop.is_set():
        succeeded = True
        try:
            current, _ = read_current(store)
            if current is None or datetime.now(UTC) - manifest_time(
                current
            ) >= timedelta(days=1):
                result = compact(store)
                logger.info(
                    "Link snapshot published: pages=%d edges=%d",
                    result["pages"],
                    result["edges"],
                )
        except Exception:
            succeeded = False
            logger.exception("Link snapshot failed; retrying in 60 seconds")
        try:
            if not last_collection or time.monotonic() - last_collection >= 3600:
                removed = collect(store)
                logger.info("Link archive collection: objects=%d", removed)
                last_collection = time.monotonic()
        except Exception:
            succeeded = False
            logger.exception("Link archive collection failed; retrying in 60 seconds")
        state["maintenance_ok"] = succeeded
        stop.wait(60)


def run() -> None:
    logging.basicConfig(level=logging.INFO)
    store = ObjectStore.from_env()
    # Establish connectivity before Compose admits crawler startup.
    next(store.list(f"{PREFIX}commits/"), None)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    state = {"maintenance_ok": False}
    maintenance = threading.Thread(
        target=_maintenance, args=(store, stop, state), name="link-snapshots"
    )
    maintenance.start()
    try:
        while not stop.is_set():
            failed = False
            try:
                pages = flush_once(store)
                if pages:
                    logger.info("Archived link observations: pages=%d", pages)
            except Exception:
                failed = True
                logger.exception("Link upload failed; pending observations retained")
            heartbeat = {"updated_at": time.time(), "upload_ok": not failed, **state}
            temporary = HEARTBEAT.with_suffix(".tmp")
            temporary.write_text(json.dumps(heartbeat))
            os.replace(temporary, HEARTBEAT)
            if failed:
                logger.warning("Link archive backlog: %s", status())
            stop.wait(10 if failed else 1)
    finally:
        stop.set()
        maintenance.join()
        HEARTBEAT.unlink(missing_ok=True)


def healthy() -> bool:
    try:
        value = json.loads(HEARTBEAT.read_text())
        return (
            value["upload_ok"]
            and value["maintenance_ok"]
            and time.time() - value["updated_at"] < 90
        )
    except (OSError, ValueError, KeyError):
        return False
