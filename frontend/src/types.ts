export type Severity = "BLOQUANT" | "AVERTISSEMENT" | "INFO";

/** Mirrors com.wealthguard.quality.domain.Anomaly (Jackson-serialised). */
export interface Anomaly {
  ruleId: string;
  ruleLabel: string;
  category: string;
  severity: Severity;
  dataset: string;
  recordKey: string;
  fieldName: string | null;
  observedValue: string | null;
  message: string;
  estimatedImpact: string;
  suggestedFix: string;
}

export interface ValidationCounts {
  positions: number;
  clients: number;
  instruments: number;
  targetAllocations: number;
  anomalies: number;
  blockingAnomalies: number;
}

/** Mirrors com.wealthguard.quality.domain.ValidationReport. */
export interface ValidationReport {
  reportId: string;
  validatedAt: string;
  evaluationDate: string;
  counts: ValidationCounts;
  countsBySeverity: Record<string, number>;
  countsByRule: Record<string, number>;
  countsByCategory: Record<string, number>;
  executedRules: string[];
  durationMillis: number;
  anomalies: Anomaly[];
}

export const SEVERITIES: Severity[] = ["BLOQUANT", "AVERTISSEMENT", "INFO"];
