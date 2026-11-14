# F1 AI — Web Frontend

The web surface for **F1 AI**, a Next.js 16 / React 19 app styled as a Formula 1
"Race Control" pit-wall workspace. It talks to the FastAPI backend for AI chat,
the race-weekend Command Center, standings, predictions, telemetry, live timing,
and regulation search.

> This is one part of the monorepo. See the [root README](../README.md) for the
> full architecture, backend setup, and API reference.

## Getting Started

Point the app at a running backend and start the dev server:

```bash
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) — the root route redirects to
`/race-control`.

### Environment

| Variable              | Description                                                                            |
| --------------------- | -------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | Base URL of the FastAPI backend (e.g. `http://localhost:8000`)                         |
| `API_URL`             | Optional — backend origin for server renders only; falls back to `NEXT_PUBLIC_API_URL` |

The backend only accepts browser requests from the origins in its
`ALLOWED_ORIGINS` (default `http://localhost:3000`). Running the dev server on
another port needs that origin added there, or every fetch is blocked.

## Scripts

| Command         | Description                      |
| --------------- | -------------------------------- |
| `npm run dev`   | Start the dev server (Turbopack) |
| `npm run build` | Production build                 |
| `npm start`     | Serve the production build       |
| `npm run lint`  | Run ESLint                       |

## Routes

One top bar on every screen (`app/ui/shell/`, lists in `navConfig.ts`) links
seven sections; Champions, Debriefs and Rulebook sit under "More". Below
1280 px the links move into a full-screen menu.

| Route                                                        | Purpose                                                                                         |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| `/race-control`                                              | Command Center: the race weekend — circuit map, session weather, title stakes, podium, strategy |
| `/race-control/engineer`                                     | Streaming AI race-engineer chat                                                                 |
| `/race-control/grand-prix`                                   | Grand Prix Hub (`?round=&tab=&view=`), including predictions                                    |
| `/race-control/telemetry`                                    | Telemetry Lab: speed map, head-to-head, tyre degradation                                        |
| `/race-control/teams`                                        | Championship standings                                                                          |
| `/race-control/constructors/[team]`                          | Teams & Drivers: line-up, wins, PU usage                                                        |
| `/race-control/drivers/[driver]`                             | Driver season: every result, car's PU                                                           |
| `/race-control/power-units`                                  | Power-unit usage and grid penalties                                                             |
| `/race-control/champions` · `/race-control/champions/[year]` | Historical champions                                                                            |
| `/race-control/debriefs`                                     | Post-race debriefs                                                                              |
| `/race-control/rulebook`                                     | FIA regulation semantic search                                                                  |

Older routes redirect: `/` and `/calendar` → `/race-control`; `/standings` →
`/race-control/teams`; `/champions` → `/race-control/champions`; `/predictions`
and `/race-control/predictions` → `/race-control/grand-prix`; `/consumer` →
`/race-control/engineer`; `/race-control/intel` → `/race-control/constructors`;
`/live` and `/race-control/live` → `/race-control`.

### Command Center code

`app/race-control/CommandCenterView.tsx` fetches the five overview segments
(`shell`, `strategy`, `predictions`, `weather`, `circuit`) in parallel, so each
panel renders as its own data arrives. The race-weekend panels live in
`app/race-control/weekend/`: the hero and circuit map, the session forecast and
its animated weather glyphs, the title stakes, podium and circuit history. Their
keyframes are in `app/globals.css`. Every animation runs behind `motion-safe:`;
the lapping marker on the circuit map is SMIL, so it is left out under reduced
motion and added only after hydration.

## Stack

Next.js 16 · React 19 · TypeScript 5 · Tailwind CSS 4 · Recharts · Framer Motion ·
SWR · react-markdown · lucide-react · Sentry.
</content>
