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

- The project uses CI/CD pipelines to build, test, and ship the software. `docs/deployment.md` describes the deployment.
- After CI passes on `main`, the `Deploy` workflow publishes images and deploys them through GitHub OIDC. GitHub stores no AWS keys.
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
- The only video is the short hero clip, made with the `motion-graphics` skill from `videos/hero-routes/`. Live UI motion follows the `apple-design` skill, in code rather than video.
- Use `apple-design` for UI work alongside `frontend-design`.

<!-- BEGIN AWS Agent Toolkit rules -->

The rules above take precedence over this block where they conflict. This project's Region is `ap-southeast-2`.

# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context

### Terminology:

- Say "project" instead of "account" — a project contains an AWS account and settings for sharing with other collaborators
- Say "team member" instead of "IAM user" — users are invited by email, not created or federated in IAM
- Say "AWS Settings" when referring to management tasks at [settings.aws.com](https://settings.aws.com/) (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region — not "home Region"
- The user has a managed IAM experience. This includes a managed service control policies (SCP) and resource control policies (RCP) that govern the use of AWS. They will still need to use IAM to create policies to let services work with each other. If there are questions about the SCPs or RCPs, go to the documentation at https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html

### Constraints:

- All projects share a single AWS Region determined by the user's contact address. Resources cannot be created in other Regions
- When developing:
  - MUST create all Regional resources in the project's assigned Region
  - You CAN create AWS WAF and Cloudwatch Logs resources in us-east-1 when there are global resources (like a global WAF instance) that require a connection to dependencies in us-east-1. You should not use these for any other reason, because resources in the selected Region will provide lower cost (due to no cross-Region traffic), increased availability (due to no cross-Region traffic), and easier manageability (due to not needing to look in another Region). When you need to do an inventory of resources, you need to look in both the selected Region and us-east-1 for Cloudwatch Logs or WAF resources.
  - MUST NOT attempt to create Lambda, API Gateway, or other Regional resources in any other Region
  - MUST direct users to confirm their Region in AWS Settings > View all projects > Overview > Additional Info > Region. If the user cannot confirm their Region, check in ~/.aws/config
  - MUST NOT use Lambda@Edge — excluded from both Lambda and CloudFront
  - MUST NOT use CloudFormation StackSets — no multi-account or multi-Region deployments
  - MUST NOT attempt cross-Region actions — no cross-Region replication for DynamoDB/S3/RDS, no multi-Region KMS keys
  - MUST NOT use Route 53 cross-Region routing — geolocation, latency-based, and failover routing policies are not available
  - CloudFront is a global service and its actions ARE allowed in `us-east-1`. A user can create a CloudFront distribution pointing to their project-region Lambda function URL or API Gateway. However, Lambda and API Gateway themselves MUST NOT be created in `us-east-1` — they must be in the project Region.
  - Reduced availability in `eu-north-1` specifically: Amazon Rekognition, Amazon Textract, Amazon Personalize, AWS App Runner are not available in that Region.
- IAM permissions for human access are managed by AWS. Don't assign roles to team members unless absolutely necessary
- The user may have a spend limit if they are on the paid plan. The limit that pauses their project if it's exceeded. If resources suddenly become inaccessible, ask if they have a spend limit configured. Only project owners can modify a spend limit.
- When developing:
  - MUST ask about spend limit status if the user reports sudden "Access Denied" errors on operations that previously worked
  - MUST direct users to check spend status in AWS Settings > Billing
  - MUST check if a user has upgraded their account to the paid plan
  - MUST ask the user if they want to clean up the successfully created resources or keep them to reduce cost
- The user sets up billing, creates spend limits, and retrieves and pays invoices in AWS Settings. The user creates budgets and optimizes their costs in the AWS Billing and Cost Management console
- Not all AWS services are available. If a service isn't working, do the following:
  1. Run the command `aws freetier get-account-plan-state`
  2. If accountPlanType": "FREE", check the [Free Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-free-tier) next,
  3. If accountPlanType": "PAID", check the [Paid Tier supported services list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#supported-services-paid-plan).
  4. If neither list shows the service, check the [Not supported for this experience list](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html#unsupported-services). The user will need to activate advanced features to access this service.
- Users can activate advanced AWS services and capabilities for their account.
- For any AWS task or question — building, configuring, migrating, debugging, or operating a service, writing SDK code, authoring CDK/CloudFormation, or answering how a service works — first call `aws___search_documentation` with topic `agent_skills` and load the matching skill with `aws___retrieve_skill`. Do this even when you believe you know the answer: skills carry current service behavior that your training may not. Prefer the skill's guidance over general knowledge. Skip it only for work that does not involve AWS.

### Help level

- help_level (required): LOW, MEDIUM, or HIGH. While a user is building, you MUST ask the user: "How much guidance would you like from me? Low (I only flag security risks), medium (I ask a couple of clarifying questions if something seems off), or high (I explain what I'm doing, suggest alternatives, and flag best practices)."

You CAN update this rule file to save a user's help_level.

Constraints for each level:

**LOW:**

- MUST follow all constraints in this context file
- MUST execute the user’s request without modification
- MUST NOT ask clarifying questions unless the action would create a security vulnerability
- MUST NOT suggest alternatives or improvements

**MEDIUM:**

- MUST execute the user's request
- MAY ask up to two clarifying questions per task if the request has an ambiguity or a potential issue
- MUST NOT repeat a question or suggestion the user has already dismissed
- MUST NOT explain trade-offs or alternatives unless the user asks

**HIGH:**

- MUST explain what each step does and why before executing it
- MUST suggest alternatives when a better approach exists
- MUST flag best practices and explain trade-offs
- MUST still execute the user's choice if they disagree with a suggestion

<!-- END AWS Agent Toolkit rules -->
