package com.wealthguard.quality.rules.referential;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Instrument;
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

class PositionKnownInstrumentRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "POS_KNOWN_INSTRUMENT", RuleCategory.REFERENTIEL, Severity.BLOQUANT, Map.of());

    private final PositionKnownInstrumentRule rule = new PositionKnownInstrumentRule(DEFINITION);

    @Test
    void isNotApplicableWithoutAnInstrumentReferenceTable() {
        ValidationContext context = new ValidationContext(
                List.of(position("AAPL")), List.of(), List.of(), List.of(), LocalDate.of(2024, 1, 1));

        assertThat(rule.isApplicable(context)).isFalse();
    }

    @Test
    void reportsAnUnknownTicker() {
        ValidationContext context = new ValidationContext(
                List.of(position("ZZZZ")),
                List.of(), List.of(instrument("AAPL")), List.of(), LocalDate.of(2024, 1, 1));

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).observedValue()).isEqualTo("ZZZZ");
    }

    @Test
    void reportsNoAnomalyWhenTheTickerResolves() {
        ValidationContext context = new ValidationContext(
                List.of(position("AAPL")),
                List.of(), List.of(instrument("AAPL")), List.of(), LocalDate.of(2024, 1, 1));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void skipsANullOrBlankTickerBecauseItIsAnotherRulesFinding() {
        ValidationContext nullTicker = new ValidationContext(
                List.of(position(null)), List.of(), List.of(instrument("AAPL")), List.of(), LocalDate.of(2024, 1, 1));
        ValidationContext blankTicker = new ValidationContext(
                List.of(position("  ")), List.of(), List.of(instrument("AAPL")), List.of(), LocalDate.of(2024, 1, 1));

        assertThat(rule.evaluate(nullTicker)).isEmpty();
        assertThat(rule.evaluate(blankTicker)).isEmpty();
    }

    private static Position position(String ticker) {
        return new Position("P1", "C1", ticker, BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");
    }

    private static Instrument instrument(String ticker) {
        return new Instrument(ticker, "Apple Inc.", "EQUITY", "ACTIONS", "USD", "NASDAQ");
    }
}
