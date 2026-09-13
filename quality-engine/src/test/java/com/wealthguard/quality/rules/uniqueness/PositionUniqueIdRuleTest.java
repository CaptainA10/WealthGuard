package com.wealthguard.quality.rules.uniqueness;

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

import static org.assertj.core.api.Assertions.assertThat;

class PositionUniqueIdRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of("POS_UNIQUE_ID", Severity.BLOQUANT);

    private final PositionUniqueIdRule rule = new PositionUniqueIdRule(DEFINITION);

    @Test
    void reportsNoAnomalyWhenAllIdsAreUnique() {
        ValidationContext context = context(
                position("P1", "10"),
                position("P2", "5"));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsOneAnomalyPerDuplicatedKeyNotPerExtraRow() {
        ValidationContext context = context(
                position("P1", "10"),
                position("P1", "10"),
                position("P1", "10"));

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).recordKey()).isEqualTo("position_id=P1");
    }

    @Test
    void flagsDivergentQuantitiesInTheMessage() {
        ValidationContext context = context(
                position("P1", "10"),
                position("P1", "20"));

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).estimatedImpact()).contains("quantites differentes");
    }

    @Test
    void ignoresBlankIdsBecauseTheyAreAnotherRulesFinding() {
        ValidationContext context = context(
                new Position(null, "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD"),
                new Position(null, "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD"));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    private static Position position(String id, String quantity) {
        return new Position(id, "C1", "AAPL", new BigDecimal(quantity), BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");
    }

    private static ValidationContext context(Position... positions) {
        return new ValidationContext(List.of(positions), List.of(), List.of(), List.of(), LocalDate.of(2024, 1, 1));
    }
}
