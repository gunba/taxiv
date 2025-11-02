# Testing Standards

All code must be testable and accompanied by relevant tests.

## General Principles

* Tests should be isolated and independent.
* Use the Arrange-Act-Assert (AAA) structure.
* Use descriptive test names.

## Frontend Testing

* **Framework:** Jest (or Vitest)
* **Library:** React Testing Library (RTL)
* **Priorities:**
    1. Test user interactions and component behavior (RTL). Do not test implementation details.
    2. Unit test complex business logic, utility functions, and custom hooks.
* **Mocking:** Mock external dependencies (API calls) using [e.g., Mock Service Worker (MSW) or jest.mock].

## Backend Testing

* **Framework:** Pytest
* **Priorities:**
    1. Unit tests for data manipulation logic (`processors`) and `services`.
    2. Integration tests for API endpoints (if applicable).
* **Fixtures:** Use Pytest fixtures for setup and teardown.
* **Parametrization:** Use `pytest.mark.parametrize` to test functions with different inputs/outputs.
* **Mocking:** Mock external services and complex dependencies.