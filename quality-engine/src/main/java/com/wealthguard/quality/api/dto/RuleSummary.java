package com.wealthguard.quality.api.dto;

import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.Map;

/**
 * Wire representation of a {@link RuleDefinition} for {@code GET /api/v1/rules}.
 *
 * <p>Not the domain {@link RuleDefinition} itself: its {@code parameters()} is a
 * {@link com.wealthguard.quality.rules.RuleParameters}, a validation helper with
 * no bean-style getters, which Jackson cannot serialize on its own. This DTO
 * flattens it to a plain {@code Map<String, String>} instead of leaking an
 * internal helper class through the API contract.
 */
public record RuleSummary(
        String id,
        String label,
        RuleCategory category,
        Severity severity,
        String description,
        Map<String, String> parameters) {

    public static RuleSummary from(RuleDefinition definition) {
        return new RuleSummary(
                definition.id(),
                definition.label(),
                definition.category(),
                definition.severity(),
                definition.description(),
                definition.parameters().asMap());
    }
}
