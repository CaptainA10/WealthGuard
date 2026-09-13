package com.wealthguard.quality.rules;

import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;

import java.util.Objects;

/**
 * The configured identity of a rule: what it is called, how serious it is, and
 * which parameters it runs with.
 *
 * <p>This is the object that makes the rules "configurable, not hardcoded"
 * (cahier des charges §2.2). A rule implementation receives its definition at
 * construction time and never hardcodes its own severity or thresholds -- so
 * raising the concentration limit from 40% to 25%, or downgrading a control from
 * BLOQUANT to AVERTISSEMENT, is a one-line change in
 * {@code quality-rules.yml} with no recompilation.
 */
public record RuleDefinition(
        String id,
        String label,
        RuleCategory category,
        Severity severity,
        String description,
        RuleParameters parameters) {

    public RuleDefinition {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(category, "category");
        Objects.requireNonNull(severity, "severity");
        parameters = parameters == null ? RuleParameters.empty() : parameters;
        label = (label == null || label.isBlank()) ? id : label;
        description = description == null ? "" : description;
    }
}
