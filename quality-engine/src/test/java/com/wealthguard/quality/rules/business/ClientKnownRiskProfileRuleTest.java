package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Client;
import com.wealthguard.quality.domain.Severity;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.RuleDefinition;
import com.wealthguard.quality.support.RuleDefinitions;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class ClientKnownRiskProfileRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "CLI_KNOWN_RISK_PROFILE", Severity.AVERTISSEMENT,
            Map.of("allowedProfiles", "PRUDENT,EQUILIBRE,DYNAMIQUE,OFFENSIF"));

    private final ClientKnownRiskProfileRule rule = new ClientKnownRiskProfileRule(DEFINITION);

    @Test
    void reportsNoAnomalyForAKnownProfile() {
        assertThat(rule.evaluate(context(client("EQUILIBRE")))).isEmpty();
    }

    @Test
    void reportsAProfileOutsideTheNomenclature() {
        assertThat(rule.evaluate(context(client("AGRESSIF")))).hasSize(1);
    }

    @Test
    void ignoresABlankProfileOutOfScope() {
        assertThat(rule.evaluate(context(client(null)))).isEmpty();
        assertThat(rule.evaluate(context(client("  ")))).isEmpty();
    }

    private static Client client(String riskProfile) {
        return new Client("C1", "Jane Doe", riskProfile, "EUR", LocalDate.of(2020, 1, 1), "advisor-1");
    }

    private static ValidationContext context(Client client) {
        return new ValidationContext(List.of(), List.of(client), List.of(), List.of(), LocalDate.of(2024, 1, 1));
    }
}
