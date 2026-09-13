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

class PositionPositivePurchasePriceRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "POS_POSITIVE_PURCHASE_PRICE", Severity.BLOQUANT, Map.of("minExclusive", "0"));

    private final PositionPositivePurchasePriceRule rule = new PositionPositivePurchasePriceRule(DEFINITION);

    @Test
    void reportsNoAnomalyForAPositivePrice() {
        assertThat(rule.evaluate(context(position("100")))).isEmpty();
    }

    @Test
    void reportsANegativePriceAsAnomaly() {
        assertThat(rule.evaluate(context(position("-1")))).hasSize(1);
    }

    @Test
    void treatsZeroAsTheClassicEdgeCase() {
        List<Anomaly> anomalies = rule.evaluate(context(position("0")));

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).message()).contains("nul");
    }

    @Test
    void skipsANullPriceBecauseItIsAnotherRulesFinding() {
        Position noPrice = new Position("P1", "C1", "AAPL", BigDecimal.TEN, null, LocalDate.of(2024, 1, 1), "USD");

        assertThat(rule.evaluate(context(noPrice))).isEmpty();
    }

    private static Position position(String price) {
        return new Position(
                "P1", "C1", "AAPL", BigDecimal.TEN, new BigDecimal(price), LocalDate.of(2024, 1, 1), "USD");
    }

    private static ValidationContext context(Position position) {
        return new ValidationContext(List.of(position), List.of(), List.of(), List.of(), LocalDate.of(2024, 1, 1));
    }
}
