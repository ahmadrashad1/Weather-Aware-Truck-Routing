# Loom walkthrough checklist

A script for the 5–10 minute walkthrough. The timings add up to about 8 minutes.

## Before recording

- [ ] Start the app with `docker compose up --build`, and open <http://localhost:8080>.
- [ ] Plan the demo trips once beforehand. Forecasts stay cached for an hour, so they load quickly during the recording.
- [ ] Check the forecast and pick a trip with real bad weather if you can. Otherwise, use the fixture run below to show the risk colours.
- [ ] Zoom the browser so the map and route cards are readable.
- [ ] Close anything showing `.env` or API keys.

## 1. The problem (30 seconds)

- The app helps a truck driver choose the safest route, based on weather, load weight and travel time.
- The key idea: weather is checked for when the truck will reach each place, not when it leaves.

## 2. Plan a trip (1 minute)

- [ ] Type a partial city name, and show the suggestions.
- [ ] Set the departure time and a 45,000 lb load.
- [ ] Choose a 25-mile interval. Mention 10 and 50 are also available.
- [ ] Plan the routes.

## 3. The recommendation (2 minutes)

This is the heart of the assessment, so spend time here.

- [ ] Point out the recommended route, and read its reason aloud.
- [ ] Explain the strict order: fewest Severe miles, fewest High miles, lowest average risk, shortest travel time. It's not a weighted score.
- [ ] If you can, show a slower route beating a faster one. New York to Los Angeles has done this: a longer route won because the faster one had 10 High miles.
- [ ] Explain No Travel: those routes rank last and are never recommended, because the assessment's order doesn't mention them and could otherwise recommend a forbidden route.
- [ ] Mention the trade-off: the strict order can add hours for a tiny average-risk difference. Say this follows the rule as written.

## 4. The risk rules (1.5 minutes)

- [ ] Open `backend/routing/services/risk_engine.py`, and show the thresholds in one place.
- [ ] Give one boundary example: rain at exactly 0.25 in/hr is High, and at exactly 1.00 stays Severe.
- [ ] Give one load example: 35 mph is High at 40,000 lb, but Severe at 40,001 lb.
- [ ] Show the matching tests in `backend/tests/services/test_risk_engine.py`.

## 5. Checkpoints and ETAs (1 minute)

- [ ] Open a checkpoint from the list, and show its popup on the map.
- [ ] Point out the ETA, wind, rain, snow, and each condition's risk.
- [ ] Click a checkpoint on the map itself, and show the list follows.
- [ ] Explain ETAs use the elapsed time along the real route, with truck speed capped at about 65 mph.

## 6. The heatmap (1 minute)

- [ ] Drag the slider slowly from 0 to 48, then quickly. Show it stays smooth.
- [ ] Open the browser's network tab, and show that dragging makes no requests.
- [ ] Explain the shading shows risk for this load at the chosen hour, while route colours use each checkpoint's arrival time.
- [ ] Explain why it's a blurred circle layer: a heatmap layer drew No Travel as pale as Moderate, so a driver could misread it.

## 7. Engineering (1 minute)

- [ ] Show the architecture diagram in `README.md`.
- [ ] Show CI on a pull request: five checks, including browser tests with real WebGL.
- [ ] Mention the signed commits and the protected `main` branch.
- [ ] Mention a bug only real browser testing found: the map's worker failing in the production image.

## Close

- [ ] State the known limits: free-tier forecast quota, and about 80 seconds for a coast-to-coast trip on an empty cache.

## Showing the risk colours if the weather is calm

Live weather may be mild on the day. The browser tests' storm fixture shows every level at hour 12. Playwright's UI mode lets you step through a test at your own pace:

```bash
cd frontend
npx playwright test e2e/heatmap.spec.ts --project=desktop --ui
```

Run "the shading follows the selected hour", and step to the frame after the slider moves to 12. These tests use a blank background instead of the real base map. Say plainly that this is test data, and not a live forecast.
