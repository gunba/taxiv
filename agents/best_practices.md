# General Best Practices

* Prefer tab indentation to minimize file size and token overhead.
* Keep every function narrowly scoped to a single responsibility.
* When naming things (files, functions, variables, etc.), choose simple names that explicitly state the purpose or intent rather than "standard industry terminology".
* Treat the codebase as production-facing: threat-model input, sanitize outputs, and avoid leaking secrets.
* Only add error handling for issues that are likely to actually occur.
