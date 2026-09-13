package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Severity;
import com.wealthguard.quality.domain.TargetAllocation;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.RuleDefinition;
import com.wealthguard.quality.support.RuleDefinitions;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class AllocationWeightInRangeRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "ALLOC_WEIGHT_IN_RANGE", Severity.BLOQUANT,
            Map.of("minInclusive", "0", "maxInclusive", "100"));

    private final AllocationWeightInRangeRule rule = new AllocationWeightInRangeRule(DEFINITION);

    @Test
    void reportsNoAnomalyForAWeightInsideTheRange() {
        assertThat(rule.evaluate(context(allocation("50")))).isEmpty();
    }

    @Test
    void reportsANegativeWeight() {
        assertThat(rule.evaluate(context(allocation("-5")))).hasSize(1);
    }

    @Test
    void reportsAWeightAboveOneHundred() {
        assertThat(rule.evaluate(context(allocation("105")))).hasSize(1);
    }

    @Test
    void reportsNoAnomalyAtTheRangeBoundaries() {
        assertThat(rule.evaluate(context(allocation("0")))).isEmpty();
        assertThat(rule.evaluate(context(allocation("100")))).isEmpty();
    }

    @Test
    void skipsANullWeight() {
        assertThat(rule.evaluate(context(new TargetAllocation("C1", "ACTIONS", null)))).isEmpty();
    }

    private static TargetAllocation allocation(String weight) {
        return new TargetAllocation("C1", "ACTIONS", new BigDecimal(weight));
    }

    private static ValidationContext context(TargetAllocation allocation) {
        return new ValidationContext(List.of(), List.of(), List.of(), List.of(allocation), LocalDate.of(2024, 1, 1));
    }
}
