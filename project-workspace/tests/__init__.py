"""
Phase A (Foundation) Test Suite for WSB Analysis Tool

This test suite defines what "done" looks like for Phase A.
All tests are expected to FAIL initially since no implementation exists yet.

Test Organization:
- test_schema.py: Database schema creation and constraints (story-001-001)
- test_seed_config.py: System configuration seeding (story-001-002)
- test_seed_portfolios.py: Portfolio initialization (story-001-003)
- test_connection_manager.py: DB connection management (story-001-004)
- test_schema_validation.py: Schema validation script (story-001-005)
- test_schwab_spike.py: Schwab OAuth integration spike (story-001-006)
- test_wal_concurrency.py: SQLite WAL concurrency spike (story-001-007)
- test_error_handling.py: Shared error handling utilities (story-001-008)
- test_fastapi_app.py: FastAPI application setup (story-007-001)
- test_response_envelope.py: Standard response envelope (story-007-002)
- test_endpoints.py: REST API GET endpoints (story-007-003)
- test_seed_data.py: Test data seeding (story-007-004)

Run all tests:
    cd project-workspace && python -m pytest tests/ -v

Run specific test file:
    cd project-workspace && python -m pytest tests/test_schema.py -v

Skip Schwab API tests (require credentials):
    cd project-workspace && python -m pytest tests/ -v -m "not schwab_api"
"""
