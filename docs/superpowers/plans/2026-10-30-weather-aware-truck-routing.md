# Weather-Aware Truck Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a React + Django app that generates 3 truck routes, assesses weather at each checkpoint's ETA, ranks routes by the assessment's lexicographic order, and shows routes, checkpoints and a 0–48 hour corridor heatmap on an interactive map.

**Architecture:** A stateless Django REST API holds all business logic as pure functions in `routing/services/`, with third-party APIs behind typed providers in `routing/providers/`. React renders only what the API returns, using types generated from the OpenAPI schema. The slider changes one MapLibre paint property, so it causes no refetch and no map re-render.

**Tech Stack:** Python 3.13, Django 5.2 LTS, DRF, drf-spectacular, httpx, pytest, respx, ruff, mypy, Redis (production cache), gunicorn, whitenoise; React 19, TypeScript (strict), Vite, Tailwind CSS, shadcn/ui, MapLibre GL JS, react-map-gl, TanStack Query, openapi-typescript, Vitest, Playwright; TomTom (routing, geocoding), Open-Meteo (weather), OpenFreeMap (base map); GitHub Actions, Docker.

**Spec:** `CLAUDE.md` (rules, resolved ambiguities, repository guidelines) and `fs-assessment-spotter.pdf`.

## Global Constraints

- Commits: author `ahmadrashad1`, signed, Verified on GitHub, with no Claude attribution anywhere in commits or PRs. Never pass `--no-gpg-sign`.
- After Task 1, each task lands through a PR from its own branch, and CI must be green before merge.
- CI only until the user asks for production. No deploy or release workflows.
- All risk thresholds and load limits live in `backend/routing/services/risk_engine.py` and nowhere else. React contains no thresholds.
- Sampling intervals are exactly 10, 25, 50 miles. Forecast slider is exactly 0–48 hours (49 frames).
- Units in the API: miles, mph, in/hr, lb, seconds, ISO 8601 with offset.
- Never fabricate weather or routes. Fixtures live only in test directories.
- Provider API keys are read from environment variables and never appear in logs or browser traffic.

## Review Focus

1. **The provider returns fewer than 3 distinct routes** (short or constrained trips, where near-identical alternatives are common). Expect forced via-point alternatives, then fewer routes with an explicit warning, and never a padded duplicate. Test in Task 5.
2. **Every route has No Travel miles.** Expect all routes still shown and ranked, `recommended_route_id: null`, and a clear "no safe route" message. Test in Tasks 4 and 9.
3. **Weather is partly or wholly unavailable.** Partial outage: affected checkpoints are `unknown`, and routes carry a warning and rank after complete routes. Total outage: 503 with a retry message and no routes. Test in Tasks 6 and 7.
4. **Long trips:** a coast-to-coast trip at a 10-mile interval (about 900 checkpoints across 3 routes), or ETAs past the forecast horizon. Expect batching within provider limits, `unknown` beyond the horizon, and no timeout. Test in Tasks 6 and 7.
5. **Time zones:** a departure entered in one zone with a trip crossing midnight or a DST change. Expect ETAs computed in UTC and returned with an offset, with forecast hours matched correctly. Test in Tasks 3 and 6.

---

### Task 1: Repository bootstrap and CI

**Files:**
- Create: `.gitignore`, `.env.example`, `README.md` (stub), `.github/workflows/ci.yml`
- Create: `backend/pyproject.toml`, `backend/manage.py`, `backend/config/{settings,urls,wsgi}.py`, `backend/routing/{__init__,apps}.py`, `backend/tests/test_health.py`
- Create: `frontend/` (Vite React TS scaffold, ESLint, Prettier, Vitest, Tailwind, shadcn/ui init), `frontend/src/App.test.tsx`
- Create: `backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore`
- Commit: `CLAUDE.md`, this plan

**Interfaces:**
- Produces: `GET /api/v1/health` → `{"status": "ok"}`; settings env vars `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `REDIS_URL` (locmem cache when unset), `TOMTOM_API_KEY`, `OPEN_METEO_API_KEY` (optional).

- [ ] **Step 1: Initialize git and ignores**

Run `git init -b main` and `git remote add origin git@github.com:ahmadrashad1/Weather-Aware-Truck-Routing.git`. `.gitignore` must cover `fs-assessment-spotter.pdf`, `.agents/`, `.claude/skills/`, `skills-lock.json`, `.env`, plus Python and Node build output.

Verify: `git check-ignore fs-assessment-spotter.pdf .agents .claude/skills skills-lock.json .env` lists all five.

- [ ] **Step 2: Write failing tests**

```python
def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

`App.test.tsx` asserts the app renders the heading "Weather-Aware Truck Routing".

- [ ] **Step 3: Scaffold both apps until tests pass**

Use `uv` with Python pinned to 3.13 (the machine's default 3.14 is not used) and Node 22. Confirm current Django and Tailwind versions with Context7.

Run: `cd backend && uv run pytest && uv run ruff check . && uv run mypy .`, then `cd frontend && npm test -- --run && npm run lint && npm run typecheck && npm run build`
Expected: all pass.

- [ ] **Step 4: Write `.github/workflows/ci.yml`**

Trigger on `pull_request` and push to `main`, with no secrets. Jobs:
- `backend`: ruff check, ruff format check, mypy, pytest with coverage, and `manage.py spectacular` to detect schema drift (once Task 7 adds it).
- `frontend`: lint, typecheck, Vitest, build.
- `e2e`: Playwright (added in Task 11).
- `docker`: build both images without pushing.
- `commit-policy` (pull requests only): for each commit in the PR, fail if `gh api repos/$REPO/commits/$SHA --jq .commit.verification.verified` is not `true`, if the author login is not `ahmadrashad1`, or if the message matches `(?i)co-authored-by:.*(claude|anthropic)|generated with.*claude`.

- [ ] **Step 5: Make the signed bootstrap commit and verify**

```bash
git add -A && git status   # confirm no PDF, skills or .env staged
git commit -m "chore: bootstrap Django, React and CI"
git log -1 --show-signature
git push -u origin main
gh api repos/ahmadrashad1/Weather-Aware-Truck-Routing/commits/main --jq .commit.verification.verified
```

Expected: `true`. If it is `false`, stop. The signing key or email is not registered as verified on GitHub, and the user must fix that before any more commits.

- [ ] **Step 6: Protect `main`**

Add a ruleset requiring signed commits, a PR, and passing `backend`, `frontend`, `docker`, `commit-policy`. If GitHub refuses because of the repo's plan and visibility, report that to the user. The `commit-policy` job still enforces the rule.

### Task 2: Risk engine

**Files:**
- Create: `backend/routing/domain.py`, `backend/routing/services/risk_engine.py`
- Test: `backend/tests/services/test_risk_engine.py`

**Interfaces:**
- Produces:
  - `class RiskLevel(IntEnum)`: `LOW=0, MODERATE=1, HIGH=2, SEVERE=3, NO_TRAVEL=4`
  - `@dataclass(frozen=True) WeatherSample(wind_mph: float, rain_in_hr: float, snow_in_hr: float)`
  - `@dataclass(frozen=True) RiskAssessment(level: RiskLevel, wind: RiskLevel, rain: RiskLevel, snow: RiskLevel, load_adjusted: bool, drivers: tuple[str, ...])`
  - `classify_wind(mph: float) -> RiskLevel`, `classify_rain(in_hr: float) -> RiskLevel`, `classify_snow(in_hr: float) -> RiskLevel`
  - `apply_load_rules(wind_mph: float, load_lb: float) -> RiskLevel`
  - `assess(sample: WeatherSample, load_lb: float) -> RiskAssessment`

- [ ] **Step 1: Write failing parametrized tests with these exact tables**

```python
@pytest.mark.parametrize("mph,expected", [
    (0, LOW), (24.99, LOW), (25, MODERATE), (34.99, MODERATE), (35, HIGH), (44.99, HIGH),
    (45, SEVERE), (54.99, SEVERE), (55, NO_TRAVEL), (90, NO_TRAVEL)])
def test_wind_bands(mph, expected): assert classify_wind(mph) == expected

@pytest.mark.parametrize("rate,expected", [
    (0, LOW), (0.099, LOW), (0.10, MODERATE), (0.249, MODERATE), (0.25, HIGH), (0.499, HIGH),
    (0.50, SEVERE), (1.00, SEVERE), (1.001, NO_TRAVEL)])
def test_rain_bands(rate, expected): assert classify_rain(rate) == expected

@pytest.mark.parametrize("rate,expected", [
    (0, LOW), (0.49, LOW), (0.5, MODERATE), (0.99, MODERATE), (1.0, HIGH), (1.99, HIGH),
    (2.0, SEVERE), (3.0, SEVERE), (3.01, NO_TRAVEL)])
def test_snow_bands(rate, expected): assert classify_snow(rate) == expected

@pytest.mark.parametrize("mph,load,expected", [
    (35, 40_000, HIGH), (35, 40_001, SEVERE), (44.99, 40_001, SEVERE),
    (45, 30_000, SEVERE), (45, 30_001, NO_TRAVEL), (54.99, 30_001, NO_TRAVEL),
    (55, 0, NO_TRAVEL), (34.99, 80_000, MODERATE), (45, 40_001, NO_TRAVEL)])
def test_load_rules(mph, load, expected): assert apply_load_rules(mph, load) == expected

def test_final_is_worst_condition():
    assert assess(WeatherSample(10, 0.3, 0.6), 1000).level == HIGH
    assert assess(WeatherSample(35, 1.5, 0), 40_001).level == NO_TRAVEL

def test_load_adjustment_is_reported():
    result = assess(WeatherSample(35, 0, 0), 40_001)
    assert result.load_adjusted and result.wind == SEVERE
```

Also test that negative rates and NaN raise `ValueError`.

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/services/test_risk_engine.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Implement `risk_engine.py`**

Keep thresholds as module constants, with a comment citing the boundary convention in `CLAUDE.md`.

- [ ] **Step 4: Run to verify pass**

Expected: PASS. Then run `uv run ruff check . && uv run mypy .`.

- [ ] **Step 5: Commit**

Message: `feat: add weather and load risk engine`

### Task 3: Checkpoints and ETAs

**Files:**
- Create: `backend/routing/services/geometry.py`, `checkpoint_generator.py`, `eta_calculator.py`
- Test: `backend/tests/services/test_checkpoint_generator.py`, `test_eta_calculator.py`

**Interfaces:**
- Consumes: domain module from Task 2.
- Produces:
  - `LatLon = tuple[float, float]`; `haversine_miles(a: LatLon, b: LatLon) -> float`
  - `@dataclass(frozen=True) Checkpoint(mile: float, position: LatLon, represented_miles: float, start_mile: float, end_mile: float)`
  - `generate_checkpoints(geometry: Sequence[LatLon], total_miles: float, interval_miles: int) -> list[Checkpoint]`
  - `@dataclass(frozen=True) TravelProfile(points: tuple[tuple[float, float], ...])`, a list of `(mile, elapsed_seconds)`, strictly increasing, from `(0, 0)` to `(total_miles, total_seconds)`
  - `eta_at(mile: float, departure: datetime, profile: TravelProfile) -> datetime`

- [ ] **Step 1: Write failing tests**

```python
def test_120_mile_route_at_50():
    cps = generate_checkpoints(straight_line(120), 120, 50)
    assert [round(c.mile, 2) for c in cps] == [0, 50, 100, 120]
    assert [round(c.represented_miles, 2) for c in cps] == [25, 50, 35, 10]

@pytest.mark.parametrize("interval", [10, 25, 50])
def test_represented_miles_sum_to_length(interval):
    cps = generate_checkpoints(curved_line(), 333.3, interval)
    assert sum(c.represented_miles for c in cps) == pytest.approx(333.3)

def test_route_shorter_than_interval_has_endpoints_only():
    assert [c.mile for c in generate_checkpoints(straight_line(8), 8, 50)] == [0, 8]

def test_interval_outside_allowed_values_rejected():
    with pytest.raises(ValueError): generate_checkpoints(straight_line(50), 50, 30)

def test_position_lies_on_geometry():
    # a checkpoint at mile 50 of a line with a bend is on the second leg, within 0.01 mile

def test_eta_uses_profile_not_average_speed():
    profile = TravelProfile(((0, 0), (50, 3600), (100, 10800)))
    dep = datetime(2026, 11, 1, 12, tzinfo=UTC)
    assert eta_at(50, dep, profile) == dep + timedelta(hours=1)
    assert eta_at(75, dep, profile) == dep + timedelta(hours=2)

def test_eta_preserves_instant_across_dst():
    # departure 2026-11-01T00:30-04:00 (America/New_York), +3h is the correct UTC instant
```

Geometry length rarely equals the provider's reported length, so scale cumulative geometry distance to `total_miles`.

- [ ] **Step 2: Run to verify failure, implement, run to verify pass**

Run: `uv run pytest tests/services -v`
Expected: FAIL, then PASS.

- [ ] **Step 3: Commit**

Message: `feat: add checkpoint generation and ETA calculation`

### Task 4: Route aggregation and ranking

**Files:**
- Create: `backend/routing/services/route_scorer.py`
- Test: `backend/tests/services/test_route_scorer.py`

**Interfaces:**
- Consumes: `Checkpoint`, `RiskLevel`, `RiskAssessment`.
- Produces:
  - `@dataclass(frozen=True) AssessedCheckpoint(checkpoint: Checkpoint, eta: datetime, sample: WeatherSample | None, assessment: RiskAssessment | None)`
  - `@dataclass(frozen=True) RouteScore(severe_miles, high_miles, no_travel_miles, moderate_miles, low_miles, unknown_miles: float, average_risk: float | None, duration_seconds: int)`
  - `score_route(checkpoints: Sequence[AssessedCheckpoint], duration_seconds: int) -> RouteScore`
  - `rank_key(score: RouteScore) -> tuple`
  - `rank_routes(scores: Mapping[str, RouteScore]) -> RankingResult`, where `RankingResult(ordered_ids: list[str], recommended_id: str | None, no_safe_route: bool)`

`rank_key` is:

```python
(score.no_travel_miles > 0, score.unknown_miles > 0, round(score.no_travel_miles, 2),
 round(score.severe_miles, 2), round(score.high_miles, 2),
 round(score.average_risk, 4) if score.average_risk is not None else inf, score.duration_seconds)
```

Rounding stops floating-point noise from deciding a higher-priority tie.

- [ ] **Step 1: Write failing tests**

```python
def test_fewer_severe_beats_faster(): ...      # A: 0 severe, 10h; B: 5 severe, 2h → A
def test_high_miles_break_severe_tie(): ...
def test_average_risk_breaks_high_tie(): ...
def test_duration_only_breaks_full_tie(): ...
def test_float_noise_does_not_override_priority(): ...  # A: severe 10.000001, shorter; B: severe 10.0, longer → tie on severe, so A wins on duration
def test_no_travel_route_never_recommended(): ...       # A: 1 no-travel, 0 severe; B: 50 severe → B
def test_all_no_travel_returns_no_recommendation():
    result = rank_routes(all_blocked)
    assert result.recommended_id is None and result.no_safe_route and len(result.ordered_ids) == 3
def test_unknown_ranks_after_complete(): ...
def test_aggregates_distance_weighted_average():
    # 25 mi Low(0), 50 mi High(2), 25 mi Severe(3) → average_risk == 1.75
def test_all_unknown_average_is_none(): ...
```

- [ ] **Step 2: Run to verify failure, implement, run to verify pass**

Run: `uv run pytest tests/services/test_route_scorer.py -v`
Expected: FAIL, then PASS.

- [ ] **Step 3: Commit**

Message: `feat: add route scoring and lexicographic ranking`

### Task 5: Routing and geocoding provider

**Files:**
- Create: `backend/routing/providers/{base,errors,tomtom}.py`, `backend/routing/services/route_alternatives.py`
- Test: `backend/tests/providers/test_tomtom.py`, `backend/tests/services/test_route_alternatives.py`, `backend/tests/fixtures/tomtom/*.json`

**Interfaces:**
- Consumes: `TravelProfile`, `LatLon`.
- Produces:
  - `@dataclass(frozen=True) ProviderRoute(geometry: tuple[LatLon, ...], total_miles: float, duration_seconds: int, profile: TravelProfile)`
  - `class RoutingProvider(Protocol)`: `routes(origin: LatLon, destination: LatLon, departure: datetime, load_lb: float, via: LatLon | None = None, max_alternatives: int = 2) -> list[ProviderRoute]`
  - `class GeocodingProvider(Protocol)`: `search(query: str) -> list[Place]`, with `Place(label: str, position: LatLon)`
  - Errors: `ProviderUnavailable`, `ProviderRateLimited`, `NoRouteFound`
  - `get_three_routes(provider, origin, destination, departure, load_lb) -> AlternativesResult`, with `AlternativesResult(routes: list[ProviderRoute], warnings: list[str])`

- [ ] **Step 1: Check the TomTom response with a live call**

This needs `TOMTOM_API_KEY` from the user. Call `calculateRoute` with `travelMode=truck`, `maxAlternatives=2`, `vehicleWeight` (kg), `vehicleCommercial=true`, `departAt`, `instructionsType=coded` on a real long-haul pair (Dallas to Denver). Save the scrubbed response to `tests/fixtures/tomtom/`.

Decide from the actual response how to build `TravelProfile`:
- Use guidance instruction offsets and travel times if present (the published spec has no response schema, so this is unconfirmed).
- Otherwise use a two-point profile, which assumes constant average speed, and record that limitation in the README.

Also confirm whether long routes hit the documented compute limit of about 30 seconds.

- [ ] **Step 2: Write failing tests**

```python
def test_parses_fixture_into_routes(): ...      # 3 routes, miles converted from metres
def test_cargo_plus_tare_sent_as_kg(): ...      # load 40,000 lb + TARE_LB 33,000 → vehicleWeight=33112
def test_429_raises_rate_limited(): ...
def test_5xx_and_timeout_raise_unavailable(): ...
def test_no_route_response_raises_no_route(): ...
def test_api_key_absent_from_logs_and_errors(caplog): ...

def test_three_returned_needs_no_via(): ...
def test_near_duplicates_are_dropped(): ...     # >90% geometry overlap counts as the same route
def test_via_points_requested_when_short(): ...  # 1 route → perpendicular offset vias at the midpoint, 15% of length each side
def test_returns_fewer_with_warning_when_exhausted():
    result = get_three_routes(provider_with_one_road, ...)
    assert len(result.routes) == 1 and result.warnings
```

- [ ] **Step 3: Run to verify failure, implement, run to verify pass**

Use `httpx` with a 30-second timeout and two retries on 5xx only. Set the `httpx` logger to WARNING because TomTom keys travel in the query string. Use `respx` in tests.

Run: `uv run pytest tests/providers tests/services/test_route_alternatives.py -v`
Expected: FAIL, then PASS.

- [ ] **Step 4: Commit**

Message: `feat: add TomTom routing, geocoding and route alternatives`

### Task 6: Weather provider and cache

**Files:**
- Create: `backend/routing/providers/open_meteo.py`, `backend/routing/services/weather_lookup.py`
- Test: `backend/tests/providers/test_open_meteo.py`, `backend/tests/services/test_weather_lookup.py`, `backend/tests/fixtures/open_meteo/*.json`

**Interfaces:**
- Consumes: `WeatherSample`, provider errors.
- Produces:
  - `@dataclass(frozen=True) HourlyForecast(times_utc: tuple[datetime, ...], wind_mph: tuple[float | None, ...], rain_in_hr: tuple[float | None, ...], snow_in_hr: tuple[float | None, ...])`
  - `class WeatherProvider(Protocol)`: `hourly(cells: Sequence[LatLon]) -> dict[LatLon, HourlyForecast]`
  - `snap_to_cell(position: LatLon) -> LatLon` (0.05°)
  - `sample_at(forecast: HourlyForecast, at: datetime) -> WeatherSample | None`
  - `class WeatherLookup`: `forecasts(positions: Sequence[LatLon]) -> dict[LatLon, HourlyForecast | None]`

Request `hourly=wind_speed_10m,rain,showers,snowfall` with `wind_speed_unit=mph`, `timezone=GMT`, `forecast_days=16`, and comma-separated coordinates in batches of 100. Keep the default mm and cm units and convert in our code. The docs don't say whether `precipitation_unit=inch` also changes `snowfall`, so this avoids relying on it. Rain is `(rain + showers) / 25.4`, and never `precipitation`, which includes snow. Snow is `snowfall / 2.54`. Use `customer-api.open-meteo.com` with `apikey` when `OPEN_METEO_API_KEY` is set.

Timing rules from the Open-Meteo docs: rain, showers and snowfall are preceding-hour sums, so the value stamped at the next whole hour covers the ETA. Wind is instantaneous, so interpolate linearly between the two surrounding hours.

- [ ] **Step 1: Capture a live fixture**

Save a two-location response to `tests/fixtures/open_meteo/`. Record how it's billed if the response reveals it, because the docs don't say how multi-location calls count against the 10,000-per-day limit.

- [ ] **Step 2: Write failing tests**

```python
def test_rain_sums_rain_and_showers_and_excludes_snow(): ...
def test_units_convert_to_inches(): ...  # 25.4 mm → 1.0, 2.54 cm → 1.0
def test_precip_uses_hour_covering_eta():
    # ETA 14:20 reads the 15:00 value; ETA exactly 14:00 reads the 14:00 value
def test_wind_interpolates(): ...        # 14:30 between 20 and 30 → 25
def test_eta_past_horizon_returns_none(): ...
def test_null_values_return_none(): ...
def test_eta_with_offset_matches_utc_hour(): ...
def test_batches_100_cells_per_request(): ...
def test_cache_hit_makes_no_request(): ...
def test_cache_entries_expire_after_one_hour(): ...
def test_failed_batch_marks_only_its_cells_none(): ...
def test_total_outage_raises_unavailable(): ...
def test_429_raises_rate_limited(): ...
```

- [ ] **Step 3: Run to verify failure, implement, run to verify pass**

Run: `uv run pytest tests/providers/test_open_meteo.py tests/services/test_weather_lookup.py -v`
Expected: FAIL, then PASS.

- [ ] **Step 4: Commit**

Message: `feat: add Open-Meteo weather provider with caching`

### Task 7: Trip planning API

**Files:**
- Create: `backend/routing/services/trip_planner.py`, `backend/routing/api/{serializers,views,urls,errors}.py`, `backend/schema.yml`
- Modify: `backend/config/urls.py`, `backend/config/settings.py`, `.github/workflows/ci.yml`
- Test: `backend/tests/api/test_plan.py`, `backend/tests/services/test_trip_planner.py`

**Interfaces:**
- Consumes: everything from Tasks 2–6.
- Produces:
  - `plan_trip(request: TripRequest, routing: RoutingProvider, weather: WeatherLookup) -> TripPlan`
  - `GET /api/v1/geocode?q=` → `{"results": [{"label", "lat", "lon"}]}`
  - `POST /api/v1/trips/plan`, request: `{origin: {label, lat, lon}, destination: {...}, departure_at, load_lb, interval_miles}`
  - Response:
    ```
    {recommended_route_id, no_safe_route, warnings[], routes[{id, rank, rationale,
      summary{distance_miles, duration_seconds, arrival_at, severe_miles, high_miles, moderate_miles,
              low_miles, no_travel_miles, unknown_miles, average_risk},
      geometry (GeoJSON LineString),
      segments[{risk, from_mile, to_mile, coordinates}],
      checkpoints[{id, mile, lat, lon, eta, represented_miles,
                   weather{wind_mph, rain_in_hr, snow_in_hr}|null,
                   risk, wind_risk, rain_risk, snow_risk, load_adjusted, drivers[]}]}]}
    ```
    `risk` is `low|moderate|high|severe|no_travel|unknown`.
  - Error body: `{"code", "message", "fields"?}`, with `code` from `validation_error` (400), `no_route` (422), `rate_limited` (429), `provider_unavailable` (503).

- [ ] **Step 1: Write failing tests**

```python
def test_each_checkpoint_gets_weather_at_its_own_eta():
    # fake weather varies by hour; assert the planner requests by position and samples at each ETA
def test_order_is_eta_then_weather_then_risk(): ...
def test_recommendation_matches_ranking(): ...
def test_segments_cover_route_and_match_checkpoint_risk(): ...
def test_coast_to_coast_at_10_miles_batches_requests(): ...  # ~900 checkpoints, deduped cells, 100 per request

@pytest.mark.parametrize("field,value", [
    ("interval_miles", 30), ("load_lb", -1), ("load_lb", 80_001),
    ("departure_at", "2020-01-01T00:00:00Z"), ("departure_at", "<now + 15 days>"),
    ("departure_at", "2026-11-01T10:00:00")])  # naive datetime rejected
def test_invalid_input_returns_400(api, field, value): ...
def test_same_origin_and_destination_returns_400(api): ...
def test_no_route_returns_422(api): ...
def test_routing_outage_returns_503(api): ...
def test_total_weather_outage_returns_503_with_no_routes(api): ...
def test_partial_weather_outage_returns_200_with_warning(api): ...
def test_response_contains_no_api_key(api): ...
def test_schema_is_current(): ...  # generated schema equals schema.yml
```

Limits: `0 ≤ load_lb ≤ 80,000`; `departure_at` from 15 minutes ago to 14 days ahead, with an offset required. Add DRF anonymous throttling of 30 plans per hour per IP to protect provider quotas.

- [ ] **Step 2: Run to verify failure, implement, run to verify pass**

Run: `uv run pytest -v`
Expected: FAIL, then PASS.

- [ ] **Step 3: Check against live providers**

With real keys, run `manage.py runserver` and POST Dallas to Denver, 25-mile interval, 45,000 lb. Confirm 3 routes (or an explicit warning), ETAs that increase along each route, and represented miles that sum to the route length. Compare one checkpoint's wind by hand against Open-Meteo's own response.

- [ ] **Step 4: Add the schema drift step to CI and commit**

Message: `feat: add trip planning and geocoding API`

### Task 8: Corridor heatmap API

**Files:**
- Create: `backend/routing/services/corridor_grid.py`, `backend/routing/services/heatmap.py`
- Modify: `backend/routing/api/{serializers,views,urls}.py`, `backend/schema.yml`
- Test: `backend/tests/services/test_corridor_grid.py`, `test_heatmap.py`, `backend/tests/api/test_heatmap_api.py`

**Interfaces:**
- Consumes: `WeatherLookup`, `sample_at`, `assess`, `snap_to_cell`.
- Produces:
  - `corridor_points(routes: Sequence[Sequence[LatLon]], half_width_miles: float = 25, max_points: int = 300) -> list[LatLon]`
  - `build_heatmap(points: Sequence[LatLon], departure: datetime, load_lb: float, weather: WeatherLookup) -> Heatmap`
  - `POST /api/v1/trips/heatmap`, request: `{routes: [<encoded polyline>], departure_at, load_lb}`
  - Response: `{departure_at, hours: 49, points: [[lon, lat]], risk: [[int|null × 49] per point]}`

The stateless request means no plan has to be stored, so it works across workers.

- [ ] **Step 1: Write failing tests**

```python
def test_points_stay_within_corridor(): ...
def test_point_count_never_exceeds_cap_on_long_routes(): ...
def test_short_route_still_gets_a_usable_grid(): ...  # 20-mile route → at least 9 points
def test_points_dedupe_across_overlapping_routes(): ...
def test_returns_49_frames_per_point(): ...
def test_frame_h_samples_departure_plus_h():
    # fake forecast with wind by hour; frame 12 equals the level at departure + 12h
def test_load_rules_apply(): ...       # 35 mph → 2 at 40,000 lb, 3 at 40,001 lb
def test_missing_hour_is_null_not_zero(): ...
def test_outage_returns_503(api): ...
```

- [ ] **Step 2: Run to verify failure, implement, run to verify pass**

Run: `uv run pytest tests/services/test_corridor_grid.py tests/services/test_heatmap.py tests/api/test_heatmap_api.py -v`
Expected: FAIL, then PASS.

- [ ] **Step 3: Commit**

Message: `feat: add corridor heatmap API with 49 hourly frames`

### Task 9: Trip form and route summaries

**Files:**
- Create: `frontend/src/api/{schema.d.ts,client.ts,queries.ts}`, `frontend/src/features/trip/{TripForm,PlaceInput,RouteList,RouteCard,CheckpointDetails,Alerts}.tsx`, `frontend/src/lib/format.ts`, `frontend/src/test/fixtures/plan.ts`
- Modify: `frontend/src/App.tsx`, `frontend/package.json`
- Test: `*.test.tsx` beside each component

**Interfaces:**
- Consumes: `schema.yml` from Tasks 7 and 8 (`npm run gen:api`, checked for drift in CI).
- Produces:
  - `usePlanTrip()`, `useGeocode(query)`, `useHeatmap(plan, request)`
  - `ApiError { code, message, fields }`
  - `RISK_DISPLAY: Record<RiskCode, { label, color }>`, which holds presentation only and no thresholds
  - App state: `selectedRouteId`, `selectedCheckpointId`

Invoke the `frontend-design` skill before building UI, and `vercel-react-best-practices` for components. The layout is a dense operations dashboard: full-bleed map, left panel with form and ranked routes, bottom slider. Risk always pairs color with a text label.

- [ ] **Step 1: Write failing tests**

- `TripForm`: submits `{origin, destination, departure_at (ISO with offset), load_lb, interval_miles}`; offers exactly 10, 25, 50; requires places chosen from suggestions; shows field errors from `ApiError.fields`.
- `RouteCard`: shows rank, Recommended badge, severe, high and unknown miles, average risk, duration, distance and arrival time from the API, unchanged.
- `RouteList`: keeps API order and never re-sorts.
- `Alerts`: `no_safe_route` shows "No safe route" and no Recommended badge; `warnings[]` render; 503 shows a retry action; 422 explains no route was found.
- Static check: a Vitest test fails if `frontend/src` contains a numeric comparison with `wind`, `rain` or `snow`.

- [ ] **Step 2: Run to verify failure, implement, run to verify pass**

Run: `cd frontend && npm test -- --run && npm run typecheck`
Expected: FAIL, then PASS.

- [ ] **Step 3: Commit**

Message: `feat: add trip form and ranked route summaries`

### Task 10: Map of routes and checkpoints

**Files:**
- Create: `frontend/src/features/map/{MapPanel,RouteLayers,CheckpointLayer,CheckpointPopup,Legend,buildGeoJson}.tsx`
- Modify: `frontend/src/App.tsx`
- Test: `buildGeoJson.test.ts`, `RouteLayers.test.tsx`

**Interfaces:**
- Consumes: `TripPlan` response, `selectedRouteId`, `selectedCheckpointId`.
- Produces:
  - `MapPanel` (uses `react-map-gl/maplibre`, exposes the map through `useMap`)
  - `routesToSegments(plan) -> FeatureCollection`, `checkpointsToPoints(plan) -> FeatureCollection`

Use one GeoJSON source per data type and data-driven paint expressions, not one React component per checkpoint, so thousands of points stay fast. Base map: OpenFreeMap Positron.

- [ ] **Step 1: Write failing tests**

- `routesToSegments` emits one feature per API segment, carrying `route_id` and `risk`.
- `checkpointsToPoints` emits one feature per checkpoint.
- Selecting a route changes only its opacity and line width, with no `setData` call.
- A new plan fits the map bounds to all routes.
- Clicking a checkpoint opens a popup with mile, ETA, wind, rain, snow, each condition's risk, the final risk and the load-adjusted note.
- An unknown checkpoint shows "Weather unavailable" rather than zeros.

- [ ] **Step 2: Run to verify failure, implement, run to verify pass**

Run: `npm test -- --run && npm run typecheck`
Expected: FAIL, then PASS.

- [ ] **Step 3: Check in a browser**

Run the app with live keys and use Playwright MCP. Confirm all 3 routes draw in risk colors, popups match the API response, and the console has no errors. Take a screenshot.

- [ ] **Step 4: Commit**

Message: `feat: render risk-colored routes and checkpoints on the map`

### Task 11: Heatmap, forecast slider and end-to-end tests

**Files:**
- Create: `frontend/src/features/map/{HeatmapLayer,heatmapExpression}.ts(x)`, `frontend/src/features/forecast/{ForecastSlider,forecastStore}.ts(x)`, `frontend/playwright.config.ts`, `frontend/e2e/{trip,heatmap,errors}.spec.ts`, `frontend/e2e/fixtures/*.ts`, `frontend/e2e/live.spec.ts`, `.github/workflows/live-smoke.yml`
- Modify: `.github/workflows/ci.yml`, `frontend/src/App.tsx`
- Test: `heatmapExpression.test.ts`, `HeatmapLayer.test.tsx`, `ForecastSlider.test.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/trips/heatmap`, the map from Task 10.
- Produces:
  - `heatmapToGeoJson(data) -> FeatureCollection`, with feature properties `h0`…`h48`
  - `heatmapWeight(hour: number) -> ExpressionSpecification`, equal to `['/', ['coalesce', ['get', 'h' + hour], 0], 4]`
  - `forecastStore`, an external store of the current hour read through `useSyncExternalStore`, so only the slider label subscribes

The heatmap source is set once per plan. A slider change only calls `map.setPaintProperty('corridor-heat', 'heatmap-weight', heatmapWeight(hour))`, coalesced to one call per animation frame.

- [ ] **Step 1: Write failing unit tests**

```ts
test('heatmapWeight reads the selected hour', () => {
  expect(heatmapWeight(12)).toEqual(['/', ['coalesce', ['get', 'h12'], 0], 4]);
});
test('slider change calls setPaintProperty and never setData', ...);
test('slider change does not re-render MapPanel', ...);   // render counter stays constant
test('slider covers 0 to 48 and labels hour with clock time from departure', ...);
test('null hour is excluded and the coverage note shows', ...);
```

- [ ] **Step 2: Run to verify failure, implement, run to verify pass**

Run: `npm test -- --run`
Expected: FAIL, then PASS.

- [ ] **Step 3: Write Playwright specs and run them**

Use `page.route` for `/api/v1/*`, with fixtures typed against `schema.d.ts`. Fixtures live only under `e2e/`.
- `trip.spec.ts`: fill the form and submit; 3 routes appear with one Recommended; clicking a card selects the route; clicking a map checkpoint opens details with its ETA.
- `heatmap.spec.ts`: moving the slider from 0 to 48 makes no network requests; the hour label updates; the heatmap paint weight references `h48`; 49 rapid slider steps finish with no console errors.
- `errors.spec.ts`: 503, 422, `no_safe_route`, partial-weather warning.
- Also run the main flow at a 390 px mobile width.

Run: `npx playwright test`
Expected: all pass.

- [ ] **Step 4: Add the `e2e` job to CI and the manual live smoke workflow**

`live-smoke.yml` runs on `workflow_dispatch` only, against real providers, using repository secrets. `live.spec.ts` skips when no keys are present.

- [ ] **Step 5: Check smoothness on a long trip**

With live keys, plan a long route and record a Chrome performance trace while dragging the slider. Target: no long tasks over 50 ms. If the target is missed, reduce the point cap in `corridor_points` before changing the architecture. Report the measured result.

- [ ] **Step 6: Commit**

Message: `feat: add corridor heatmap, forecast slider and E2E tests`

### Task 12: Production readiness and documentation

**Files:**
- Modify: `README.md`, `backend/Dockerfile`, `frontend/Dockerfile`, `backend/config/settings.py`
- Create: `docker-compose.yml`, `docs/loom-checklist.md`, `backend/tests/test_settings.py`

**Interfaces:**
- Produces: `docker compose up` runs the full stack, with Redis, from `.env`.

- [ ] **Step 1: Write failing settings tests**

With `DJANGO_DEBUG=false`: startup fails without `DJANGO_SECRET_KEY`, `TOMTOM_API_KEY` or `REDIS_URL`; secure cookies and HSTS are on; `manage.py check --deploy` reports no warnings. The test fails if any test-fixture path is importable from `routing/`.

- [ ] **Step 2: Implement, run to verify pass, then run the whole stack**

Run: `docker compose up --build`, then plan a live trip at `http://localhost:8080`.
Expected: routes, checkpoints and heatmap all load.

- [ ] **Step 3: Write the README and Loom checklist**

README: overview, architecture diagram, setup, env vars, API reference link, test commands, CI description, every item from "Resolved ambiguities" in `CLAUDE.md`, provider limits (below), and deployment instructions. Checklist: a 5–10 minute script covering the recommendation logic, a boundary example, ETA sampling, the heatmap, and tests.

- [ ] **Step 4: Run a requirements audit**

Walk through each PDF requirement and each `CLAUDE.md` core requirement, and record the test or live check that proves it. Any gap reopens its task.

- [ ] **Step 5: Commit**

Message: `docs: add README, deployment guide and Loom checklist`

---

### Task 13: Deployment on Lightsail

Added after Task 12. **Files:** `deploy/`, `.github/workflows/deploy.yml`, `docs/deployment.md`. Test: `backend/tests/test_deploy_update.py`. See `docs/deployment.md` for the design and `docs/decisions.md` for the reasoning. This task supersedes the "CI only" constraint above.

## Open items for the user

- **`TOMTOM_API_KEY`** is needed before Task 5 Step 1. TomTom's store page lists a free commercial-friendly tier with no card, but sources disagree on the current quota.
- **Open-Meteo's free tier is non-commercial** (10,000 calls per day). That suits an assessment. Commercial production use needs a paid key, which `OPEN_METEO_API_KEY` supports.
- **Hosting is out of this plan's scope** because only CI is wanted before production, but the PDF requires a hosted application. A deployment task and CD pipeline need to be added once you're ready.
- **Signing on GitHub** is unverified until Task 1 Step 5. The local config is correct, but "Verified" also needs the SSH key registered as a signing key on GitHub.
