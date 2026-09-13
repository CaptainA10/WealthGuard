package com.wealthguard.quality.rules;

import com.wealthguard.quality.domain.Anomaly;

import java.util.Objects;

/**
 * Shared plumbing for every rule: holds the {@link RuleDefinition} and builds
 * {@link Anomaly} instances pre-filled with this rule's identity.
 *
 * <p>Without this, all sixteen rules would repeat the same seven constructor
 * arguments and would be free to report a severity that disagrees with their own
 * configuration. Here the id, label, category and severity can only ever come
 * from the definition.
 */
public abstract class AbstractQualityRule implements QualityRule {

    private final RuleDefinition definition;

    protected AbstractQualityRule(RuleDefinition definition) {
        this.definition = Objects.requireNonNull(definition, "definition");
    }

    @Override
    public final RuleDefinition definition() {
        return definition;
    }

    /** Shorthand for the rule's parameters, validated at construction time. */
    protected final RuleParameters parameters() {
        return definition.parameters();
    }

    /**
     * Build an anomaly attributed to this rule.
     *
     * @param dataset       source dataset name (positions, clients, target_allocations)
     * @param recordKey     business key of the offending line
     * @param fieldName     offending field, or {@code null} for a record-level finding
     * @param observedValue what was actually received, rendered for a human
     * @param message       what is wrong, in business terms
     * @param impact        estimated consequence if the record were loaded as-is
     * @param fix           correction hypothesis for the data steward
     */
    protected final Anomaly anomaly(
            String dataset,
            String recordKey,
            String fieldName,
            Object observedValue,
            String message,
            String impact,
            String fix) {

        return new Anomaly(
                definition.id(),
                definition.label(),
                definition.category(),
                definition.severity(),
                dataset,
                recordKey,
                fieldName,
                observedValue == null ? null : String.valueOf(observedValue),
                message,
                impact,
                fix);
    }

    @Override
    public String toString() {
        return definition.id() + "[" + definition.severity() + "]";
    }
}
