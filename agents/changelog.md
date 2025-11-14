2025-11-14 - Extended the semantic-search modal for current-Act and all-Acts scopes, mapped act_ids to human-readable titles, and documented Playwright MCP UI smoke tests for multi-act verification.
2025-11-12 - Captured a multi-act readiness audit (docs/multi-act-readiness.md) covering ITAA-specific coupling across ingestion, backend search, and the frontend act picker gap.
2025-11-12 - Generalized the stack for multi-act datasets: added config/datasets.json, act-aware search/relatedness APIs, frontend act selector, a base ingestion pipeline, and a document ingestion path with `/api/documents/search`.
2025-11-12 - Updated AGENTS/testing guidance to mandate running the relevant test suites (and documenting commands) after every change, referencing the new host-side workflows.
2025-11-12 - Added a host-based test workflow (requirements-dev, npm scripts, run-tests.sh) and documented the steps in README for Vitest + Pytest parity.
2025-02-14 - Documented VPS access credentials, Caddy proxy wiring, ChatGPT MCP connector steps, and day-to-day service management in `agents/deployment.md`.
2025-02-14 - Added deployment/capacity planning notes for Qwen3 embeddings to `agents/backend.md`, covering CPU memory, throughput, and scaling guidance.
2025-02-14 - Swapped the backend container to a multi-worker uvicorn launcher (`scripts/start-backend.sh`), documented the new concurrency env vars, bumped SQLAlchemy pool defaults, and raised Postgres max connections in compose.
2025-02-14 - Documented the FastMCP decoupling (formatter vendored into `mcp_server`) and the VPS deployment procedure, including restoring the Postgres volume and setting up the `.env` with new worker/pool knobs.
2025-02-14 - Added `agents/deployment.md` (remote DB refresh playbook), removed the temporary `Handover.md`, and allowed Vite to serve `raja-block.bnr.la`.
2025-11-09 - Added the `/api/provisions/markdown_subtree` endpoint and rewired SideNav copy-to-markdown to batch visible descendants via a single request.
2025-11-09 - Updated `/api/provisions/markdown_subtree` to emit each visible provision's content plus a deduped definitions section, keeping the MCP markdown formatter unchanged.
2025-11-09 - Enforced deterministic ordering in `MainContent` via `utils/provisionSort.ts` so streamed provisions match the SideNav hierarchy, and documented the constraint in `agents/frontend.md`.
2025-02-14 - Rewired SideNav copy-to-markdown to call the lightweight detail markdown endpoint, added a shared toast provider, and documented the heavyweight export path for future tooling.
2025-02-14 - Documented that markdown export currently iterates every descendant/reference/definition via individual ProvisionDetail queries, explaining slow copy-to-markdown operations on large selections.
2025-11-09 - Documented that ingestion must run via `docker compose exec backend` to reuse container dependencies (pgvector, ImageMagick, LibreOffice, etc.) after diagnosing host-side ModuleNotFound errors.
2025-11-09 - Centralized MCP markdown formatting in the backend, added `format=markdown` support on the provision detail API, and updated the semantic-search modal copy buttons to consume those endpoints.
2025-11-09 - Aligned the semantic-search modal "Copy MCP JSON" button with the MCP provision_detail response by fetching and copying full provision detail payloads.
2025-11-09 - Added ~120-char provision snippets (or 'No content') to unified search responses, wiring them through the MCP server and semantic search modal.
2025-11-09 - Reworded AGENTS.md and all agent guidance docs to tighten tone and clarify mandatory workflows.
2025-11-09 - Investigated semantic search latency after the Qwen3 embedding swap and documented the fingerprint cache warm-up behavior in `agents/backend.md`.
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
2025-11-09 - Clamped ITAA1997 list levels to prevent orphaned Markdown code blocks.
2025-02-14 - Swapped provision embeddings to Qwen/Qwen3-Embedding-0.6B, added the HF backend helper + pgvector resize CLI, and documented the new chunking defaults.
2025-11-09 - Landed the search-performance plan (lexical SQL/indexes, TTL caching, multi-seed PPR, ingestion fingerprint precompute) and suppressed Section 995 from relatedness/search results.
2025-11-10 - Added disjunctive lexical fallback for unified search to retain candidates on mixed-term queries.
2025-02-14 - Streamed oversized provision markdown via IntersectionObserver-driven chunking in `InteractiveContent` and added lazy render regression coverage.
2025-11-11 - Added MCP capabilities endpoint, paginated search, lean provision detail metadata, and batch provision hydration.
2025-11-12 - Fixed MCP import usage and normalized backend detail helpers for lean responses with caching metadata.
2025-02-14 - Added the ITAA1936 ingestion pipeline with DOCX conversion, shared docx phases, and LLM-free parsing stabilizers.
2025-11-13 - Added LibreOffice to the backend image, cached ITAA1936 RTF conversions via manifests, normalized style handling for Section 6 definitions, and documented the ingestion nuances.
