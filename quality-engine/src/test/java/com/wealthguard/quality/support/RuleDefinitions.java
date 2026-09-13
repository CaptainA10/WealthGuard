package com.wealthguard.quality.support;

import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;
import com.wealthguard.quality.rules.RuleDefinition;
import com.wealthguard.quality.rules.RuleParameters;

import java.util.Map;

/**
 * Builds a {@link RuleDefinition} for a unit test without the ceremony of a full
 * {@code quality-rules.yml} fixture.
 */
public final class RuleDefinitions {

    private RuleDefinitions() {
    }

    public static RuleDefinition of(String id, RuleCategory category, Severity severity, Map<String, String> parameters) {
        return new RuleDefinition(id, id, category, severity, "test rule", RuleParameters.of(parameters, id));
    }

    /** Convenience overload for rules whose category is not under test. */
    public static RuleDefinition of(String id, Severity severity, Map<String, String> parameters) {
        return of(id, RuleCategory.COHERENCE_METIER, severity, parameters);
    }

    public static RuleDefinition of(String id, Severity severity) {
        return of(id, severity, Map.of());
    }
}
