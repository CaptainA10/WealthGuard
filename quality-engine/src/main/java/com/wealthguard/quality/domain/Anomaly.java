package com.wealthguard.quality.domain;

import java.util.Objects;

/**
 * A single quality finding.
 *
 * <p>The field list is driven by cahier des charges §2.2, which requires a
 * structured log carrying: the source, the offending line, the violated rule,
 * the estimated impact and a correction hypothesis. The last two are the ones
 * that make a report actionable -- "quantity is negative" tells an analyst
 * nothing they could not see; "the client's AUM is understated by 48 210 EUR,
 * probably a sign inversion in the custodian export" tells them what to do.
 */
public record Anomaly(
        String ruleId,
        String ruleLabel,
        RuleCategory category,
        Severity severity,
        String dataset,
        String recordKey,
        String fieldName,
        String observedValue,
        String message,
        String estimatedImpact,
        String suggestedFix) {

    public Anomaly {
        Objects.requireNonNull(ruleId, "ruleId");
        Objects.requireNonNull(severity, "severity");
        Objects.requireNonNull(dataset, "dataset");
        Objects.requireNonNull(recordKey, "recordKey");
    }

    /**
     * Single-line structured rendering for the application log.
     *
     * <p>Key=value pairs rather than prose so that the log is greppable and can
     * be shipped to a log aggregator without a custom parser.
     */
    public String toStructuredLog() {
        return "quality_anomaly"
                + " rule=" + ruleId
                + " severity=" + severity
                + " category=" + category
                + " dataset=" + dataset
                + " record=" + recordKey
                + " field=" + (fieldName == null ? "-" : fieldName)
                + " observed=" + (observedValue == null ? "<null>" : observedValue)
                + " impact=\"" + estimatedImpact + "\""
                + " fix=\"" + suggestedFix + "\"";
    }
}
