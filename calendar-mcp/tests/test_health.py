"""
Tests for health check and root endpoints.

This module tests the basic API health and information endpoints:
- Health check endpoint for monitoring/load balancers
- Root endpoint for API information
"""

import pytest
from fastapi.testclient import TestClient


class TestHealthCheck:
    """Tests for GET /health endpoint."""

    def test_health_check_returns_healthy(self, client: TestClient):
        """
        Verify that the health check endpoint returns healthy status.
        
        Expected behavior:
        - Returns 200 OK status
        - Response body contains {"status": "healthy"}
        
        This endpoint is typically used by:
        - Load balancers to check if the service is running
        - Kubernetes liveness/readiness probes
        - Monitoring systems
        """
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestRootEndpoint:
    """Tests for GET / endpoint."""

    def test_root_returns_api_info(self, client: TestClient):
        """
        Verify that the root endpoint returns API information.
        
        Expected behavior:
        - Returns 200 OK status
        - Response includes API name and version
        - Response includes link to documentation
        """
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "docs" in data
        assert data["name"] == "Calendar MCP Server"

