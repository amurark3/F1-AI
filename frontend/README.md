# F1 AI — Web Frontend

The web surface for **F1 AI**, a Next.js 16 / React 19 app styled as a Formula 1
"Race Control" pit-wall workspace. It talks to the FastAPI backend for AI chat,
standings, predictions, live timing, and regulation search.

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

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | Base URL of the FastAPI backend (e.g. `http://localhost:8000`) |

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start the dev server (Turbopack) |
| `npm run build` | Production build |
| `npm start` | Serve the production build |
| `npm run lint` | Run ESLint |

## Routes

Top-level navigation (`app/components/NavShell.tsx`): Workspaces, Race Control,
Consumer, Calendar, Standings, Champions, Predictions, Live.

| Route | Purpose |
|---|---|
| `/` | Redirects to `/race-control` |
| `/race-control` | Operational season control board |
| `/race-control/engineer` | Streaming AI race-engineer chat |
| `/race-control/teams` · `/teams/[team]` | Constructor breakdowns |
| `/race-control/debriefs` | LLM post-race debriefs |
| `/race-control/intel` | Per-team strategic intel |
| `/race-control/predictions` | Race predictions + post-mortems |
| `/race-control/rulebook` | FIA regulation semantic search |
| `/race-control/live` | Live timing + AI commentary |
| `/race-control/champions` · `/champions/[year]` | Historical champions |
| `/calendar` | Season schedule with countdown |
| `/standings` | WDC + WCC tables |
| `/champions` | Champions 1950→present |
| `/predictions` | Race predictions + championship scenarios |
| `/live` | Live timing |
| `/consumer` | Redirects to `/race-control/engineer` |

## Stack

Next.js 16 · React 19 · TypeScript 5 · Tailwind CSS 4 · Recharts · Framer Motion ·
SWR · Vercel AI SDK (`ai` / `@ai-sdk/react`) · lucide-react.
</content>
