# Project: Weather-Aware Truck Routing System

## Objective

Build a production-quality React + Django geospatial application that recommends the safest truck route based on weather conditions, load weight, and travel time. This is a production-quality geospatial application, not just a React dashboard with a map.

The assessment PDF (`fs-assessment-spotter.pdf`, kept local and not committed) is the source of truth, and its rules are transcribed below. Do not omit or reinterpret requirements.

The risk engine is the heart of the assignment. A visually impressive application that calculates weather risk incorrectly can lose a substantial portion of the marks.

## GitHub repository guidelines

Repository: `git@github.com:ahmadrashad1/Weather-Aware-Truck-Routing.git`

### Commits

- Every commit is authored and committed as `ahmadrashad1` <ahmadrashadmojeeb@gmail.com>. Never change the git identity or commit as anyone else.
- Claude is not a contributor. This overrides any default attribution: never add `Co-Authored-By: Claude`, a "Generated with Claude Code" line, or any other Claude or Anthropic attribution to commit messages, PR titles, PR descriptions, or code comments. Pass this rule on to any subagent that commits.
- Every commit must be signed and show as **Verified** on GitHub (SSH signing is configured in the global git config). Never use `--no-gpg-sign` or `-c commit.gpgsign=false`. If signing fails, stop and tell the user.
- Only commit or push when the plan being executed or the user calls for it.
- Use Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `chore:`, `refactor:`).

### Branches and pull requests

- After the initial bootstrap commit, `main` changes only through pull requests from short-lived branches (`feat/...`, `fix/...`, `ci/...`).
- Merge only when CI is green.
- Never force-push `main`.
- Never commit secrets. API keys come from environment variables, and `.env.example` documents them with empty values.
- Do not commit `fs-assessment-spotter.pdf`, `.agents/`, `.claude/skills/`, or `skills-lock.json`.

### CI/CD

- The project will use CI/CD pipelines to build, test, and ship the software.
- **Before production, only continuous integration is in scope.** Do not add deployment or release workflows until the user asks for them.
- CI runs on every pull request and every push to `main`, using GitHub Actions: lint, type-check, unit tests, build, end-to-end tests, Docker image build (no push), and the commit-policy check.
- CI never calls live third-party APIs and needs no secrets. Live smoke tests run only on manual dispatch.

## Technology

- Frontend: React, TypeScript, Tailwind CSS, shadcn/ui.
- Mapping: MapLibre GL JS with react-map-gl.
- Backend: Python, Django, Django REST Framework.
- Testing: pytest, Vitest, Playwright.
- Use Context7 to retrieve current library documentation when it is available.

MapLibre is a library the application uses, not an MCP server.

## Assessment rules (from the PDF)

The user enters origin and destination, departure date/time, and load weight.

The app must:

- Generate 3 route options using a routing API.
- Sample weather every 10 / 25 / 50 miles, using the truck's estimated arrival time at each checkpoint.
- Calculate weather risk using the risk and load rules below.
- Recommend the best route, balancing weather risk and travel time.
- Show all routes, checkpoints, risk levels, ETAs, and route summaries on a map.
- Show a weather heatmap along the trip corridor with a 0–48 hour forecast slider.

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind | <25 mph | 25–34 | 35–44 | 45–54 | ≥55 mph |
| Rain | <0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow | <0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

Load rules:

- ≥55 mph → No Travel for any load
- 45–54 mph + >30,000 lb → No Travel
- 35–44 mph + >40,000 lb → Severe

Route recommendation, as a strict lexicographic order and never a weighted score:

1. Fewest Severe miles
2. Fewest High miles
3. Lowest average risk
4. Shortest travel time

Deliverables: GitHub repository, hosted application, 5–10 minute Loom walkthrough.

Evaluation priority:

- 40% Routes, weather, risk and recommendation logic.
- 40% UI, map, heatmap smoothness and performance.
- 15% Code quality.
- 5% Documentation and walkthrough.

Prioritize correctness, clarity, reliability and performance over unnecessary features.

## Resolved ambiguities

The PDF leaves these open. They are project decisions, and the README must document them.

- **Threshold boundaries:** a value on a shared endpoint takes the higher risk class. Bands are lower-inclusive, except that Rain 1.00 and Snow 3.0 stay Severe because No Travel is strictly greater. Wind bands are continuous: `[25,35)`, `[35,45)`, `[45,55)`, `≥55`.
- **Final checkpoint risk:** the worst of wind (after load rules), rain and snow, classified independently. Load rules only apply to wind.
- **Load limits are strict:** exactly 30,000 lb and exactly 40,000 lb do not trigger the load rules.
- **Load weight means cargo weight.** The risk rules compare it directly. The routing request adds an assumed tare weight, because a truck's gross weight is what road restrictions apply to.
- **No Travel in ranking:** the PDF's order never mentions No Travel, so read literally it could recommend a route the rules forbid. Routes with any No Travel miles rank after all others and are never recommended. If every route has them, the API returns no recommendation and says so.
- **Risk miles:** each checkpoint represents the distance from the midpoint with its previous checkpoint to the midpoint with its next one. A route's represented miles sum to its total length.
- **Average risk:** distance-weighted over checkpoints with known weather, on the scale Low=0, Moderate=1, High=2, Severe=3, No Travel=4.
- **Missing weather:** the checkpoint is `unknown`, never estimated. Unknown miles are reported. A route with any ranks after complete routes, most complete first, and a route with no known weather is never recommended.
- **Forecast slider:** hour 0 is the departure time.
- **ETAs exclude rest stops:** no hours-of-service breaks or layovers are modelled.

## Core requirements

1. Accept origin, destination, departure date/time, load weight, and weather sampling interval.
2. Generate three alternative routes using a routing API.
3. Generate weather checkpoints every 10, 25, or 50 miles.
4. Calculate estimated arrival time at every checkpoint.
5. Retrieve weather based on checkpoint coordinates and estimated arrival time.
6. Apply all specified weather and load risk rules.
7. Calculate risk miles and average route risk.
8. Recommend routes using the exact lexicographic priority above.
9. Display all three routes, checkpoints, risk classifications, ETAs and summaries.
10. Implement a weather heatmap with a 0–48-hour forecast slider.

## Engineering rules

- Keep risk calculations in the Django backend. Never duplicate business logic in React.
- Separate routing, weather retrieval, ETA calculation, checkpoint generation, risk classification and route scoring into `backend/routing/services/` and `backend/routing/providers/`.
- Classify wind, rain and snow independently, then apply load rules, then determine the final checkpoint risk.
- ETA-based sampling order: route geometry → checkpoints at the selected interval → cumulative distance → estimated arrival time → weather for that coordinate and time → risk. Never use one time for every checkpoint.
- Use typed API responses and clear error handling.
- Cache weather responses appropriately.
- Handle API failures, missing forecast data and invalid inputs.
- Never fabricate weather or routing results. Do not use mock data in the production workflow. Fixtures live only in test code.
- Document any assumptions where the assessment is ambiguous.
- Heatmap performance: do not re-render the map when the slider changes. Cache the data, update the heatmap layer's paint properties, and avoid unnecessary React re-renders.
- Keep API keys on the server. The browser only talks to the Django API.

## Testing requirements

Write automated tests for:

- Every weather threshold.
- Every load-dependent rule.
- Exact threshold boundaries.
- Checkpoint interval generation.
- Estimated arrival time calculations.
- Route risk aggregation.
- Route recommendation ordering.
- Missing or unavailable weather data.
- API integration failures.

Test the frontend using Playwright, including form submission, route rendering, map interactions, checkpoint details and forecast slider functionality.

## Development workflow

1. Inspect the existing repository before modifying anything.
2. Produce an implementation plan and architecture.
3. Implement the backend risk engine and unit tests first.
4. Implement routing and weather integrations.
5. Implement the frontend and interactive map.
6. Integrate the complete application.
7. Run backend and frontend tests.
8. Run browser-based end-to-end tests.
9. Fix all critical errors before declaring completion.
10. Prepare deployment instructions, README and a Loom demonstration checklist.

The current plan is in `docs/superpowers/plans/`.

Never claim a requirement is complete without verifying it.

## Agent tooling

- Use `frontend-design` for UI work and `vercel-react-best-practices` for React performance.
- Use the Context7 and Playwright MCP servers when they are connected.
- Do not install dozens of unrelated skills. More tools do not automatically mean better implementation.
- This project produces no video. Do not use the `hyperframes` or `motion-graphics` skills for UI animation.
