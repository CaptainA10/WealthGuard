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

class PositionQuantityPrecisionRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "POS_QUANTITY_PRECISION", Severity.INFO, Map.of("maxDecimals", "4"));

    private final PositionQuantityPrecisionRule rule = new PositionQuantityPrecisionRule(DEFINITION);

    @Test
    void reportsNoAnomalyAtExactlyTheMaxDecimals() {
        assertThat(rule.evaluate(context(position("1.2345")))).isEmpty();
    }

    @Test
    void reportsAQuantityWithTooManyDecimals() {
        List<Anomaly> anomalies = rule.evaluate(context(position("1.23456")));

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).severity()).isEqualTo(Severity.INFO);
    }

    @Test
    void reportsNoAnomalyForAnIntegerQuantity() {
        assertThat(rule.evaluate(context(position("100")))).isEmpty();
    }

    @Test
    void skipsANullQuantity() {
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
