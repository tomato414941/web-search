import json
import time
from threading import Event
from unittest.mock import Mock

from web_search_web_model.archive import worker


class OneCycle(Event):
    def wait(self, timeout=None):
        self.set()
        return True


def test_failed_compaction_still_collects_abandoned_files_and_reports_unhealthy(
    monkeypatch,
):
    store = Mock()
    monkeypatch.setattr(worker, "read_current", lambda store: (None, None))
    monkeypatch.setattr(
        worker, "compact", Mock(side_effect=RuntimeError("upload failed"))
    )
    cleanup = Mock(return_value=2)
    monkeypatch.setattr(worker, "collect", cleanup)
    state = {}
    worker._maintenance(store, OneCycle(), state)
    cleanup.assert_called_once_with(store)
    assert state["maintenance_ok"] is False


def test_health_requires_recent_successful_upload_and_maintenance(
    tmp_path, monkeypatch
):
    path = tmp_path / "health.json"
    monkeypatch.setattr(worker, "HEARTBEAT", path)
    assert not worker.healthy()
    values = {"updated_at": time.time(), "upload_ok": True, "maintenance_ok": True}
    path.write_text(json.dumps(values))
    assert worker.healthy()
    path.write_text(json.dumps({**values, "maintenance_ok": False}))
    assert not worker.healthy()
    path.write_text(json.dumps({**values, "updated_at": time.time() - 100}))
    assert not worker.healthy()
