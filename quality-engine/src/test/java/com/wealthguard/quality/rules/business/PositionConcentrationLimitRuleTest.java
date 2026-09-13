package com.wealthguard.quality.rules.business;

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
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class PositionConcentrationLimitRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "POS_CONCENTRATION_LIMIT", Severity.AVERTISSEMENT, Map.of("maxWeightPct", "40"));

    private final PositionConcentrationLimitRule rule = new PositionConcentrationLimitRule(DEFINITION);

    @Test
    void reportsALineAboveTheConcentrationLimit() {
        // Client C1: 900 vs 100 cost basis -> the first line is 90% of the portfolio.
        Position dominant = position("C1", "AAPL", "9", "100");
        Position small = position("C1", "MSFT", "1", "100");
        ValidationContext context = context(List.of(client("C1")), dominant, small);

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).recordKey()).isEqualTo(dominant.recordKey());
    }

    @Test
    void reportsNoAnomalyWhenThePortfolioIsBalanced() {
        // Three equal lines -> each is ~33.33% of the portfolio, under the 40% limit.
        Position first = position("C1", "AAPL", "1", "100");
        Position second = position("C1", "MSFT", "1", "100");
        Position third = position("C1", "GOOG", "1", "100");

        assertThat(rule.evaluate(context(List.of(client("C1")), first, second, third))).isEmpty();
    }

    @Test
    void excludesLinesWithoutAUsableCostBasisFromTheDenominator() {
        Position dominant = position("C1", "AAPL", "9", "100");
        Position unusable = new Position("P2", "C1", "MSFT", BigDecimal.ZERO, BigDecimal.TEN, LocalDate.of(2024, 1, 1), "USD");

        List<Anomaly> anomalies = rule.evaluate(context(List.of(client("C1")), dominant, unusable));

        // Denominator is only the dominant line's own cost basis -> 100%, still a breach,
        // but the unusable line itself must not appear in the report.
        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).recordKey()).isEqualTo(dominant.recordKey());
    }

    @Test
    void isolatesConcentrationPerClient() {
        Position clientA = position("A", "AAPL", "10", "100");
        Position clientB = position("B", "MSFT", "10", "100");

        // Each client has a single line -> 100% of their own portfolio, both breach independently.
        assertThat(rule.evaluate(context(List.of(client("A"), client("B")), clientA, clientB))).hasSize(2);
    }

    @Test
    void skipsPositionsWhoseClientIdDoesNotResolve() {
        // Two orphan positions sharing one bad client id: with only two lines,
        // whichever is larger trivially exceeds 40% of their combined total --
        // a real bug this test pins down (see PositionConcentrationLimitRule's
        // javadoc): an unresolved client is not a portfolio to score.
        Position orphanA = position("CLI-9999", "AAPL", "6", "100");
        Position orphanB = position("CLI-9999", "MSFT", "4", "100");

        assertThat(rule.evaluate(context(List.of(client("C1")), orphanA, orphanB))).isEmpty();
    }

    @Test
    void isNotApplicableWithoutAnyClientReferenceAtAll() {
        Position dominant = position("C1", "AAPL", "9", "100");
        ValidationContext context = context(List.of(), dominant);

        assertThat(rule.isApplicable(context)).isFalse();
    }

    @Test
    void isApplicableAssoonAsAClientReferenceIsPresent() {
        ValidationContext context = context(List.of(client("C1")));

        assertThat(rule.isApplicable(context)).isTrue();
    }

    private static Position position(String clientId, String ticker, String quantity, String price) {
        return new Position(
                clientId + "-" + ticker, clientId, ticker,
                new BigDecimal(quantity), new BigDecimal(price), LocalDate.of(2024, 1, 1), "USD");
    }

    private static Client client(String clientId) {
        return new Client(clientId, "Jane Doe", "EQUILIBRE", "EUR", LocalDate.of(2020, 1, 1), "advisor-1");
    }

    private static ValidationContext context(List<Client> clients, Position... positions) {
        return new ValidationContext(List.of(positions), clients, List.of(), List.of(), LocalDate.of(2024, 1, 1));
    }
}
