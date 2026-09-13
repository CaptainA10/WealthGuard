package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
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

class AllocationSumEquals100RuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "ALLOC_SUM_EQUALS_100", Severity.AVERTISSEMENT, Map.of("tolerancePct", "0.5"));

    private final AllocationSumEquals100Rule rule = new AllocationSumEquals100Rule(DEFINITION);

    @Test
    void isNotApplicableWithoutAnyAllocations() {
        ValidationContext context = new ValidationContext(
                List.of(), List.of(), List.of(), List.of(), LocalDate.of(2024, 1, 1));

        assertThat(rule.isApplicable(context)).isFalse();
    }

    @Test
    void reportsNoAnomalyWhenTheSumIsExactly100() {
        ValidationContext context = context(
                allocation("C1", "ACTIONS", "60"),
                allocation("C1", "OBLIGATIONS", "40"));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsNoAnomalyWithinTolerance() {
        ValidationContext context = context(
                allocation("C1", "ACTIONS", "60.3"),
                allocation("C1", "OBLIGATIONS", "40"));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsADeviationBeyondTolerance() {
        ValidationContext context = context(
                allocation("C1", "ACTIONS", "70"),
                allocation("C1", "OBLIGATIONS", "37"));

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).recordKey()).isEqualTo("client_id=C1");
    }

    @Test
    void isolatesTheSumPerClient() {
        ValidationContext context = context(
                allocation("A", "ACTIONS", "100"),
                allocation("B", "ACTIONS", "50"));

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).recordKey()).isEqualTo("client_id=B");
    }

    private static TargetAllocation allocation(String clientId, String assetClass, String weight) {
        return new TargetAllocation(clientId, assetClass, new BigDecimal(weight));
    }

    private static ValidationContext context(TargetAllocation... allocations) {
        return new ValidationContext(List.of(), List.of(), List.of(), List.of(allocations), LocalDate.of(2024, 1, 1));
    }
}
