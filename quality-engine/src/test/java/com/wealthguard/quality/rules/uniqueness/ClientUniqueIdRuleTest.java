package com.wealthguard.quality.rules.uniqueness;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Client;
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

class ClientUniqueIdRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of("CLI_UNIQUE_ID", Severity.BLOQUANT);

    private final ClientUniqueIdRule rule = new ClientUniqueIdRule(DEFINITION);

    @Test
    void reportsNoAnomalyWhenAllClientIdsAreUnique() {
        ValidationContext context = new ValidationContext(
                List.of(),
                List.of(client("C1"), client("C2")),
                List.of(), List.of(), LocalDate.of(2024, 1, 1));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsTheFanOutImpactOnAffectedPositions() {
        Position position = new Position(
                "P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");
        ValidationContext context = new ValidationContext(
                List.of(position),
                List.of(client("C1"), client("C1")),
                List.of(), List.of(), LocalDate.of(2024, 1, 1));

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).estimatedImpact()).contains("1 position(s)");
    }

    private static Client client(String id) {
        return new Client(id, "Jane Doe", "EQUILIBRE", "EUR", LocalDate.of(2020, 1, 1), "advisor-1");
    }
}
