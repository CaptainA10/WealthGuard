import type { Severity } from "../types";

const LABELS: Record<Severity, string> = {
  BLOQUANT: "Bloquant",
  AVERTISSEMENT: "Avertissement",
  INFO: "Info",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={`badge badge-${severity.toLowerCase()}`}>{LABELS[severity]}</span>;
}
