# Frontend Architecture (React/TypeScript)

## Stack

* **Framework:** React 19+
* **Language:** TypeScript (strict mode)
* **Build Tool:** Vite
* **Styling:** Tailwind CSS via CDN injection in `index.html`
* **State:** React Context plus hooks (`useState`, `useEffect`, `useCallback`, `useMemo`)
* **Runtime:** Dockerized Node.js container

## Directory Structure

```
frontend/
├── App.tsx          # Application shell + routing
├── main.tsx         # Entry point
├── index.html       # Vite HTML entry
├── components/      # Reusable UI primitives
│   ├── ActSelector.tsx
│   ├── DetailView.tsx
│   ├── Icons.tsx
│   ├── InteractiveContent.tsx
│   ├── MainContent.tsx
│   ├── SemanticSearchModal.tsx
│   └── SideNav.tsx
├── utils/           # Frontend helpers
│   ├── api.ts       # Backend abstraction layer
│   ├── clipboard.ts # Clipboard helper for exports
│   └── provisionSort.ts
└── types.ts         # Shared TypeScript interfaces

tests/frontend/
├── components/      # Component-focused Vitest suites
│   ├── InteractiveContent.*.test.tsx
│   ├── SemanticSearchModal.test.tsx
│   └── nodeFormatting.test.ts
├── utils/           # Utility/helper tests
│   └── provisionSort.test.ts
├── NavNode.test.tsx # Nav node behavior tests
└── setupTests.ts    # Vitest/RTL setup
```

## Patterns

* **Components:** Favor functional components and hooks; keep them pure and predictable.
* **Data Fetching:**
	* All API calls terminate in `utils/api.ts`.
	* Fetch data on demand from the FastAPI backend rather than preloading.
* `SideNav.tsx` lazily loads child nodes when a parent expands to limit payload size.
* The SideNav copy-to-markdown icon posts the visible subtree to `/api/provisions/markdown_subtree`, which now returns each visible provision's `content_md` plus a definitions section (deduped) so even whole-chapter selections stay single-request.
	* The semantic-search modal's copy actions call `/api/provisions/detail/{id}` with `format=json|markdown` so the UI dogfoods the MCP surface.
	* `MainContent.tsx` sorts streamed provisions via `utils/provisionSort.ts` so the lazy-loaded sequence always matches the SideNav ordering, even if fetches resolve out of order; keep that comparator aligned with backend hierarchy sorting.
* **API Proxy:** `vite.config.ts` proxies `/api` to `http://backend:8000`, eliminating dev-time CORS noise.
* **Media Proxy:** Static ingestion artifacts under `/media/...` are forwarded through the same proxy so diagrams render
  during Vite development sessions.
* **TypeScript:** Maintain strict typing. Avoid `any`. Interfaces in `types.ts` must mirror the backend Pydantic schema.
* **Enumerated indentation:** `InteractiveContent.tsx` applies Tailwind padding heuristics for lines that begin with markers like `(1)`, `(1A)`, `(a)`, `(aa)`, or `(i)`, mapping top-level numerals, nested numerals-with-letters, letters, and roman/double-letter styles (used by acts such as ITAA 1936) to consistent visual indentation levels.

## UX/UI

* **Styling:** Dark theme composed via Tailwind utility classes.
* **Interactivity:** `MainContent.tsx` rewrites markdown renderings at runtime to make definition tokens (e.g., `*term*`)
  interactive using regex detection and event delegation.
* **Lazy Rendering:** Long content is lazily materialized at two levels:
  * **Within a provision:** `InteractiveContent.tsx` chunk-renders oversized `content_md` and shows only an initial subset of markdown chunks plus an explicit “Load more of this provision” button; clicking the button reveals additional chunks without relying on scroll position, so users can either read deeper into long provisions (e.g. ITAA 1936 s 6 or ITAA 1997 s 995) or scroll past them.
  * **Across provisions:** `MainContent.tsx` lazily fetches and appends child provisions based on the `main` scroll container’s position (near-bottom threshold), with per-position gating so that continuous downward scrolling brings in additional provisions without chaining the entire hierarchy at once or requiring an up-then-down bounce.
* **Error Handling:** `App.tsx` and `SideNav.tsx` implement base loading/error states; extend them before adding new UX
  surface area.

## Repo Layout (Frontend Surface)

The frontend container (`frontend` in `docker-compose.yml`) corresponds to the `frontend/` React/Vite app:

* App shell and entrypoints live under `frontend/` (`App.tsx`, `main.tsx`, `index.html`), with Vite/Vitest config and `package.json` at the repo root.
* Reusable UI primitives and feature components live under `frontend/components/`.
* Shared helpers and abstractions live under `frontend/utils/` (e.g., `frontend/utils/api.ts`), with shared interfaces in `frontend/types.ts`.
* Frontend tests are centralized under `tests/frontend/**`, mirroring the frontend structure.

When adding new frontend behavior, place tests under the corresponding path in `tests/frontend/**` (for example, `tests/frontend/components/` for a new component), and keep imports using the `@` alias to point at `frontend/`.
