# General Best Practices

* Prefer tab indentation to minimize file size and token overhead.
* Keep every function narrowly scoped to a single responsibility.
* Choose precise, intention-revealing names for identifiers, modules and files.
* Treat the codebase as production-facing: threat-model input, sanitize outputs, and avoid leaking secrets.
* Only add error handling for realistic fault modes; noise around improbable scenarios dilutes real signal.
