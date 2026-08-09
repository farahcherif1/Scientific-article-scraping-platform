# Frontend — Yonnov'IA

React 18 + Vite + TypeScript + Tailwind CSS. See the [repo root
README](../README.md) and [`docs/`](../docs/) for the project overview,
architecture, and setup instructions covering both the frontend and
backend together — this file only covers frontend-specific commands.

## Scripts

```bash
npm install       # install dependencies
npm run dev       # start the Vite dev server (http://localhost:5173)
npm run build     # type-check (tsc -b) then production build to dist/
npm run preview   # serve the production build locally
npm run lint      # eslint .
npm test          # vitest run (one-shot)
npm run test:watch  # vitest, watch mode
```

`VITE_API_BASE_URL` (see `.env.example`) points the frontend at the
backend API — defaults to `http://localhost:8000`, matching both the
Docker Compose and manual install paths in [`docs/install.md`](../docs/install.md).

## Structure

- `src/pages/` — one component per route (see `src/App.tsx` for the
  router).
- `src/api/` — fetch wrappers, one module per backend resource.
- `src/components/` — shared UI.
- `src/lib/` — pure, framework-free helpers.

Full breakdown in [`docs/architecture.md`](../docs/architecture.md).
