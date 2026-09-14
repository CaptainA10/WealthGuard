import { useEffect, useMemo, useState } from "react";
import { loadReport, type ReportSource } from "./api";
import { AnomalyTable } from "./components/AnomalyTable";
import { SeverityFilter } from "./components/SeverityFilter";
import { SummaryBar } from "./components/SummaryBar";
import { SEVERITIES, type Severity, type ValidationReport } from "./types";
import "./App.css";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; report: ValidationReport; source: ReportSource };

function App() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [activeSeverities, setActiveSeverities] = useState<Set<Severity>>(new Set(SEVERITIES));

  useEffect(() => {
    let cancelled = false;
    loadReport()
      .then(({ report, source }) => {
        if (!cancelled) setState({ status: "ready", report, source });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: "error", message: error instanceof Error ? error.message : String(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filteredAnomalies = useMemo(() => {
    if (state.status !== "ready") return [];
    return state.report.anomalies.filter((a) => activeSeverities.has(a.severity));
  }, [state, activeSeverities]);

  function toggleSeverity(severity: Severity) {
    setActiveSeverities((current) => {
      const next = new Set(current);
      if (next.has(severity)) {
        next.delete(severity);
      } else {
        next.add(severity);
      }
      return next;
    });
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>WealthGuard — Anomalies</h1>
        <p className="subtitle">
          Contrôle qualité en temps réel des positions de portefeuille, via le moteur de règles
          Java.
        </p>
      </header>

      {state.status === "loading" && <p className="status-message">Validation du lot en cours…</p>}

      {state.status === "error" && (
        <p className="status-message status-error">
          Impossible de contacter le moteur de qualité, et impossible de charger l'instantané de
          démo non plus : {state.message}
        </p>
      )}

      {state.status === "ready" && (
        <>
          {state.source === "demo" && (
            <p className="status-message status-demo">
              Moteur de qualité injoignable — affichage d'un instantané figé (données réelles,
              non temps réel). Lance <code>quality-engine</code> et <code>data-pipeline</code> en
              local pour la validation en direct — voir le README du dépôt.
            </p>
          )}
          <SummaryBar report={state.report} />
          <SeverityFilter
            active={activeSeverities}
            countsBySeverity={state.report.countsBySeverity}
            onToggle={toggleSeverity}
          />
          <AnomalyTable anomalies={filteredAnomalies} />
        </>
      )}
    </div>
  );
}

export default App;
