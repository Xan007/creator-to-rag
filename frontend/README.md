# CreatorRAG frontend

React 19 + TypeScript SPA for CreatorRAG. It talks to the FastAPI backend in
[`../src/api`](../src/api) and does not duplicate backend or database logic.

## Stack

- React 19 + TypeScript (strict-ish, `tsc -b` in the build)
- Vite 8 (Rolldown) with route-level code splitting
- Tailwind CSS 3 + `@tailwindcss/typography`
- Radix Dialog primitives, `lucide-react` icons
- `@tanstack/react-table` for the content inventory
- `react-i18next` (Spanish/English)
- `react-markdown` + `remark-gfm` (loaded on demand, not in the entry chunk)

## Requirements

- Node.js **20.19+** (or 22.12+); the repo is developed on Node 24
- npm (a `package-lock.json` is committed; use `npm ci`)
- The API running locally (default `http://127.0.0.1:8000`)

## Local setup

From the repository root, start the API:

```bash
uv sync --extra api
uv run crag-api
```

In a second terminal:

```bash
cd frontend
cp .env.example .env    # Windows: copy .env.example .env
npm ci
npm run dev
```

Vite prints `http://localhost:5173`.

### How the browser reaches the API

By default `VITE_API_URL=/api` and Vite proxies `/api/*` to
`http://127.0.0.1:8000/*` (prefix stripped). Requests stay same-origin, so there
is **no CORS and no preflight** during development.

- Change the proxy target with `VITE_API_PROXY_TARGET`.
- To call the API directly (absolute URL), set `VITE_API_URL` to the backend
  origin; the backend must then allow that origin via `CRAG_CORS_ORIGINS`.
- In production, serve the built assets behind the same origin that exposes the
  API under `/api`, or build with an absolute `VITE_API_URL`.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `/api` | Backend base URL or `/api` prefix |
| `VITE_USER_ID` | `default` | Sent as `X-User-Id` (username or UUID) |
| `VITE_API_KEY` | — | Sent as `X-API-Key` when the backend sets `CRAG_API_KEY` |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Dev/preview proxy target (not exposed to the bundle) |
| `CHOKIDAR_USEPOLLING` | `false` | Enable only for Docker/VM/network drives |

Only `VITE_*` values reach the browser; they are public. Never put
`GEMINI_API_KEY`, `PINECONE_API_KEY` or `APIFY_API_KEY` here.

## Commands

```bash
npm run dev        # Vite dev server with HMR + proxy
npm run typecheck  # tsc -b
npm run lint       # oxlint
npm run build      # type-check + production build -> dist/
npm run check      # typecheck + lint + build (what CI runs)
npm run preview    # serve dist/ locally (proxy is configured too)
```

## Performance notes

- `App.tsx` lazy-loads the chat, video player, dashboard, browser and modals.
  The markdown renderer, Radix dialogs and TanStack Table are therefore not part
  of the entry chunk; markdown and Radix only download when a chat, details
  sheet or dialog is actually opened.
- Vendor code is split with Rolldown's `output.codeSplitting` groups (React,
  i18n, Radix, Table). See [`vite.config.ts`](vite.config.ts).
- Job polling is centralized in [`src/hooks/useJobs.ts`](src/hooks/useJobs.ts):
  one request at a time, faster while a job runs, paused in hidden tabs.
- Global search is debounced (300 ms) and in-flight requests are aborted when
  filters change, so stale responses cannot overwrite newer ones.
- The chat composer keeps its draft local to `ChatView`; message bubbles are
  memoized, so typing does not re-parse the whole conversation with markdown.

## Project layout

```text
src/
  components/   layout, chat, modals, ui primitives and tables
  hooks/        chat sessions, job polling, sidebar resizing
  lib/          API client, shared types, i18n, search parser, utils
  locales/      es.json / en.json
```

The API client lives in [`src/lib/api.ts`](src/lib/api.ts); it owns base URL,
identity/API-key headers, timeouts, abort signals and FastAPI error parsing.

## shadcn/ui

The project is configured in [`components.json`](components.json). Add
components with the CLI from `frontend/`:

```bash
npx shadcn@latest add button
```

Generated components belong in `src/components/ui/`; import aliases use `@/`.
