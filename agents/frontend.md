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
/
├── components/      # Reusable UI primitives
│   ├── DetailView.tsx
│   ├── Icons.tsx
│   ├── MainContent.tsx
│   └── SideNav.tsx
├── utils/
│   └── api.ts       # Backend abstraction layer
├── types.ts         # Shared TypeScript interfaces
├── App.tsx          # Application shell + routing
├── index.tsx        # Entry point
└── vite.config.ts   # Vite config (proxy, plugins)
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

## UX/UI

* **Styling:** Dark theme composed via Tailwind utility classes.
* **Interactivity:** `MainContent.tsx` rewrites markdown renderings at runtime to make definition tokens (e.g., `*term*`)
  interactive using regex detection and event delegation.
* **Error Handling:** `App.tsx` and `SideNav.tsx` implement base loading/error states; extend them before adding new UX
  surface area.
