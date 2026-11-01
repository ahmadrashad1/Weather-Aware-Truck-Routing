# Decisions made during the build

Choices the assessment and plan left open, recorded as they were made, with their reasoning and what each costs if it turns out wrong. Later entries can supersede earlier ones. The heatmap's Low and missing shading is the main example: the final review overturned the Task 11 decision.

## Before starting

- T1 implementer commits locally and does NOT push or create the ruleset; the controller pushes (Step 5 verification) and does Step 6 only after task review passes — review must gate an outward push to main — cost if wrong: a slightly longer path to first CI run.
- T1 review BASE is the empty tree 4b825dc642cb6eb9a060e54bf8d69288fbee4904 — repo has no earlier commit — cost if wrong: none.
- T1 health view lives in config/urls.py — plan lists no views file for T1 and T7 adds routing/api — cost if wrong: a small move in T7.
- T8 request takes `routes` as arrays of [lon, lat] coordinates, not encoded polylines — T7 returns GeoJSON and React should not need an encoder — cost if wrong: larger request bodies. Carry into T8 dispatch.
- T12 fixture check means "no module under routing/ imports from tests" — the plan text is vague — cost if wrong: a weaker guard. Carry into T12 dispatch.
- T1 ruleset has no bypass actors and 0 required approvals — a sole developer cannot approve their own PR, and no bypass keeps the signed/PR rule absolute — cost if wrong: a stuck main needs the ruleset edited in repo settings.
- T1 merge methods are squash and merge only — GitHub's rebase merge produces unsigned commits, which required_signatures rejects — cost if wrong: none.

## Task 4

- A route with no known weather (average_risk None) is never recommended, and no_safe_route stays true only when every route has No Travel miles — recommending a route with no data would be fabricating safety; the plan did not cover this — cost if wrong: one condition in _can_recommend.

## Task 5

- Cap truck speed with vehicleMaxSpeed=105 km/h (about 65 mph) — live Dallas-Denver averaged about 75 mph uncapped, which samples checkpoint weather too early; the plan did not specify a cap — cost if wrong: ETAs a few percent off, one constant to change.
- Place search uses /search/2/search with idxSet=Geo,Str,PAD,Addr instead of /geocode — live "Dall" returned "Dall Lane" before Dallas on /geocode; the plan said geocoding but not the endpoint — cost if wrong: one URL.
- Place search is US-only (countrySet=US) — rules are in miles, mph and pounds, and unrestricted "Dall" returned Italy and India — cost if wrong: non-US trips can't be searched, one constant to change.
- Routes are duplicates only when each overlaps the other by more than 90% — one-directional overlap would discard a real detour depending on order — cost if wrong: an occasional similar route shown.
- A failure while forcing detours keeps the routes already found, with a warning; a failure on the first request propagates — real routes beat an error — cost if wrong: fewer routes during an outage.

## Task 6

- On Open-Meteo's per-minute 429, WeatherLookup waits 61s once and continues; hourly and daily limits do not wait — giving up left later routes unknown and ranked them lower because of request order, not weather (live: 245 of 883 checkpoints) — cost if wrong: one request can take about 75s on a cold cache.
- Gunicorn uses gthread with 8 threads and a 150s timeout, ahead of Task 12 — the default 30s sync worker would kill a request waiting out the limit — cost if wrong: one Dockerfile line; hosting proxies with shorter timeouts must be checked at deployment.
- Extracted the retry logic into routing/providers/http.py and moved TomTom onto it, beyond the plan's file list — it would otherwise be duplicated verbatim — cost if wrong: none; TomTom's tests still pass.
- Local cache MAX_ENTRIES raised to 10,000 in settings — Django's default of 300 is less than one long trip's cells — cost if wrong: more memory in development only.

## Task 7

- Route segments and geometry are simplified with Douglas-Peucker at 0.0005 degrees (about 180 feet), while checkpoints use the full geometry — a long route has nearly 40,000 points; live New York to Los Angeles dropped to about 2,300 per route and 129 KB gzipped — cost if wrong: slightly coarser lines at street zoom, one constant.
- Each route gets a `rationale` naming the deciding criterion, explained against the route below for rank 1 and the route above for the rest — the plan named the field but not its content — cost if wrong: wording only.
- Added GZip middleware, not in the plan — the long-trip response is 543 KB uncompressed — cost if wrong: none.
- Geocoding is throttled at 120 requests/minute per IP, not in the plan — type-ahead spends the shared TomTom quota — cost if wrong: one setting; Task 9 must debounce.
- "nan" and "inf" strings are rejected, and departure must carry a UTC offset — both would otherwise pass validation and cause a 500 or a guessed time zone — cost if wrong: none.

## Task 8

- Corridor uses rows offset from each route (5, then 3, then 1 by budget) rather than a regular grid — a regular grid thinned to 300 points on a long trip leaves stretches of route with no point in range; rows keep every stretch covered — cost if wrong: a less even heatmap pattern, contained in corridor_grid.py.
- Heatmap requests are throttled at 30/hour per IP like plans — each spends up to 300 cells of the shared Open-Meteo quota — cost if wrong: one setting.

## Task 9

- Load weight is required with no default or placeholder value — a pre-filled weight could silently change a safety result — cost if wrong: one extra field to fill in.
- Place search waits 250ms after typing and needs 2 characters, and results aren't kept once nothing shows them — type-ahead spends the shared TomTom quota, and TomTom's terms (clause 11.4) allow client caching only with cache headers, which search responses lack — cost if wrong: more search calls when someone retypes the same text.
- ETAs show in the browser's time zone with its abbreviation — simplest correct display, and departure is entered in the same zone — cost if wrong: a dispatcher in another zone reads local-to-them times, labelled as such.
- Added Vite's dev proxy to the backend and moved Recharts out as decided earlier — needed to run locally — cost if wrong: none.
- UseHeatmap keys on a small per-plan id rather than the plan object — hashing about 500 KB of JSON on every render would hurt slider smoothness — cost if wrong: none; covered by tests.
- Raised Vitest testTimeout to 30s and Testing Library's async timeout to 10s — interaction tests timed out under CPU load (22 failures across 30 loaded runs, 0 after) — cost if wrong: a truly hung test takes longer to fail.

## Task 10

- MapLibre's worker URL is set explicitly through the bundler — MapLibre 6 looks beside its own script, so the worker was missing in both dev and the production build and no routes drew — cost if wrong: none; verified in a real browser on dev, production build and the Docker image.
- Nginx serves .mjs as text/javascript and CI asserts it on the built image, beyond the plan's file list — nginx served octet-stream, which browsers refuse for module workers, so the hosted map would not draw — cost if wrong: none; proven failing then passing against the image.
- The map loads in its own lazy chunk behind an error boundary — it is most of the bundle and needs WebGL, and the route list must survive without it — cost if wrong: a brief "Loading the map" message.
- On phones the map stays pinned above the lists rather than moving below the form — a selection must be visible straight away — cost if wrong: less screen for the lists, one CSS class.
- Clicking a checkpoint also selects its route, and clicking an open row closes it — keeps map and list in step, and the row reports aria-expanded — cost if wrong: small interaction changes.
- Added route labels on the map, and clicks on route lines select them, beyond the plan's list — three green lines are otherwise impossible to tell apart — cost if wrong: small and removable.

## Task 11

- The heatmap is a blurred circle layer coloured directly by risk level, replacing the plan's MapLibre heatmap layer and heatmapWeight — a heatmap layer colours by summed density, so No Travel rendered as pale yellow (real pixel test: 338 dark pixels against a required 5,000+) and clusters of Moderate would look severe — cost if wrong: a slightly less fluid look; colours are now exact, one component to swap.
- The slider sits below the map on phones and floats on wide screens, with extra fit padding — it covered route labels on a phone, which tests caught — cost if wrong: less map height on phones.
- On phones a selected checkpoint moves low in the map — the zoom control covered the popup's close button — cost if wrong: small map movement on selection.
- Low and missing hours are both unshaded, with missing hours named in the slider's note — the plan treats null as no heat; shading Low would hide the map — cost if wrong: Low and missing look alike on the map, though the note says which points are missing.
- Browser tests use a blank base map style and fail on any other outside request or console error — CI must not call third parties, and the worker bug only ever showed in the console — cost if wrong: base map problems are only caught by the manual live smoke test.
- Heatmap checks compare real rendered pixels rather than exposing the map to tests — keeps test-only code out of production — cost if wrong: none so far; 90 repeated runs had no flakes.

## Task 12

- The T12 fixture check is an AST scan that no module under routing/ imports from tests — the pre-flight ruling — cost if wrong: a weaker guard.
- Production also refuses to start without ALLOWED_HOSTS, beyond the plan's list — the old localhost default meant every real request would fail with a 400 — cost if wrong: one more required setting.
- Fixed the two deferred items here: ResilientRedisCache treats a Redis outage as an empty cache, and NUM_PROXIES makes throttling see real client IPs — both would break a real deployment — cost if wrong: during an outage requests are slower and spend more quota (live: 22s plan against 8s).
- Nginx now proxies /api, compresses assets and caches hashed files, using an image template so it starts without the backend, beyond the plan's list — the Compose stack needs one origin, and the map bundle was going out uncompressed (1.13 MB, now 363 KB) — cost if wrong: small; covered by the CI docker job.
- The CI docker job now starts the full stack with Compose and checks it, replacing the image-only builds — it proves the pieces work together — cost if wrong: a little more CI time.
- Added CSRF and clickjacking middleware to satisfy Django's deployment check, and silenced only security.W021 (HSTS preload) — preload is a permanent decision for the domain's owner — cost if wrong: the owner opts in later.
- Added docs/requirements-audit.md for the plan's Step 4 audit, listing what remains unproven — the audit should outlive this session — cost if wrong: none.

## Final review

- Unknown miles now rank before Severe and High among partial routes, and no minimum coverage is required to recommend — a partial route's unknown miles can hide anything, and the warning says the ranking may reflect missing data — cost if wrong: a route with slightly more missing data can lose to one with known Severe miles.
- Average risk is ranked at 3 decimals, the precision shown — two routes that look tied are then treated as tied, so travel time decides — cost if wrong: differences under 0.001 no longer decide.
- Corridor budget stays sized before removing duplicates (reviewer preferred after) — one row still applies to long trips either way, and the route stays covered — cost if wrong: a thinner corridor on long trips with shared roads.
- Past-departure question closed — a live call showed TomTom accepts a departure 10 minutes in the past — cost if wrong: none.
- US-only search, 0.05 degree weather grid, sustained wind rather than gusts, 33,000 lb tare and 65 mph cap stand as documented assumptions; hosting and the Loom remain open deliverables — the reviewer set these aside as outside the spec — cost if wrong: each is one constant or a documented choice.

## Deployment

- Deploys use GitHub OIDC, restricted to the `production` environment, which only allows `main` — no AWS keys are stored in GitHub. This replaces the earlier pull-on-a-timer design, needed only while the AWS account couldn't create identity providers — cost if wrong: the workflow is one file to change.
- GitHub reaches the server over SSH using Lightsail's short-lived keys, with port 22 open only to the runner during a deploy and the host key pinned — Lightsail has no SSM agent by default, and this avoids a stored SSH key — cost if wrong: a cancelled run can leave that one IP allowed until the next deploy.
- The role can only get SSH access to this one server and open or close its ports — the narrowest set that works. SSH access still means root on the server — cost if wrong: rebuilding the server needs the policy updated.
- Deploys run automatically after CI passes on `main` — the user asked for a CD workflow — cost if wrong: remove the trigger, keeping the manual one.
- The health endpoint reports the running version, and the workflow confirms it on the public site — this proves the deploy reached users — cost if wrong: none; the commit hash is already public.
- A failed deploy rolls back automatically and isn't retried until a newer commit is published — a bad release shouldn't loop or leave the app down — cost if wrong: a failure caused by a brief outage needs a new commit or a manual redeploy.
- Redis is removed from the deployed stack, with the cache in the app's process, limited to 5,000 entries, and one worker — the user chose to drop caching infrastructure while there are no users, and rate limits still need a cache — cost if wrong: an empty cache after each update; adding `REDIS_URL` brings Redis back.
- ALLOWED_HOSTS is still required in production, and `REDIS_URL` no longer is — a server with no Redis must still start — cost if wrong: none.
- The data credit sits under the page title and in the map's attribution — Open-Meteo's licence asks for it next to wherever its data appears, and the map's control collapses on small screens or after a drag — cost if wrong: a line of text to move. TomTom's credit is its own Copyright API caption, as clause 17.3 of its terms requires, and is left out if that call fails rather than invented. Its name isn't otherwise used, since that needs written approval.

- A trip over the weather budget is refused whole, not checked in part — partly checked routes would rank by what was fetched, not by weather — cost if wrong: a user waits, even though some of the trip could have been checked.
- The weather budget doesn't track the per-minute limit — the existing wait on Open-Meteo's minute limit already handles it, and tracking it too would add a second wait path — cost if wrong: long trips still see the occasional rate-limit response.
- Budget counters live in the shared cache, and only locations actually fetched stay charged — charging failures locked users out after an outage, which a local hang test showed — cost if wrong: a restart or full cache forgets counts, with Open-Meteo's limit as the backstop.
- Weather loading stops at 120 seconds or after two failed batches in a row — one more request can still take its 30-second timeout, which ends inside nginx's 170-second limit, and one failure alone may be a blip — cost if wrong: very slow provider days show more `unknown` miles.
- The circuit breaker lives in each process rather than the shared cache — there's one worker, and it needs no extra round trips — cost if wrong: extra workers would each detect an outage separately.
- Django logs requests in place of Gunicorn's access log — the access log includes search text — cost if wrong: requests rejected before Django aren't logged.
- `web-vitals` was added for browser timings, reported to our own API instead of an outside service — no account or new data processor is needed — cost if wrong: one small dependency to remove.
- TomTom results are never cached on the server — clause 11.4 of its terms bans caching that serves several users — cost if wrong: repeat trips and searches keep spending TomTom quota, which is the price of following the terms.
- Trips needing weather only within about a week fetch a 7-day forecast instead of 16 — a batch of 100 locations measured about half the time and a fifth of the data — cost if wrong: entries for the two lengths are cached separately, so some forecasts are fetched twice.
- Six heavy requests run at once per worker, and more get a `busy` error rather than queueing — this keeps threads free for searches and health checks — cost if wrong: the limit hasn't been reached in a load test, so it could refuse trips the server could have handled.
- The load test uses invented routes, not recorded ones — TomTom's terms don't allow storing its results — cost if wrong: real route shapes could cost more or less CPU.
- Redis and more workers are an optional overlay, not switched on — the load test stopped before comparing them, and they use memory on a small server — cost if wrong: one worker's CPU remains the limit until someone turns the overlay on.
- The page opens on a hero with a parallax scroll, and the planner is the next screen — requested for the UI update — cost if wrong: every test and visitor now scrolls past it to reach the planner.
- Parallax is written directly to the layers on each scroll frame, with no animation library — it adds nothing to the bundle and never re-renders React, which keeps the map smooth — cost if wrong: future gesture-driven springs would still need a library.
- The hero film is a rendered clip with no text, and the headline is real page text — text stays sharp and accessible, and doesn't wait for video — cost if wrong: 256 KB more on first load (111 KB for browsers that take the MP4).
- The film's checkpoint colours are illustrative, not weather — it plays before any trip exists — cost if wrong: someone could read it as a real forecast, so it carries no place names or numbers.
- Reduced motion and data saving get a still image and no parallax — the skill's accessibility rule — cost if wrong: none.
- The system font replaces Overpass, and blue replaces the highway-sign green as the action colour — Apple's guidance is to use the platform font, and blue stays clear of the risk colours on the map — cost if wrong: the app looks a little less distinctive, and differs slightly by device.
- The map's wheel zoom stays off until it's at least 95% in view — otherwise a map rising under the pointer captures the scroll partway up the screen — cost if wrong: a slightly short map can't zoom by wheel until it's scrolled into place.

## Known minor issues, left as they are

- CI uses actions and uv by tag, not SHA or pinned uv version.
- .dockerignore is per build context, not at the repo root as the brief names.
- Commit-policy attribution regex is per line, so a trailer split across lines is missed.
- A Redis outage raises from cache.get_many and fails the request instead of falling back to the provider. Revisit in Task 12.
- DRF throttling identifies clients by IP, so a hosting proxy needs NUM_PROXIES set or all users share one limit. Revisit in Task 12.
- TomTom responses are not cached, so a repeat trip takes 6-12s even with cached weather.
- Where route lines run close together, a click selects whichever is on top (seen once on mobile: a click near route 2 selected route 3). The labels and list remain exact.
- A displayed reading can round to the next class, such as interpolated wind 54.96 shown as 55 mph with Severe.
- A hung Open-Meteo takes up to 270s across batches, past nginx's 170s, and gives a generic error.
- A detour outage still warns "Only N distinct routes", which blames geography.
- The form doesn't state that the departure is in the browser's time zone.
- A nonexistent DST local time produces an inconsistent offset.
- A new Intl.DateTimeFormat per row, about 48ms for 280 rows cold.
- Heatmap retry fails once the departure is over 15 minutes old.
- Load_lb true is accepted as 1 lb.
- No browser test for fewer than 3 routes.
- CI's frontend job skips format:check.
- The gunicorn timeout comment's reason is likely wrong for threaded workers.
- Nginx sets no security headers and forwards a client-supplied X-Forwarded-Proto.
