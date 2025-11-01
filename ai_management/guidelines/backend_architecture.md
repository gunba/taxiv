# Backend Architecture (Python)

## Stack
*   Language: Python (Specify version, e.g., 3.10+)
*   Framework: [Specify your framework, e.g., FastAPI, Django, Flask, or None if pure scripts]
*   Data Processing: Pandas, NumPy
*   Environment Management: [e.g., Poetry, Pipenv, venv]

## Directory Structure (Example)

## Patterns
*   **Data Ingestion/Manipulation:**
    *   Prefer vectorized operations in Pandas/NumPy over iterative loops.
    *   Validate data integrity immediately upon ingestion (e.g., using Pydantic or Pandera).
    *   Optimize for memory usage when handling large datasets.
*   **API Design:** Adhere to RESTful principles. Use clear naming conventions and appropriate HTTP status codes.
*   **Type Hinting:** Utilize Python type hints for all function signatures. Use `mypy` for static type checking.