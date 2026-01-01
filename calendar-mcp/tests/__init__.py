"""
Test suite for Calendar MCP Server.

This package contains pytest tests for all FastAPI endpoints.

Test modules:
- test_businesses.py: Business CRUD operations
- test_availability.py: Availability rules and slot queries  
- test_appointments.py: Booking, cancellation, and rescheduling
- test_health.py: Health check and root endpoints

Run tests with:
    pytest                          # Run all tests
    pytest -v                       # Verbose output
    pytest --cov=app               # With coverage
    pytest tests/test_businesses.py # Single file
"""
