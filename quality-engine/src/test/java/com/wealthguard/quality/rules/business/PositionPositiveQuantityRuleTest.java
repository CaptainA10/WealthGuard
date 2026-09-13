package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.Severity;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.RuleDefinition;
import com.wealthguard.quality.support.RuleDefinitions;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class PositionPositiveQuantityRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "POS_POSITIVE_QUANTITY", Severity.BLOQUANT, Map.of("minExclusive", "0"));

    private final PositionPositiveQuantityRule rule = new PositionPositiveQuantityRule(DEFINITION);

    @Test
    void reportsNoAnomalyForAPositiveQuantity() {
        assertThat(rule.evaluate(context(position("5")))).isEmpty();
    }

    @Test
    void reportsANegativeQuantityAsAnomaly() {
        List<Anomaly> anomalies = rule.evaluate(context(position("-5")));

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).message()).contains("negative");
    }

    @Test
    void treatsZeroAsAViolationNotAPass() {
        List<Anomaly> anomalies = rule.evaluate(context(position("0")));

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).message()).contains("nulle");
    }

    @Test
    void skipsANullQuantityBecauseItIsAnotherRulesFinding() {
        Position noQuantity = new Position("P1", "C1", "AAPL", null, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");

        assertThat(rule.evaluate(context(noQuantity))).isEmpty();
    }

    private static Position position(String quantity) {
        return new Position(
                "P1", "C1", "AAPL", new BigDecimal(quantity), BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");
    }

    private static ValidationContext context(Position position) {
        return new ValidationContext(List.of(position), List.of(), List.of(), List.of(), LocalDate.of(2024, 1, 1));
    }
}
