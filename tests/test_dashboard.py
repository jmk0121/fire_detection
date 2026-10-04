from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_dashboard_and_static_assets_are_served(self) -> None:
        page = self.client.get("/")
        stylesheet = self.client.get("/static/styles.css")
        script = self.client.get("/static/app.js")

        self.assertEqual(page.status_code, 200)
        self.assertIn("화재 현장 브리핑", page.text)
        self.assertEqual(stylesheet.status_code, 200)
        self.assertEqual(script.status_code, 200)

    def test_live_endpoint_explains_missing_sensor_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "live_dashboard.json"
            with patch("app.main.LIVE_SNAPSHOT_PATH", missing_path):
                response = self.client.get("/api/v1/live")

        self.assertEqual(response.status_code, 404)
        self.assertIn("ESP32", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
