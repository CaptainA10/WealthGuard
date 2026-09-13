package com.wealthguard.quality.domain;

import java.time.Instant;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * The outcome of one validation run: the anomalies plus the aggregates a
 * dashboard or a CI gate needs without having to re-scan the list.
 */
public record ValidationReport(
        String reportId,
        Instant validatedAt,
        LocalDate evaluationDate,
        Counts counts,
        Map<String, Integer> countsBySeverity,
        Map<String, Integer> countsByRule,
        Map<String, Integer> countsByCategory,
        List<String> executedRules,
        long durationMillis,
        List<Anomaly> anomalies) {

    /** Volume of input actually examined -- lets a consumer detect a truncated batch. */
    public record Counts(
            int positions,
            int clients,
            int instruments,
            int targetAllocations,
            int anomalies,
            int blockingAnomalies) {
    }

    /**
     * Assemble a report, sorting the findings worst-first.
     *
     * <p>Sort order is (severity, ruleId, recordKey): deterministic, which is what
     * lets the end-to-end test diff the response against the seed manifest.
     */
    public static ValidationReport of(
            String reportId,
            Instant validatedAt,
            ValidationContext context,
            List<String> executedRules,
            List<Anomaly> anomalies,
            long durationMillis) {

        List<Anomaly> sorted = anomalies.stream()
                .sorted(Comparator.comparingInt((Anomaly a) -> a.severity().rank())
                        .thenComparing(Anomaly::ruleId)
                        .thenComparing(Anomaly::recordKey))
                .toList();

        Map<String, Integer> bySeverity = new LinkedHashMap<>();
        for (Severity severity : Severity.values()) {
            bySeverity.put(severity.name(), 0);
        }
        Map<String, Integer> byRule = new TreeMap<>();
        Map<String, Integer> byCategory = new TreeMap<>();
        int blocking = 0;
        for (Anomaly anomaly : sorted) {
            bySeverity.merge(anomaly.severity().name(), 1, Integer::sum);
            byRule.merge(anomaly.ruleId(), 1, Integer::sum);
            byCategory.merge(String.valueOf(anomaly.category()), 1, Integer::sum);
            if (anomaly.severity().isBlocking()) {
                blocking++;
            }
        }

        Counts counts = new Counts(
                context.positions().size(),
                context.clients().size(),
                context.instruments().size(),
                context.targetAllocations().size(),
                sorted.size(),
                blocking);

        return new ValidationReport(
                reportId,
                validatedAt,
                context.evaluationDate(),
                counts,
                bySeverity,
                byRule,
                byCategory,
                List.copyOf(executedRules),
                durationMillis,
                sorted);
    }

    /** True when at least one BLOQUANT anomaly was found: the pipeline must not load the batch as-is. */
    public boolean hasBlockingAnomalies() {
        return counts.blockingAnomalies() > 0;
    }
}
