# Frontend Architecture

RedForge V3 Sprint 4 delivers a polished, dark-first web app on top of the
existing Sprint 1–3 backend. **No backend logic was changed** — the frontend
consumes the APIs exactly as implemented. The experience reduces the user's job
to three actions: **pick a model, pick a profile, start** — everything else is
planned and executed server-side.

Design language: neutral grey surfaces with a single red accent, restrained
motion, high contrast — the register of Linear / Vercel / Grafana / GitHub
Actions.

> **Tooling note.** The brief specified Figma MCP + Fable for design and
> `@tanstack/react-query`, `@tanstack/react-table`, and `sonner` as libraries.
> This environment has **no network access**, so those packages could not be
> installed and Figma/Fable were unavailable. To honor the intent without them,
> the app ships small, dependency-free, drop-in equivalents:
> `src/lib/query.tsx` (a react-query-shaped cache + polling layer),
> `src/lib/toast.tsx` (a sonner-shaped toaster), and native typed tables. Their
> public APIs mirror the originals so a future swap is mechanical.

---

## Stack

| Concern | Choice |
|--------|--------|
| Framework | React 18 + TypeScript + Vite |
| Styling | TailwindCSS (custom red/grey theme), `@tailwindcss/typography` |
| Primitives | Radix UI (already present), Lucide icons |
| Charts | Recharts |
| Data/state | In-house `useQuery`/`useMutation` (react-query-shaped) |
| Toasts | In-house `toast` (sonner-shaped) |
| Routing | react-router-dom v6 |

---

## Directory layout

```
src/
├── main.tsx                 # providers: QueryProvider, ToasterProvider, Router
├── App.tsx                  # routes (all pages lazy-loaded)
├── index.css                # theme tokens, fonts, scrollbars, component classes
├── api/
│   ├── client.ts            # single axios instance + error normalization
│   ├── endpoints.ts         # ALL API calls, typed (the only axios callers)
│   └── types.ts             # response types mirroring the backend
├── hooks/
│   ├── queries.ts           # typed data hooks (useModels, useProfiles, …)
│   └── useSessionStream.ts  # live session polling + derived metrics
├── lib/
│   ├── query.tsx            # react-query-shaped cache/polling layer
│   ├── toast.tsx            # sonner-shaped toaster
│   ├── cn.ts, format.ts, export.ts
├── components/
│   ├── AppShell.tsx         # sidebar + content shell
│   ├── ui/index.tsx         # design-system primitives
│   └── shared.tsx           # ScoreDonut, badges, KeyValue
└── pages/                   # one file per route (lazy-loaded)
```

---

## Component hierarchy

```
main.tsx
└─ QueryProvider
   └─ ToasterProvider
      └─ BrowserRouter
         └─ App
            └─ AppShell (sidebar nav + system status)
               └─ <Suspense> lazy route
                  ├─ DashboardPage
                  ├─ NewEvaluationPage
                  ├─ LiveListPage / LiveSessionPage
                  ├─ ReportsPage / ReportDetailPage
                  ├─ LeaderboardPage
                  └─ HistoryPage
```

Pages compose design-system primitives from `components/ui` (Card, Button,
Badge, Progress, Stat, Skeleton, EmptyState, ErrorState, PageHeader,
StatusBadge) and shared visuals from `components/shared` (ScoreDonut, RiskBadge,
SeverityBadge, VerdictBadge). **No page calls axios or contains API logic** —
all data flows through hooks.

---

## Routing

| Path | Page | Purpose |
|------|------|---------|
| `/` | Dashboard | Control center: models, recent evals, latest score/findings, resources |
| `/new` | New Evaluation | Model → profile → live runtime/resource preview → start |
| `/live` | Live list | Active + recent sessions |
| `/live/:id` | Live session | **Flagship** streaming page |
| `/reports` | Reports | Completed reports grid |
| `/reports/:id` | Report detail | Full report + JSON/Markdown/PDF export |
| `/leaderboard` | Leaderboard | Sortable model ranking |
| `/history` | History | Filterable timeline of all sessions |

Every page is `React.lazy`-loaded (code-split — see the per-page chunks in the
build output), wrapped in a `<Suspense>` boundary with a spinner fallback.
Unknown routes redirect to `/`.

---

## State management

A tiny cache layer (`lib/query.tsx`) provides the react-query ergonomics the app
relies on:

- **Shared cache** keyed by a serialized `queryKey`, with subscriber
  notification so multiple components share one request.
- **Request de-duplication** — concurrent identical queries reuse one in-flight
  promise.
- **`staleTime`** to avoid redundant refetches.
- **`refetchInterval`** for polling (the basis of the "live" feel).
- **`queryClient.invalidate(prefix)`** after mutations.

Hooks in `hooks/queries.ts` wrap endpoints (`useModels`, `useProfiles`,
`usePlanPreview`, `useSessions`, `useSession`, `useReport`, `useFindings`,
`useLeaderboard`, `useHistory`) plus mutations (`useStartEvaluation`,
`useSessionControl`). Components never see endpoints directly.

---

## API layer

`api/endpoints.ts` is the single source of API calls. One axios instance
(`api/client.ts`, `baseURL: /api`, proxied to `:8000` by Vite) normalizes errors
into `{ error, detail }`; `errorMessage(err)` extracts a display string. Types in
`api/types.ts` mirror the backend responses (sessions, events, profiles, engine
preview, plan, findings, report, leaderboard, history).

Endpoints consumed (all pre-existing, unchanged):
`GET /models`, `GET /evaluation-profiles`, `POST /evaluation-plan`,
`POST /evaluate`, `GET /plans|findings|report/{id}`, `GET /sessions`,
`GET /sessions/{id}`, `GET /sessions/{id}/events?after_id=N`,
`POST /sessions/{id}/pause|resume|cancel`, `GET /leaderboard`,
`GET /history/{model}`.

---

## Theme system

Tokens live in `tailwind.config.ts` (semantic color names — `base`, `surface`,
`elevated`, `overlay`, `border`, `content.*`, `red.*`, `pass`/`fail`/
`uncertain`) and `index.css` (font imports, custom scrollbars, `.rf-card`,
`.rf-focus`, keyframes). Dark mode is the only mode (dark-first). Motion is
subtle by design: `fade-in` for new feed rows, a `pulse-dot` for live
indicators, and smooth width/stroke transitions on progress and the score gauge
— no flashy animation.

Helpers in `lib/format.ts` centralize presentation (durations, bytes, relative
time, and `scoreColor`/`verdictColor`/`riskColor` mappings) so color semantics
are consistent everywhere.

---

## Live streaming (WebSocket integration point)

The backend event store exposes an **incremental cursor**
(`GET /sessions/{id}/events?after_id=N`) designed for a future WebSocket feed.
WebSockets are **not yet available server-side**, so `hooks/useSessionStream.ts`
polls that cursor every ~1.2s — the same incremental data, delivered live — and:

1. accumulates events (advancing the `after_id` cursor, so each poll only
   fetches what's new),
2. derives `LiveMetrics` (progress, current model/category, avg latency, a
   running "live score", ETA, and the pipeline stage), and
3. stops automatically once the session reaches a terminal status.

The hook is deliberately transport-agnostic: **swapping polling for a real
`WebSocket` is a change inside this one file** — every consumer (the Live page's
stage timeline, progress cards, event feed, current-finding panel) stays the
same. That is the intended WebSocket integration seam.

---

## Performance

- **Code splitting** — every page is lazy-loaded; Recharts only loads with the
  report page.
- **Windowed event feed** — the live feed renders only the most recent ~150
  events (newest first), so a long-running session never grows the DOM
  unbounded.
- **Cache + de-dupe** — shared query cache avoids redundant fetches; reports are
  cached with a long `staleTime`.
- **Cursor polling** — the live stream fetches only new events each tick, not the
  whole history.

---

## Accessibility & states

- Keyboard-navigable controls with a visible focus ring (`.rf-focus`).
- ARIA live region on the toaster; semantic headings and labels.
- Every data surface has explicit **loading** (skeletons/spinners), **error**
  (with retry), and **empty** states.
- Responsive layout (sidebar + fluid grid) down to small viewports.
