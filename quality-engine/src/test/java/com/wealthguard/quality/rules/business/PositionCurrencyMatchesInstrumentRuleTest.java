package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Instrument;
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

class PositionCurrencyMatchesInstrumentRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "POS_CURRENCY_MATCHES_INSTRUMENT", Severity.AVERTISSEMENT);

    private final PositionCurrencyMatchesInstrumentRule rule = new PositionCurrencyMatchesInstrumentRule(DEFINITION);

    @Test
    void isNotApplicableWithoutAnInstrumentReferenceTable() {
        ValidationContext context = context(position("USD"), List.of());

        assertThat(rule.isApplicable(context)).isFalse();
    }

    @Test
    void reportsACurrencyMismatch() {
        ValidationContext context = context(position("CHF"), List.of(instrument("USD")));

        assertThat(rule.evaluate(context)).hasSize(1);
    }

    @Test
    void reportsNoAnomalyWhenCurrenciesMatchCaseInsensitively() {
        ValidationContext context = context(position("usd"), List.of(instrument("USD")));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsNoAnomalyForAnUnresolvableInstrumentDeferredToAnotherRule() {
        ValidationContext context = context(position("USD"), List.of(instrument2("EUR", "OTHER_TICKER")));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsNoAnomalyWhenTheInstrumentHasNoCurrencyOnFile() {
        Instrument noCurrency = new Instrument("AAPL", "Apple Inc.", "EQUITY", "ACTIONS", null, "NASDAQ");

        assertThat(rule.evaluate(context(position("USD"), List.of(noCurrency)))).isEmpty();
    }

    @Test
    void skipsAPositionMissingCurrencyOrTicker() {
        Position noCurrency = new Position("P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), null);
        Position blankCurrency = new Position("P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "  ");
        Position noTicker = new Position("P1", "C1", null, BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), "USD");
        List<Instrument> instruments = List.of(instrument("USD"));

        assertThat(rule.evaluate(context(noCurrency, instruments))).isEmpty();
        assertThat(rule.evaluate(context(blankCurrency, instruments))).isEmpty();
        assertThat(rule.evaluate(context(noTicker, instruments))).isEmpty();
    }

    private static Position position(String currency) {
        return new Position("P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, LocalDate.of(2024, 1, 1), currency);
    }

    private static Instrument instrument(String currency) {
        return new Instrument("AAPL", "Apple Inc.", "EQUITY", "ACTIONS", currency, "NASDAQ");
    }

    private static Instrument instrument2(String currency, String ticker) {
        return new Instrument(ticker, "Other", "EQUITY", "ACTIONS", currency, "NASDAQ");
    }

    private static ValidationContext context(Position position, List<Instrument> instruments) {
        return new ValidationContext(List.of(position), List.of(), instruments, List.of(), LocalDate.of(2024, 1, 1));
    }
}
