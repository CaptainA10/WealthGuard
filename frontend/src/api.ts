import type { ValidationReport } from "./types";

/**
 * Base URL of the Java quality engine. Configuration, not a hardcoded
 * `localhost:8080` -- same principle as `quality-rules.yml` and
 * `WG_QUALITY_API_URL` on the Python side: a deployed frontend only needs an
 * env var change, never a rebuild.
 */
const QUALITY_API_URL: string =
  (import.meta.env.VITE_QUALITY_API_URL as string | undefined) ?? "http://localhost:8080";

/**
 * Calls the Java engine directly from the browser (cahier des charges §2.5:
 * "en temps reel via l'API Java"), not a pre-computed report. The request
 * body is a static fixture exported from the seed dataset by
 * `wealthguard_pipeline.seed.export_frontend_fixture` -- in a real deployment
 * this would instead be whatever batch a backend just ingested, but the
 * engine call itself is identical either way.
 */
export async function fetchValidationReport(): Promise<ValidationReport> {
  const fixtureResponse = await fetch("/data/validate-request.json");
  if (!fixtureResponse.ok) {
    throw new Error(
      `Could not load the demo request body (${fixtureResponse.status}). ` +
        "Run `wg-export-frontend-fixture` in data-pipeline first."
    );
  }
  const requestBody = await fixtureResponse.json();

  const response = await fetch(`${QUALITY_API_URL}/api/v1/validate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
  });
  if (!response.ok) {
    throw new Error(
      `The quality engine at ${QUALITY_API_URL} returned ${response.status} ${response.statusText}.`
    );
  }
  return (await response.json()) as ValidationReport;
}
