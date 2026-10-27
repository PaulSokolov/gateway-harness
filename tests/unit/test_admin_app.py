from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from gateway_harness.admin.app import app
from gateway_harness.settings import Settings


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "healthy"}


def test_auth_protection(client):
    # Set ADMIN_TOKEN requirement
    with patch(
        "gateway_harness.admin.app.get_settings",
        return_value=Settings(ADMIN_TOKEN="super-secret-token"),
    ):
        # 1. Unauthenticated request -> 401
        res_unauth = client.get("/api/report")
        assert res_unauth.status_code == 401

        # 2. Invalid token -> 401
        res_bad = client.get("/api/report", headers={"Authorization": "Bearer wrong-token"})
        assert res_bad.status_code == 401

        # 3. Valid Bearer Token -> 200
        with patch("gateway_harness.admin.app.get_current_store"):
            with patch(
                "gateway_harness.admin.app.generate_savings_report",
                return_value={"clusters": [], "summary": {}},
            ):
                res_ok = client.get(
                    "/api/report",
                    headers={"Authorization": "Bearer super-secret-token"},
                )
                assert res_ok.status_code == 200

        # 4. Valid Cookie Token -> 200
        with patch("gateway_harness.admin.app.get_current_store"):
            with patch(
                "gateway_harness.admin.app.generate_savings_report",
                return_value={"clusters": [], "summary": {}},
            ):
                res_cookie = client.get(
                    "/api/report",
                    cookies={"gh_admin_token": "super-secret-token"},
                )
                assert res_cookie.status_code == 200


def test_kill_switch_api(client):
    with patch("gateway_harness.admin.app.set_global_kill", new_callable=AsyncMock) as mock_kill:
        with patch("gateway_harness.admin.app.get_pool", new_callable=AsyncMock):
            res = client.post("/api/kill", json={"enabled": True})
            assert res.status_code == 200
            assert res.json()["global_kill"] is True
            mock_kill.assert_called_once_with(True, actor="admin", pool=mock_kill.call_args[1]["pool"])


def test_pages_rendering(client):
    with patch("gateway_harness.admin.app.get_current_store"):
        with patch(
            "gateway_harness.admin.app.calculate_net_savings",
            return_value={
                "net_savings_usd": 150.0,
                "gross_savings_usd": 160.0,
                "optimizer_cost_usd": 10.0,
            },
        ):
            with patch("gateway_harness.admin.app.get_pool", new_callable=AsyncMock):
                # Overview
                res_overview = client.get("/overview")
                assert res_overview.status_code == 200
                assert "System Overview" in res_overview.text
                assert "150.00" in res_overview.text

                # Proposals
                res_props = client.get("/proposals")
                assert res_props.status_code == 200
                assert "Candidate Routing Proposals" in res_props.text

                # Policies
                res_pols = client.get("/policies")
                assert res_pols.status_code == 200
                assert "Active & Disabled Policies" in res_pols.text

                # Clusters
                res_clusters = client.get("/clusters")
                assert res_clusters.status_code == 200
                assert "Workload Clusters" in res_clusters.text
