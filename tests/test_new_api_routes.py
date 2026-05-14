"""Smoke tests for the refocused API routes.

Verifies endpoints return expected status codes and response shapes
against an empty SQLite test database.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# -- Constraint routes (/api) ------------------------------------------------

class TestResolveEndpoint:
    def test_resolve_returns_structure(self, client):
        resp = client.get("/api/resolve?lat=40.0&lon=-75.0")
        assert resp.status_code == 200
        data = resp.json()
        assert "lat" in data
        assert "lon" in data
        assert "constraints" in data
        assert "resolution_depth" in data

    def test_resolve_missing_params(self, client):
        resp = client.get("/api/resolve")
        assert resp.status_code == 422


class TestISOs:
    def test_list_isos(self, client):
        resp = client.get("/api/isos")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_isos_filter_rto(self, client):
        resp = client.get("/api/isos?is_rto=true")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestZones:
    def test_list_zones_not_found(self, client):
        resp = client.get("/api/zones/NONEXISTENT")
        assert resp.status_code == 404

    def test_zone_geometry_not_found(self, client):
        resp = client.get("/api/zones/NONEXISTENT/geometry")
        assert resp.status_code == 404

    def test_zone_constraints_not_found(self, client):
        resp = client.get("/api/zones/NONEXISTENT/FAKEZONE/constraints")
        assert resp.status_code == 404

    def test_zone_lmps_not_found(self, client):
        resp = client.get("/api/zones/NONEXISTENT/FAKEZONE/lmps")
        assert resp.status_code == 404


class TestLocationProfile:
    def test_location_profile_not_found(self, client):
        resp = client.get("/api/locations/zone/99999/profile")
        assert resp.status_code == 404


# -- Valuation routes (/api/valuations) ---------------------------------------

class TestProspectiveValuation:
    def test_prospective_bad_location(self, client):
        resp = client.post("/api/valuations/prospective", json={
            "lat": 0.0, "lon": 0.0, "der_type": "solar",
        })
        assert resp.status_code == 400

    def test_prospective_missing_body(self, client):
        resp = client.post("/api/valuations/prospective")
        assert resp.status_code == 422


class TestCompare:
    def test_compare_returns_structure(self, client):
        resp = client.get("/api/valuations/compare?lat=40.0&lon=-75.0")
        # Returns 400 because no zones exist, or 200 with empty
        assert resp.status_code in (200, 400)

    def test_compare_missing_params(self, client):
        resp = client.get("/api/valuations/compare")
        assert resp.status_code == 422


class TestRankings:
    def test_rankings_not_found(self, client):
        resp = client.get("/api/valuations/rankings?iso_code=NONEXISTENT&der_type=solar")
        assert resp.status_code == 404

    def test_rankings_missing_params(self, client):
        resp = client.get("/api/valuations/rankings")
        assert resp.status_code == 422


class TestBatchValuation:
    def test_batch_requires_auth(self, client):
        resp = client.post("/api/valuations/batch", json={"items": []})
        assert resp.status_code == 401


# -- Profile routes (/api/profiles) -------------------------------------------

class TestConstraintProfile:
    def test_constraint_profile_not_found(self, client):
        resp = client.get("/api/profiles/constraint/99999")
        assert resp.status_code == 404


class TestDERProfiles:
    def test_list_der_profiles(self, client):
        resp = client.get("/api/profiles/der")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_der_profile_not_found(self, client):
        resp = client.get("/api/profiles/der/nonexistent_type")
        assert resp.status_code == 404


class TestIntersection:
    def test_intersection_missing_params(self, client):
        resp = client.get("/api/profiles/intersection")
        assert resp.status_code == 422

    def test_intersection_not_found(self, client):
        resp = client.get("/api/profiles/intersection?constraint_profile_id=99999&der_type=solar")
        assert resp.status_code == 404


# -- Enrichment routes (/api/enrichment) --------------------------------------

class TestHostingCapacity:
    def test_nearby_hosting_capacity(self, client):
        resp = client.get("/api/enrichment/hosting-capacity?lat=40.0&lon=-75.0")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestInterconnectionQueue:
    def test_nearby_interconnection(self, client):
        resp = client.get("/api/enrichment/interconnection-queue?lat=40.0&lon=-75.0")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_all_interconnection(self, client):
        resp = client.get("/api/enrichment/interconnection-queue/all")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestUtilities:
    def test_list_utilities(self, client):
        resp = client.get("/api/enrichment/utilities")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_utility_filings_not_found(self, client):
        resp = client.get("/api/enrichment/filings/NONEXISTENT")
        assert resp.status_code == 404


# -- Admin routes (/api/admin) ------------------------------------------------

class TestAdmin:
    def test_computation_runs_requires_auth(self, client):
        resp = client.get("/api/admin/computation-runs")
        assert resp.status_code == 401

    def test_recompute_requires_auth(self, client):
        resp = client.post("/api/admin/recompute")
        assert resp.status_code == 401

    def test_refresh_matviews_requires_auth(self, client):
        resp = client.post("/api/admin/refresh-matviews")
        assert resp.status_code == 401
