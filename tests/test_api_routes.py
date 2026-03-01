"""Smoke tests for API route endpoints via FastAPI TestClient.

These tests verify that endpoints return expected status codes and
response shapes against an empty SQLite test database. No seed data
is inserted, so most list endpoints return empty results (200 with []).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestHealthEndpoints:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestISOEndpoints:
    def test_list_isos_empty(self, client):
        resp = client.get("/api/v1/isos")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_zones_iso_not_found(self, client):
        resp = client.get("/api/v1/isos/nonexistent/zones")
        assert resp.status_code == 404

    def test_classifications_iso_not_found(self, client):
        resp = client.get("/api/v1/isos/nonexistent/classifications")
        assert resp.status_code == 404

    def test_overview(self, client):
        resp = client.get("/api/v1/overview")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestMultiISOEndpoints:
    def test_multi_classifications_empty(self, client):
        resp = client.get("/api/v1/classifications?iso_ids=pjm,miso")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_multi_pnodes_empty(self, client):
        resp = client.get("/api/v1/pnodes?iso_ids=pjm")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_multi_recommendations_empty(self, client):
        resp = client.get("/api/v1/recommendations?iso_ids=pjm")
        assert resp.status_code == 200
        assert resp.json() == []


class TestCongestionEndpoints:
    def test_list_bas(self, client):
        resp = client.get("/api/v1/congestion/bas")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_scores(self, client):
        resp = client.get("/api/v1/congestion/scores")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_ba_scores_not_found(self, client):
        resp = client.get("/api/v1/congestion/scores/NONEXISTENT")
        assert resp.status_code == 404


class TestHostingCapacityEndpoints:
    def test_list_utilities(self, client):
        resp = client.get("/api/v1/utilities")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_hc_records_not_found(self, client):
        resp = client.get("/api/v1/utilities/nonexistent/hosting-capacity")
        assert resp.status_code == 404


class TestReviewEndpoints:
    def test_review_queue(self, client):
        resp = client.get("/api/v1/review/queue")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_review_stats(self, client):
        resp = client.get("/api/v1/review/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "pending" in data


class TestMonitorEndpoints:
    def test_monitor_health(self, client):
        resp = client.get("/api/v1/monitor/health")
        # May return 200 or 503 depending on DB state
        assert resp.status_code in (200, 503)
        data = resp.json()
        assert "status" in data
        assert "checks" in data

    def test_monitor_jobs(self, client):
        resp = client.get("/api/v1/monitor/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "events" in data


class TestDataCenterEndpoints:
    def test_list_data_centers(self, client):
        resp = client.get("/api/v1/data-centers")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_pipeline_runs(self, client):
        resp = client.get("/api/v1/pipeline/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
