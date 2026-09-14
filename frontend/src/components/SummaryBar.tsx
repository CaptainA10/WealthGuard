import type { ValidationReport } from "../types";

export function SummaryBar({ report }: { report: ValidationReport }) {
  const { counts, executedRules, durationMillis } = report;
  return (
    <dl className="summary-bar">
      <div className="summary-stat">
        <dt>Positions analysées</dt>
        <dd>{counts.positions}</dd>
      </div>
      <div className="summary-stat">
        <dt>Anomalies</dt>
        <dd>{counts.anomalies}</dd>
      </div>
      <div className="summary-stat summary-stat-critical">
        <dt>Bloquantes</dt>
        <dd>{counts.blockingAnomalies}</dd>
      </div>
      <div className="summary-stat">
        <dt>Règles exécutées</dt>
        <dd>{executedRules.length}</dd>
      </div>
      <div className="summary-stat">
        <dt>Durée moteur</dt>
        <dd>{durationMillis} ms</dd>
      </div>
    </dl>
  );
}
