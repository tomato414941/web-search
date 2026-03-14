from app import worker


def test_resolve_worker_mode_defaults_to_all():
    assert worker.resolve_worker_mode(["app.worker"]) == "all"


def test_resolve_worker_mode_accepts_explicit_modes():
    assert worker.resolve_worker_mode(["app.worker", "jobs"]) == "jobs"
    assert worker.resolve_worker_mode(["app.worker", "maintenance"]) == "maintenance"


def test_resolve_worker_mode_rejects_unknown_mode():
    try:
        worker.resolve_worker_mode(["app.worker", "invalid"])
    except ValueError as exc:
        assert "Unsupported worker mode" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported worker mode")


def test_build_task_specs_for_jobs(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_WORKERS", 2)

    task_names = [task_name for task_name, _ in worker._build_task_specs("jobs")]

    assert task_names == ["indexer-worker-1", "indexer-worker-2"]


def test_build_task_specs_for_maintenance(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_WORKERS", 2)

    task_names = [task_name for task_name, _ in worker._build_task_specs("maintenance")]

    assert task_names == ["pagerank", "domain-rank", "job-cleanup"]


def test_build_task_specs_for_all(monkeypatch):
    monkeypatch.setattr(worker.settings, "INDEXER_JOB_WORKERS", 2)

    task_names = [task_name for task_name, _ in worker._build_task_specs("all")]

    assert task_names == [
        "pagerank",
        "domain-rank",
        "job-cleanup",
        "indexer-worker-1",
        "indexer-worker-2",
    ]
