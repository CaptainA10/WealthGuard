package com.wealthguard.quality.rules.business;

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

class PurchaseDateNotInFutureRuleTest {

    private static final LocalDate EVALUATION_DATE = LocalDate.of(2024, 6, 15);

    @Test
    void reportsAPurchaseDateBeyondTolerance() {
        PurchaseDateNotInFutureRule rule = ruleWithTolerance(0);
        Position future = position(EVALUATION_DATE.plusDays(3));

        assertThat(rule.evaluate(context(future))).hasSize(1);
    }

    @Test
    void reportsNoAnomalyExactlyAtTheToleranceLimit() {
        PurchaseDateNotInFutureRule rule = ruleWithTolerance(1);
        Position atLimit = position(EVALUATION_DATE.plusDays(1));

        assertThat(rule.evaluate(context(atLimit))).isEmpty();
    }

    @Test
    void reportsAnAnomalyOneDayBeyondTheToleranceLimit() {
        PurchaseDateNotInFutureRule rule = ruleWithTolerance(1);
        Position pastLimit = position(EVALUATION_DATE.plusDays(2));

        assertThat(rule.evaluate(context(pastLimit))).hasSize(1);
    }

    @Test
    void reportsNoAnomalyForAPastPurchaseDate() {
        PurchaseDateNotInFutureRule rule = ruleWithTolerance(0);
        Position past = position(EVALUATION_DATE.minusDays(30));

        assertThat(rule.evaluate(context(past))).isEmpty();
    }

    @Test
    void skipsANullPurchaseDate() {
        PurchaseDateNotInFutureRule rule = ruleWithTolerance(0);
        Position noDate = new Position("P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, null, "USD");

        assertThat(rule.evaluate(context(noDate))).isEmpty();
    }

    @Test
    void rejectsANegativeToleranceAtConstruction() {
        RuleDefinition definition = RuleDefinitions.of(
                "POS_PURCHASE_DATE_NOT_FUTURE", Severity.BLOQUANT, Map.of("toleranceDays", "-1"));

        assertThatIllegalStateException(definition);
    }

    private static void assertThatIllegalStateException(RuleDefinition definition) {
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> new PurchaseDateNotInFutureRule(definition))
                .isInstanceOf(IllegalStateException.class);
    }

    private static PurchaseDateNotInFutureRule ruleWithTolerance(int toleranceDays) {
        RuleDefinition definition = RuleDefinitions.of(
                "POS_PURCHASE_DATE_NOT_FUTURE", Severity.BLOQUANT,
                Map.of("toleranceDays", String.valueOf(toleranceDays)));
        return new PurchaseDateNotInFutureRule(definition);
    }

    private static Position position(LocalDate purchaseDate) {
        return new Position("P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, purchaseDate, "USD");
    }

    private static ValidationContext context(Position position) {
        return new ValidationContext(List.of(position), List.of(), List.of(), List.of(), EVALUATION_DATE);
    }
}
