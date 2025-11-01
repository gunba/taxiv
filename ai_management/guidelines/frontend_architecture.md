# Frontend Architecture (React/TypeScript)

## Stack
*   Framework: React (latest stable version)
*   Language: TypeScript (Strict mode enabled)
*   Styling: [Specify your styling solution, e.g., Tailwind CSS, MUI, CSS Modules]
*   State Management: [Specify your state management, e.g., Redux Toolkit, Zustand, React Query]
*   Routing: [Specify your router, e.g., React Router v6]

## Directory Structure (Example)
** Todo:

## Patterns
*   **Components:** Prefer functional components with hooks. Keep components pure.
*   **Data Fetching:** Use [e.g., React Query] for server state synchronization. Abstract API calls into the `/services` directory.
*   **TypeScript:** All code must be strongly typed. Avoid `any`. Define interfaces for all data structures and API responses.
*   **Error Boundaries:** Implement Error Boundaries to catch rendering errors gracefully.

## UX/UI
*   Ensure accessibility (a11y) standards are met.
*   Provide immediate feedback for user interactions (loading states, error messages).