package com.wealthguard.quality.rules.completeness;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.RuleCategory;
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

class PositionRequiredFieldsRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "POS_REQUIRED_FIELDS",
            RuleCategory.COMPLETUDE,
            Severity.BLOQUANT,
            Map.of("fields", "positionId,clientId,ticker,quantity,purchasePrice,purchaseDate,currency"));

    private final PositionRequiredFieldsRule rule = new PositionRequiredFieldsRule(DEFINITION);

    @Test
    void reportsNoAnomalyWhenEveryFieldIsPresent() {
        Position complete = new Position(
                "P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");
        ValidationContext context = context(complete);

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsOneAnomalyPerMissingField() {
        Position missingTwoFields = new Position(
                "P1", null, "AAPL", BigDecimal.TEN, null, LocalDate.of(2024, 1, 1), "USD");
        ValidationContext context = context(missingTwoFields);

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(2);
        assertThat(anomalies).extracting(Anomaly::fieldName).containsExactlyInAnyOrder("clientId", "purchasePrice");
    }

    @Test
    void treatsABlankStringAsAbsent() {
        Position blankTicker = new Position(
                "P1", "C1", "  ", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");
        ValidationContext context = context(blankTicker);

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).fieldName()).isEqualTo("ticker");
        assertThat(anomalies.get(0).severity()).isEqualTo(Severity.BLOQUANT);
    }

    @Test
    void reportsEveryMissingFieldWithItsOwnImpactMessage() {
        Position missingEverything = new Position(null, null, null, null, null, null, null);
        ValidationContext context = context(missingEverything);

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(7);
        assertThat(anomalies).extracting(Anomaly::fieldName).containsExactlyInAnyOrder(
                "positionId", "clientId", "ticker", "quantity", "purchasePrice", "purchaseDate", "currency");
        assertThat(anomalies).allSatisfy(a -> assertThat(a.estimatedImpact()).isNotBlank());
    }

    @Test
    void rejectsAnUnknownFieldNameAtConstruction() {
        RuleDefinition badDefinition = RuleDefinitions.of(
                "POS_REQUIRED_FIELDS", RuleCategory.COMPLETUDE, Severity.BLOQUANT,
                Map.of("fields", "notAField"));

        org.assertj.core.api.Assertions.assertThatIllegalStateException()
                .isThrownBy(() -> new PositionRequiredFieldsRule(badDefinition))
                .withMessageContaining("notAField");
    }

    private static ValidationContext context(Position... positions) {
        return new ValidationContext(List.of(positions), List.of(), List.of(), List.of(), LocalDate.of(2024, 1, 1));
    }
}
