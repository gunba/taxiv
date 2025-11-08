# Frontend Architecture (React/TypeScript)

## Stack

* **Framework:** React (v19+)
* **Language:** TypeScript (Strict mode enabled)
* **Build Tool:** Vite
* **Styling:** Tailwind CSS (configured via CDN in `index.html`)
* **State Management:** React Context and Hooks (`useState`, `useEffect`, `useCallback`, `useMemo`).
* **Environment:** Dockerized Node.js environment.

## Directory Structure

```

/ (Project Root)
├── components/      \# Reusable UI components
│   ├── DetailView.tsx
│   ├── Icons.tsx
│   ├── MainContent.tsx
│   └── SideNav.tsx
├── utils/
│   └── api.ts           \# API abstraction layer
├── types.ts             \# Shared TypeScript interfaces
├── App.tsx              \# Main application component and layout
├── index.tsx            \# Entry point
└── vite.config.ts       \# Vite configuration (including proxy setup)

```

## Patterns

* **Components:** Prefer functional components with hooks.
* **Data Fetching:**
    * Data is fetched dynamically from the FastAPI backend.
    * API calls are abstracted in `utils/api.ts`.
    * The application uses a "load-on-demand" strategy for the navigation hierarchy (`SideNav.tsx`). Children are
      fetched only when a parent is expanded.
* **API Proxy:** Vite is configured (`vite.config.ts`) to proxy requests from `/api` to the backend container (
  `http://backend:8000`). This avoids CORS issues in development.
* **Media Proxy:** Static ingestion assets under `/media/...` are also forwarded to the backend so embedded diagrams
  load while running the Vite dev server.
* **TypeScript:** All code must be strongly typed. Avoid `any`. Interfaces in `types.ts` must align with the backend
  Pydantic schemas.

## UX/UI

* **Styling:** Uses a dark theme defined by Tailwind CSS utility classes.
* **Interactivity:**
    * `MainContent.tsx` processes markdown content to make defined terms (e.g., `*term*`) interactive using regex
      replacement and event delegation.
* **Error Handling:** Basic error and loading states are implemented in `App.tsx` and `SideNav.tsx`.
