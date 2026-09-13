package com.wealthguard.quality.rules.referential;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Client;
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

import static org.assertj.core.api.Assertions.assertThat;

class PositionKnownClientRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "POS_KNOWN_CLIENT", RuleCategory.REFERENTIEL, Severity.BLOQUANT, java.util.Map.of());

    private final PositionKnownClientRule rule = new PositionKnownClientRule(DEFINITION);

    @Test
    void isNotApplicableWithoutAClientReferenceTable() {
        ValidationContext context = new ValidationContext(
                List.of(position("C1")), List.of(), List.of(), List.of(), LocalDate.of(2024, 1, 1));

        assertThat(rule.isApplicable(context)).isFalse();
    }

    @Test
    void reportsAnOrphanClientReference() {
        ValidationContext context = new ValidationContext(
                List.of(position("UNKNOWN")),
                List.of(client("C1")),
                List.of(), List.of(), LocalDate.of(2024, 1, 1));

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).fieldName()).isEqualTo("clientId");
    }

    @Test
    void reportsNoAnomalyWhenTheClientResolves() {
        ValidationContext context = new ValidationContext(
                List.of(position("C1")),
                List.of(client("C1")),
                List.of(), List.of(), LocalDate.of(2024, 1, 1));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void skipsANullOrBlankClientIdBecauseItIsAnotherRulesFinding() {
        ValidationContext nullClientId = new ValidationContext(
                List.of(position(null)),
                List.of(client("C1")),
                List.of(), List.of(), LocalDate.of(2024, 1, 1));
        ValidationContext blankClientId = new ValidationContext(
                List.of(position("  ")),
                List.of(client("C1")),
                List.of(), List.of(), LocalDate.of(2024, 1, 1));

        assertThat(rule.evaluate(nullClientId)).isEmpty();
        assertThat(rule.evaluate(blankClientId)).isEmpty();
    }

    private static Position position(String clientId) {
        return new Position("P1", clientId, "AAPL", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");
    }

    private static Client client(String id) {
        return new Client(id, "Jane Doe", "EQUILIBRE", "EUR", LocalDate.of(2020, 1, 1), "advisor-1");
    }
}
