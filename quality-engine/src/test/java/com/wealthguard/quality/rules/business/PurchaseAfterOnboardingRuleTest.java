package com.wealthguard.quality.rules.business;

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

class PurchaseAfterOnboardingRuleTest {

    private static final LocalDate ONBOARDING = LocalDate.of(2022, 1, 1);

    private final PurchaseAfterOnboardingRule rule = ruleWithTolerance(0);

    @Test
    void isNotApplicableWithoutAClientReferenceTable() {
        ValidationContext context = context(position(ONBOARDING.minusDays(10)), List.of());

        assertThat(rule.isApplicable(context)).isFalse();
    }

    @Test
    void reportsAPurchaseBeforeOnboarding() {
        ValidationContext context = context(position(ONBOARDING.minusDays(10)), List.of(client()));

        assertThat(rule.evaluate(context)).hasSize(1);
    }

    @Test
    void reportsNoAnomalyOnOrAfterOnboarding() {
        ValidationContext context = context(position(ONBOARDING), List.of(client()));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsNoAnomalyWhenTheClientDoesNotResolve() {
        ValidationContext context = context(position(ONBOARDING.minusDays(10)), List.of());
        // Force isApplicable to pass through evaluate() directly for this edge case.
        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void reportsNoAnomalyWhenTheClientHasNoOnboardingDate() {
        Client noOnboarding = new Client("C1", "Jane Doe", "EQUILIBRE", "EUR", null, "advisor-1");
        ValidationContext context = context(position(ONBOARDING.minusDays(10)), List.of(noOnboarding));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void skipsAPositionMissingThePurchaseDateOrTheClientId() {
        Position noPurchaseDate = new Position("P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, null, "USD");
        Position noClientId = new Position("P1", null, "AAPL", BigDecimal.TEN, BigDecimal.ONE, ONBOARDING, "USD");
        Position blankClientId = new Position("P1", "  ", "AAPL", BigDecimal.TEN, BigDecimal.ONE, ONBOARDING, "USD");

        assertThat(rule.evaluate(context(noPurchaseDate, List.of(client())))).isEmpty();
        assertThat(rule.evaluate(context(noClientId, List.of(client())))).isEmpty();
        assertThat(rule.evaluate(context(blankClientId, List.of(client())))).isEmpty();
    }

    @Test
    void rejectsANegativeToleranceAtConstruction() {
        RuleDefinition definition = RuleDefinitions.of(
                "POS_PURCHASE_AFTER_ONBOARDING", Severity.AVERTISSEMENT, Map.of("toleranceDays", "-1"));

        org.assertj.core.api.Assertions.assertThatIllegalStateException()
                .isThrownBy(() -> new PurchaseAfterOnboardingRule(definition));
    }

    private static PurchaseAfterOnboardingRule ruleWithTolerance(int toleranceDays) {
        RuleDefinition definition = RuleDefinitions.of(
                "POS_PURCHASE_AFTER_ONBOARDING", Severity.AVERTISSEMENT,
                Map.of("toleranceDays", String.valueOf(toleranceDays)));
        return new PurchaseAfterOnboardingRule(definition);
    }

    private static Position position(LocalDate purchaseDate) {
        return new Position("P1", "C1", "AAPL", BigDecimal.TEN, BigDecimal.ONE, purchaseDate, "USD");
    }

    private static Client client() {
        return new Client("C1", "Jane Doe", "EQUILIBRE", "EUR", ONBOARDING, "advisor-1");
    }

    private static ValidationContext context(Position position, List<Client> clients) {
        return new ValidationContext(List.of(position), clients, List.of(), List.of(), LocalDate.of(2024, 1, 1));
    }
}
