# Testing Standards

Every change must be testable and ship with the relevant coverage.

## General Principles

* Keep tests isolated and deterministic.
* Follow an explicit Arrange → Act → Assert structure.
* Name tests after the observable behavior under scrutiny.

## Frontend Testing

* **Framework:** Vitest
* **Library:** React Testing Library (RTL)
* **Priorities:**
	1. Validate user interactions and component behavior through RTL. Avoid white-box assertions.
	2. Unit test complex business logic, utility helpers, and custom hooks.
* **Mocking:** Isolate network calls via MSW or targeted `jest.mock` shims.

## Backend Testing

* **Framework:** Pytest
* **Priorities:**
	1. Unit test processors, services, and other data-manipulation modules.
	2. Exercise API endpoints with integration tests where behavior spans layers.
* **Fixtures:** Use Pytest fixtures to manage setup/teardown efficiently.
* **Parametrization:** Prefer `pytest.mark.parametrize` for combinatorial input coverage.
* **Mocking:** Stub external services and heavyweight dependencies to keep the suite fast.
