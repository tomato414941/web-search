from datetime import UTC, datetime
import hashlib
from io import BytesIO

import pytest
from botocore.exceptions import ClientError
from botocore.response import StreamingBody

from web_search_core.testing import ensure_test_pg
from web_search_postgres.migrate import migrate
from web_search_web_model.archive.outbox import transaction
from web_search_web_model.archive.store import ObjectStore

ensure_test_pg()


@pytest.fixture(scope="session", autouse=True)
def _schema():
    migrate()


@pytest.fixture(autouse=True)
def _reset_archive():
    with transaction() as cur:
        cur.execute(
            "TRUNCATE link_outbox, link_archive_batches, url_referring_hosts, urls, documents, page_ranks, domain_ranks CASCADE"
        )
        cur.execute("""UPDATE link_archive_state SET pending_bytes = 0,
            legacy_started_at = NULL, legacy_last_src = NULL, legacy_pages = 0,
            legacy_edges = 0, legacy_complete = FALSE WHERE singleton""")
        cur.execute("ALTER TABLE legacy_links DISABLE TRIGGER freeze_legacy_links")
        cur.execute("TRUNCATE legacy_links")
        cur.execute("ALTER TABLE legacy_links ENABLE TRIGGER freeze_legacy_links")


class FakeS3:
    """An in-memory S3 transport with ETag conditions and paginated listing."""

    def __init__(self):
        self.objects = {}
        self.now = datetime(2026, 1, 1, tzinfo=UTC)
        self.puts = []

    def put_object(self, *, Bucket, Key, Body, IfMatch=None, IfNoneMatch=None):
        self.puts.append((Key, IfMatch, IfNoneMatch))
        previous = self.objects.get(Key)
        if (IfNoneMatch == "*" and previous is not None) or (
            IfMatch is not None and (previous is None or previous[1] != IfMatch)
        ):
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        data = Body if isinstance(Body, bytes) else Body.read()
        etag = '"' + hashlib.sha256(data).hexdigest() + '"'
        self.objects[Key] = (data, etag, self.now)
        return {"ETag": etag}

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        data, etag, _ = self.objects[Key]
        return {"Body": StreamingBody(BytesIO(data), len(data)), "ETag": etag}

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return self

    def paginate(self, *, Bucket, Prefix):
        rows = [
            {"Key": key, "LastModified": value[2]}
            for key, value in sorted(self.objects.items())
            if key.startswith(Prefix)
        ]
        for index in range(0, len(rows), 2):
            yield {"Contents": rows[index : index + 2]}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop(Key, None)


@pytest.fixture
def object_store():
    return ObjectStore(FakeS3(), "test-link-archive")
