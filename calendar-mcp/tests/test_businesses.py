"""
Tests for Business CRUD endpoints.

This module tests the /businesses endpoints including:
- Creating businesses with valid and invalid data
- Retrieving business details
- Updating business fields
- Deleting businesses
- Listing all businesses
"""

import pytest
from fastapi.testclient import TestClient


class TestCreateBusiness:
    """Tests for POST /businesses endpoint."""

    def test_create_business_with_valid_data(self, client: TestClient):
        """
        Verify that a business can be created with valid data.
        
        Expected behavior:
        - Returns 201 Created status
        - Response includes the created business with an ID
        - All provided fields are correctly stored
        """
        response = client.post(
            "/businesses",
            json={
                "name": "Junk Removal Pro",
                "timezone": "America/New_York",
                "default_appointment_duration": 90,
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["id"] is not None
        assert data["name"] == "Junk Removal Pro"
        assert data["timezone"] == "America/New_York"
        assert data["default_appointment_duration"] == 90

    def test_create_business_with_minimal_data(self, client: TestClient):
        """
        Verify that a business can be created with only required fields.
        
        Expected behavior:
        - Returns 201 Created status
        - Default values are applied for optional fields
        - timezone defaults to "America/New_York"
        - default_appointment_duration defaults to 60
        """
        response = client.post(
            "/businesses",
            json={"name": "Minimal Business"},
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Business"
        assert data["timezone"] == "America/New_York"  # Default
        assert data["default_appointment_duration"] == 60  # Default

    def test_create_business_without_name_fails(self, client: TestClient):
        """
        Verify that creating a business without a name fails validation.
        
        Expected behavior:
        - Returns 422 Unprocessable Entity status
        - Error message indicates name is required
        """
        response = client.post(
            "/businesses",
            json={"timezone": "America/Los_Angeles"},
        )
        
        assert response.status_code == 422

    def test_create_business_with_empty_name_fails(self, client: TestClient):
        """
        Verify that creating a business with an empty name fails validation.
        
        Expected behavior:
        - Returns 422 Unprocessable Entity status
        - Name must have at least 1 character
        """
        response = client.post(
            "/businesses",
            json={"name": ""},
        )
        
        assert response.status_code == 422

    def test_create_business_with_invalid_duration_fails(self, client: TestClient):
        """
        Verify that appointment duration must be within valid range (15-480 minutes).
        
        Expected behavior:
        - Returns 422 for duration < 15 minutes
        - Returns 422 for duration > 480 minutes
        """
        # Too short
        response = client.post(
            "/businesses",
            json={"name": "Test", "default_appointment_duration": 5},
        )
        assert response.status_code == 422
        
        # Too long
        response = client.post(
            "/businesses",
            json={"name": "Test", "default_appointment_duration": 600},
        )
        assert response.status_code == 422


class TestGetBusiness:
    """Tests for GET /businesses/{id} endpoint."""

    def test_get_existing_business(self, client: TestClient, sample_business):
        """
        Verify that an existing business can be retrieved by ID.
        
        Expected behavior:
        - Returns 200 OK status
        - Response contains all business fields
        - created_at and updated_at timestamps are present
        """
        response = client.get(f"/businesses/{sample_business.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_business.id
        assert data["name"] == sample_business.name
        assert data["timezone"] == sample_business.timezone
        assert "created_at" in data
        assert "updated_at" in data

    def test_get_nonexistent_business_returns_404(self, client: TestClient):
        """
        Verify that requesting a non-existent business returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        - Error message indicates business was not found
        """
        response = client.get("/businesses/99999")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestUpdateBusiness:
    """Tests for PATCH /businesses/{id} endpoint."""

    def test_update_business_name(self, client: TestClient, sample_business):
        """
        Verify that a business name can be updated.
        
        Expected behavior:
        - Returns 200 OK status
        - Name is updated in the response
        - Other fields remain unchanged
        """
        response = client.patch(
            f"/businesses/{sample_business.id}",
            json={"name": "Updated Name"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["timezone"] == sample_business.timezone  # Unchanged

    def test_update_business_timezone(self, client: TestClient, sample_business):
        """
        Verify that a business timezone can be updated.
        
        Expected behavior:
        - Returns 200 OK status
        - Timezone is updated in the response
        """
        response = client.patch(
            f"/businesses/{sample_business.id}",
            json={"timezone": "America/Los_Angeles"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "America/Los_Angeles"

    def test_update_business_multiple_fields(self, client: TestClient, sample_business):
        """
        Verify that multiple business fields can be updated at once.
        
        Expected behavior:
        - Returns 200 OK status
        - All provided fields are updated
        """
        response = client.patch(
            f"/businesses/{sample_business.id}",
            json={
                "name": "New Name",
                "timezone": "Europe/London",
                "default_appointment_duration": 45,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["timezone"] == "Europe/London"
        assert data["default_appointment_duration"] == 45

    def test_update_nonexistent_business_returns_404(self, client: TestClient):
        """
        Verify that updating a non-existent business returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.patch(
            "/businesses/99999",
            json={"name": "New Name"},
        )
        
        assert response.status_code == 404


class TestDeleteBusiness:
    """Tests for DELETE /businesses/{id} endpoint."""

    def test_delete_existing_business(self, client: TestClient, sample_business):
        """
        Verify that an existing business can be deleted.
        
        Expected behavior:
        - Returns 204 No Content status
        - Business is no longer retrievable after deletion
        """
        response = client.delete(f"/businesses/{sample_business.id}")
        
        assert response.status_code == 204
        
        # Verify it's gone
        get_response = client.get(f"/businesses/{sample_business.id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_business_returns_404(self, client: TestClient):
        """
        Verify that deleting a non-existent business returns 404.
        
        Expected behavior:
        - Returns 404 Not Found status
        """
        response = client.delete("/businesses/99999")
        
        assert response.status_code == 404


class TestListBusinesses:
    """Tests for GET /businesses endpoint."""

    def test_list_businesses_empty(self, client: TestClient):
        """
        Verify that listing businesses returns empty list when none exist.
        
        Expected behavior:
        - Returns 200 OK status
        - Response is an empty list
        """
        response = client.get("/businesses")
        
        assert response.status_code == 200
        assert response.json() == []

    def test_list_businesses_with_data(self, client: TestClient):
        """
        Verify that listing businesses returns all created businesses.
        
        Expected behavior:
        - Returns 200 OK status
        - Response contains all created businesses
        """
        # Create multiple businesses
        client.post("/businesses", json={"name": "Business 1"})
        client.post("/businesses", json={"name": "Business 2"})
        client.post("/businesses", json={"name": "Business 3"})
        
        response = client.get("/businesses")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        names = [b["name"] for b in data]
        assert "Business 1" in names
        assert "Business 2" in names
        assert "Business 3" in names

    def test_list_businesses_with_pagination(self, client: TestClient):
        """
        Verify that listing businesses supports skip and limit parameters.
        
        Expected behavior:
        - skip parameter skips the first N businesses
        - limit parameter limits the number of results
        """
        # Create 5 businesses
        for i in range(5):
            client.post("/businesses", json={"name": f"Business {i}"})
        
        # Get first 2
        response = client.get("/businesses?limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2
        
        # Skip first 2, get next 2
        response = client.get("/businesses?skip=2&limit=2")
        assert response.status_code == 200
        assert len(response.json()) == 2

