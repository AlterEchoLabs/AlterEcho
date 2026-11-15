# TerraLuna frontend

Next.js 16 (App Router), React 19, MapLibre GL and three.js via `@react-three/fiber`. The UI is one task-ordered page plus two reading pages:

| Route | Purpose |
|---|---|
| `/` | Atlas: Jezero reference → mission profile → ranked Earth sites → site viewer (Satellite · 3D terrain · Globe) → evidence |
| `/method` | How the index, statuses, gates, profiles and sensitivity work (reads `/api/evidence/model` and `/api/evidence/profiles`) |
| `/sources` | Every dataset, product, date and attribution |

## Layout of the code

```text
app/layout.tsx                  fonts (Newsreader, IBM Plex Sans/Mono), masthead
app/components/atlas/Atlas.tsx  state: profile, selection, URL sync, race-safe comparison loading
app/components/atlas/*.tsx      ResultsList, ReferenceBand, SiteViewer, TerrainView, GlobeView, RecentMap, EvidencePanel, charts
lib/api.ts                      typed API client (URL allowlisting, timeouts, memoised GETs)
lib/evidence.ts                 TypeScript mirror of backend/app/models/evidence.py
lib/hooks.ts                    useKeyed (stale responses never render for the wrong site), WebGL / media hooks
public/textures/                NASA/USGS globe mosaics + textures.manifest.json (attribution, checksums)
e2e/terraluna.spec.ts           Playwright, three viewports, real backend + production build
```

## Run (Git Bash on Windows)

```bash
cp .env.example .env.local      # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm ci
npm run dev                      # http://localhost:3000 (backend must run on :8000)
```

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run build
npx playwright install chromium  # once
npm run test:e2e                 # builds, starts backend :8100 and frontend :3100, 1327x660 / 1680x1000 / 390 px
```

The globe and terrain views need WebGL. Without it they fall back to a flat mosaic or a short explanation. Satellite imagery and evidence do not depend on WebGL.
