2025-11-09 - Centralized MCP markdown formatting in the backend, added `format=markdown` support on the provision detail API, and updated the semantic-search modal copy buttons to consume those endpoints.
2025-11-09 - Aligned the semantic-search modal "Copy MCP JSON" button with the MCP provision_detail response by fetching and copying full provision detail payloads.
2025-11-09 - Added ~120-char provision snippets (or 'No content') to unified search responses, wiring them through the MCP server and semantic search modal.
2025-11-09 - Reworded AGENTS.md and all agent guidance docs to tighten tone and clarify mandatory workflows.
2024-11-24 - Restricted the MCP surface to semantic search + provision detail, slimmed search results to headers only, enriched provision detail responses with breadcrumbs/definitions, and updated docs/UI wiring.
2024-11-24 - Fixed GraphAnalyzer root sibling ordering by adding a rolling counter, updated docs, and added a regression test.
2025-11-08 - Bound pgvector parameters via bindparam in `_semantic_neighbors`, documented the fastmcp SSE flow, and validated MCP tools end-to-end.
2025-02-17 - Trimmed WMF/EMF rasterized PNGs to remove blank PDF canvases and documented the behavior.
2025-11-08 - Proxied /media through Vite and made ingestion media hashing deterministic with doc-level cleanup to stop duplicate PNGs.
2025-02-14 - Specified the vector_l2_ops operator class for the embeddings HNSW index and documented the pgvector requirement.
2025-02-14 - Fixed ingestion reruns by deleting baseline/fingerprint rows and embeddings before provision reloads, plus documented the workflow.
2024-12-20 - Renamed the Document ORM attribute to doc_metadata to avoid SQLAlchemy's reserved metadata name and documented the quirk.
2025-11-08 - Documented how to recover from Postgres major-version mismatches and reset the docker volume to unblock local db startup.
2025-11-08 - Added Dockerfile.db and compose wiring so Postgres ships with pgvector preinstalled.
2025-11-08 - Replaced global semantic kNN with pgvector-backed ANN, added lazy relatedness engine/CLI, and hooked ingestion to incremental embeddings with graph-version bumps.
2025-11-08 - Added info-level logging to relatedness indexer to surface ingestion progress during PageRank and fingerprint stages.
2025-11-08 - Added LibreOffice/Ghostscript/font dependencies to Dockerfile.backend and documented rasterization requirements.
2024-06-09 - Installed WMF/EMF rasterization packages in Dockerfile.backend and documented the dependency.
2024-05-07 - Embed definition reference sections in markdown export and expanded tests.
2025-11-08 - Removed canonical reference identifiers from markdown export headings.
2025-02-14 - Restyled side navigation hierarchy with indentation, guide lines, and wrapping titles.
2025-02-14 - Replaced nav export copy buttons with a single clipboard control.
2025-02-14 - Realigned SideNav expand controls and condensed export button to clipboard icon.
2025-11-08 - Centered SideNav rows, increased label size, and removed row guide line.
2025-11-08 - Added sentence-transformers dependency to restore ingestion semantic view.
2025-11-08 - Added configurable ingestion progress helpers and instrumented pipeline stages.
2025-11-08 - Instrumented relatedness indexer workflows with ingestion progress helpers.
2025-02-18 - Allowed interactive definition buttons to wrap like surrounding text.
