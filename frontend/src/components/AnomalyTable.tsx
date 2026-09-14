import type { Anomaly } from "../types";
import { SeverityBadge } from "./SeverityBadge";

export function AnomalyTable({ anomalies }: { anomalies: Anomaly[] }) {
  if (anomalies.length === 0) {
    return <p className="empty-state">Aucune anomalie pour les criticités sélectionnées.</p>;
  }

  return (
    <div className="anomaly-table-wrapper">
      <table className="anomaly-table">
        <thead>
          <tr>
            <th scope="col">Criticité</th>
            <th scope="col">Règle</th>
            <th scope="col">Jeu de données</th>
            <th scope="col">Enregistrement</th>
            <th scope="col">Message</th>
            <th scope="col">Impact estimé</th>
          </tr>
        </thead>
        <tbody>
          {anomalies.map((anomaly, index) => (
            <tr key={`${anomaly.ruleId}-${anomaly.recordKey}-${index}`}>
              <td>
                <SeverityBadge severity={anomaly.severity} />
              </td>
              <td>
                <span className="rule-label">{anomaly.ruleLabel}</span>
                <span className="rule-id">{anomaly.ruleId}</span>
              </td>
              <td>{anomaly.dataset}</td>
              <td className="record-key">{anomaly.recordKey}</td>
              <td>{anomaly.message}</td>
              <td>{anomaly.estimatedImpact}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
