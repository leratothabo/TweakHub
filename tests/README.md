# tests/

Backend unit tests live next to the code they test, in `apps/api/tests/`
(run with `npm run test:api` or `cd apps/api && pytest`). This top-level
`tests/` directory is reserved for cross-app integration/e2e tests (e.g.
Playwright hitting a running `docker compose` stack) once those exist —
none are scaffolded yet.
