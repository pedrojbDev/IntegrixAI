import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from app.core.metrics.prometheus import (
    PrometheusHttpMetricsMiddleware,
    render_prometheus_metrics,
)
from app.main import app


class PrometheusMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_internal_endpoint_exposes_http_metrics_and_is_hidden_from_openapi(
        self,
    ) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": ""}):
                openapi_response = await client.get("/openapi.json")
                metrics_response = await client.get("/internal/metrics")

        self.assertEqual(200, openapi_response.status_code)
        self.assertEqual(200, metrics_response.status_code)
        self.assertTrue(metrics_response.headers["content-type"].startswith("text/plain"))
        self.assertIn(
            'integrix_http_requests_total{method="GET",route="__unmatched__",status="200"}',
            metrics_response.text,
        )
        self.assertNotIn("/internal/metrics", openapi_response.json()["paths"])

    async def test_scrape_endpoint_does_not_instrument_itself(self) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": ""}):
                await client.get("/internal/metrics")
                metrics_response = await client.get("/internal/metrics")

        self.assertNotIn('route="/internal/metrics"', metrics_response.text)

    async def test_unknown_paths_share_a_bounded_route_label(self) -> None:
        sensitive_path = "/not-found/phone-5511999999999"

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": ""}):
                response = await client.get(sensitive_path)
                metrics_response = await client.get("/internal/metrics")

        self.assertEqual(404, response.status_code)
        self.assertIn(
            'integrix_http_requests_total{method="GET",route="__unmatched__",status="404"}',
            metrics_response.text,
        )
        self.assertNotIn(sensitive_path, metrics_response.text)
        self.assertNotIn("5511999999999", metrics_response.text)

    async def test_unknown_http_methods_share_a_bounded_label(self) -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": ""}):
                response = await client.request("CUSTOM-5511999999999", "/not-found")
                metrics_response = await client.get("/internal/metrics")

        self.assertEqual(404, response.status_code)
        self.assertIn(
            'integrix_http_requests_total{method="OTHER",route="__unmatched__",status="404"}',
            metrics_response.text,
        )
        self.assertNotIn("CUSTOM-5511999999999", metrics_response.text)

    async def test_unhandled_errors_are_recorded_as_500(self) -> None:
        error_app = FastAPI()
        error_app.add_middleware(PrometheusHttpMetricsMiddleware)

        @error_app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("expected test error")

        transport = httpx.ASGITransport(app=error_app, raise_app_exceptions=False)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            with patch.dict(os.environ, {"PROMETHEUS_MULTIPROC_DIR": ""}):
                response = await client.get("/boom")
                content, _ = render_prometheus_metrics()

        self.assertEqual(500, response.status_code)
        self.assertIn(
            b'integrix_http_requests_total{method="GET",route="/boom",status="500"}',
            content,
        )

    async def test_multiprocess_registry_aggregates_worker_counters(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        increment_code = (
            "from app.core.metrics.prometheus import HTTP_REQUESTS_TOTAL;"
            "HTTP_REQUESTS_TOTAL.labels("
            "method='GET',route='/worker-test',status='200'"
            ").inc()"
        )
        render_code = (
            "from app.core.metrics.prometheus import render_prometheus_metrics;"
            "print(render_prometheus_metrics()[0].decode(),end='')"
        )

        with tempfile.TemporaryDirectory() as multiprocess_dir:
            env = dict(os.environ)
            env["PROMETHEUS_MULTIPROC_DIR"] = multiprocess_dir

            for _ in range(2):
                increment = subprocess.run(
                    [sys.executable, "-c", increment_code],
                    cwd=project_root,
                    env=env,
                    capture_output=True,
                    check=False,
                    text=True,
                )
                self.assertEqual(0, increment.returncode, increment.stderr)

            rendered = subprocess.run(
                [sys.executable, "-c", render_code],
                cwd=project_root,
                env=env,
                capture_output=True,
                check=False,
                text=True,
            )

        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertIn(
            'integrix_http_requests_total{method="GET",route="/worker-test",status="200"} 2.0',
            rendered.stdout,
        )


if __name__ == "__main__":
    unittest.main()
