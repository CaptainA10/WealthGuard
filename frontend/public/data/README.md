# Fixtures

- `validate-request.json` -- exported from `data/seed/landing/` by
  `wg-export-frontend-fixture` (`wealthguard_pipeline.seed.export_frontend_fixture`).
  Regenerate whenever the seed dataset changes:

  ```bash
  cd data-pipeline && wg-export-frontend-fixture --as-of 2026-09-13
  ```

- `demo-report.json` -- a frozen `ValidationReport` snapshot, used as a
  fallback on the public GitHub Pages deployment where no Java engine is
  reachable (see `src/api.ts`'s `loadReport`). Regenerate against a locally
  running engine after regenerating the fixture above:

  ```bash
  curl -s -X POST http://localhost:8080/api/v1/validate \
    -H "Content-Type: application/json" \
    --data-binary @public/data/validate-request.json \
    -o public/data/demo-report.json
  ```
