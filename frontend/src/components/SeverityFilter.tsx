import { SEVERITIES, type Severity } from "../types";
import { SeverityBadge } from "./SeverityBadge";

interface Props {
  active: Set<Severity>;
  countsBySeverity: Record<string, number>;
  onToggle: (severity: Severity) => void;
}

export function SeverityFilter({ active, countsBySeverity, onToggle }: Props) {
  return (
    <div className="severity-filter" role="group" aria-label="Filtrer par criticité">
      {SEVERITIES.map((severity) => (
        <button
          key={severity}
          type="button"
          className={active.has(severity) ? "filter-chip filter-chip-active" : "filter-chip"}
          onClick={() => onToggle(severity)}
          aria-pressed={active.has(severity)}
        >
          <SeverityBadge severity={severity} />
          <span className="filter-count">{countsBySeverity[severity] ?? 0}</span>
        </button>
      ))}
    </div>
  );
}
