from fastapi.testclient import TestClient

from frontend.api.main import app
from frontend.api.metrics import REQUEST_COUNT

client = TestClient(app)


def _request_count_total() -> float:
    total = 0.0
    for metric in REQUEST_COUNT.collect():
        for sample in metric.samples:
            if sample.name == "http_requests_total":
                total += float(sample.value)
    return total


def test_metrics_scrape_does_not_increment_request_counter():
    before = _request_count_total()

    response = client.get("/api/v1/metrics")

    after = _request_count_total()

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert after == before
