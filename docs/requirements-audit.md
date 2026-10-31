# Requirements audit

Each requirement from the assessment and `CLAUDE.md`, with what proves it. "Live" means it was also checked by hand against the real providers while building the app. Backend paths are under `backend/tests/`, and frontend paths are under `frontend/`.

## User input

| Requirement | Proof |
| --- | --- |
| Origin and destination | `src/features/trip/TripForm.test.tsx`, `e2e/trip.spec.ts`. Live. |
| Departure date and time | `TripForm.test.tsx`, `src/lib/format.test.ts`, `api/test_plan.py`. Live. |
| Load weight | `TripForm.test.tsx`, `api/test_plan.py`. Live. |
| Weather sampling interval | `TripForm.test.tsx`, `services/test_checkpoint_generator.py`, `api/test_plan.py`. Live. |

## Routes, weather, risk and recommendation

| Requirement | Proof |
| --- | --- |
| 3 route options from a routing API | `providers/test_tomtom.py`, `services/test_route_alternatives.py`. Live on four trips, including a one-road trip that returned 2 routes with a warning. |
| Weather every 10, 25 or 50 miles | `services/test_checkpoint_generator.py` |
| Weather at each checkpoint's ETA | `services/test_trip_planner.py::test_each_checkpoint_gets_weather_at_its_own_eta`, `services/test_weather_lookup.py`. Live: sampled values matched by-hand calculations from Open-Meteo's raw data. |
| ETA calculation | `services/test_eta_calculator.py`, including a DST change. Live: ETAs increase along every route. |
| Every wind, rain and snow threshold, and exact boundaries | `services/test_risk_engine.py` |
| Every load rule | `services/test_risk_engine.py`, `services/test_trip_planner.py`, `services/test_heatmap.py` |
| Risk miles and average risk | `services/test_route_scorer.py`. Live: represented miles sum to each route's length. |
| Recommendation order | `services/test_route_scorer.py`, each priority tested against the one below it. Live: a slower route beat a faster one with 10 High miles. |
| No Travel handling | `services/test_route_scorer.py`, `services/test_trip_planner.py`, `e2e/errors.spec.ts` |

## Map and heatmap

| Requirement | Proof |
| --- | --- |
| All routes on a map | `src/features/map/buildGeoJson.test.ts`, `MapPanel.test.tsx`, `e2e/trip.spec.ts` using real rendered pixels. Live. |
| Checkpoints, risk levels and ETAs | `MapPanel.test.tsx`, `e2e/trip.spec.ts` including real canvas clicks. Live. |
| Route summaries | `src/features/trip/RouteList.test.tsx`, `e2e/trip.spec.ts`. Live. |
| Corridor heatmap | `services/test_corridor_grid.py`, `services/test_heatmap.py`, `api/test_heatmap_api.py`. Live. |
| 0–48 hour slider | `src/features/forecast/ForecastSlider.test.tsx`, `HeatmapLayer.test.tsx`, `e2e/heatmap.spec.ts`. Live. |
| Heatmap colours show real risk | `e2e/heatmap.spec.ts::shading colour shows the risk level`, using real rendered pixels |
| Smooth slider | `HeatmapLayer.test.tsx`, `MapPanel.test.tsx`, and `e2e/heatmap.spec.ts`, which checks for no network requests. Measured live on a 283-point trip: 17ms median frame time and no long tasks, with software rendering. |

## Failures and invalid input

| Requirement | Proof |
| --- | --- |
| Missing or unavailable weather | `services/test_weather_lookup.py`, `services/test_trip_planner.py`, `api/test_plan.py`, `e2e/errors.spec.ts` |
| API integration failures | `providers/test_tomtom.py`, `providers/test_open_meteo.py`, `api/test_plan.py`, `e2e/errors.spec.ts`. Live: the per-minute weather limit was hit and waited out. |
| Invalid inputs | `api/test_plan.py`, `api/test_heatmap_api.py`, `TripForm.test.tsx` |
| Redis outage | `test_cache.py`. Live: Redis was stopped during a run. |
| No fabricated results | `services/test_trip_planner.py`, `api/test_plan.py::test_unknown_checkpoint_has_no_invented_values`, `test_settings.py::test_production_code_never_imports_from_tests` |
| API keys kept private | `providers/test_tomtom.py`, `providers/test_open_meteo.py`, `api/test_plan.py`. Live: no key in the server logs. |

## Engineering rules

| Requirement | Proof |
| --- | --- |
| Risk logic only in the backend | `src/lib/no-business-logic.test.ts` |
| Typed API responses | Types generated from `backend/schema.yml`, with CI failing on drift |
| Weather caching | `services/test_weather_lookup.py`. Live: a repeat heatmap fell from 1.5s to 0.2s. |
| Production settings | `test_settings.py`, including Django's deployment check |
| Continuous integration | `.github/workflows/ci.yml`, required on `main` |
| Signed commits, no tool attribution | The `commit-policy` CI job and the `main` branch ruleset |

## Not fully proven

| Item | Status |
| --- | --- |
| Severe and No Travel on live data | Weather was mild during live runs. These are covered by tests and fixtures, and haven't appeared in a live forecast. |
| Smoothness on a real GPU | Measured with software rendering only, which should be the harder case. |
| Hosted application | Not deployed yet. Only continuous integration is in scope before production. |
| Loom walkthrough | Still to record, after review. `docs/loom-checklist.md` is the script. |
| Live smoke workflow on GitHub | Passed locally. It needs a `TOMTOM_API_KEY` repository secret, and hasn't run on GitHub. |
