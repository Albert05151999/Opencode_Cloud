import asyncio

from fastapi.testclient import TestClient

from app.main import create_app
from app.metrics import MetricsMiddleware, PlatformMetrics, route_label


def test_requests_are_counted_and_metric_registries_are_isolated():
    first, second = PlatformMetrics(), PlatformMetrics()
    client = TestClient(create_app(metrics=first))
    assert client.get("/cloud/health").status_code == 200
    assert client.get("/private-user/path").status_code == 404
    body = client.get("/metrics").text
    assert 'cloud_http_requests_total{method="GET",route="/cloud/health",status="200"} 1.0' in body
    assert 'cloud_http_errors_total{method="GET",route="other",status="404"} 1.0' in body
    assert "private-user" not in body
    assert second.registry.get_sample_value("cloud_http_requests_total", {"method": "GET", "route": "/cloud/health", "status": "200"}) is None


def test_arbitrary_paths_do_not_grow_label_cardinality():
    labels = {route_label(f"/session/ses_{i}/message") for i in range(1000)}
    labels |= {route_label(f"/user/{i}/secret") for i in range(1000)}
    assert labels == {"/session/:id/message", "other"}


def test_sse_gauge_is_live_and_cleared_on_cancellation():
    async def exercise():
        metrics = PlatformMetrics()
        opened = asyncio.Event()
        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/event-stream")]})
            await send({"type": "http.response.body", "body": b"data: ready\n\n", "more_body": True})
            opened.set()
            await asyncio.Event().wait()
        async def send(message):
            pass
        async def receive():
            return {"type": "http.disconnect"}
        task = asyncio.create_task(MetricsMiddleware(app, metrics)({"type": "http", "method": "GET", "path": "/event"}, receive, send))
        await opened.wait()
        assert metrics.registry.get_sample_value("cloud_sse_connections") == 1
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert metrics.registry.get_sample_value("cloud_sse_connections") == 0
        assert metrics.registry.get_sample_value("cloud_sse_connection_duration_seconds_count") == 1
    asyncio.run(exercise())
