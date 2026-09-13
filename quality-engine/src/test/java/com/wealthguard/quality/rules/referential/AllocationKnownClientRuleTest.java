package com.wealthguard.quality.rules.referential;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Client;
import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;
import com.wealthguard.quality.domain.TargetAllocation;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.RuleDefinition;
import com.wealthguard.quality.support.RuleDefinitions;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class AllocationKnownClientRuleTest {

    private static final RuleDefinition DEFINITION = RuleDefinitions.of(
            "ALLOC_KNOWN_CLIENT", RuleCategory.REFERENTIEL, Severity.BLOQUANT, Map.of());

    private final AllocationKnownClientRule rule = new AllocationKnownClientRule(DEFINITION);

    @Test
    void isNotApplicableWithoutClientReferenceOrAllocations() {
        ValidationContext noClients = new ValidationContext(
                List.of(), List.of(), List.of(),
                List.of(new TargetAllocation("C1", "ACTIONS", BigDecimal.TEN)),
                LocalDate.of(2024, 1, 1));
        assertThat(rule.isApplicable(noClients)).isFalse();

        ValidationContext noAllocations = new ValidationContext(
                List.of(), List.of(client("C1")), List.of(), List.of(), LocalDate.of(2024, 1, 1));
        assertThat(rule.isApplicable(noAllocations)).isFalse();
    }

    @Test
    void reportsAnOrphanAllocationClientReference() {
        ValidationContext context = new ValidationContext(
                List.of(), List.of(client("C1")), List.of(),
                List.of(new TargetAllocation("UNKNOWN", "ACTIONS", BigDecimal.TEN)),
                LocalDate.of(2024, 1, 1));

        List<Anomaly> anomalies = rule.evaluate(context);

        assertThat(anomalies).hasSize(1);
        assertThat(anomalies.get(0).dataset()).isEqualTo("target_allocations");
    }

    @Test
    void reportsNoAnomalyWhenTheAllocationClientResolves() {
        ValidationContext context = new ValidationContext(
                List.of(), List.of(client("C1")), List.of(),
                List.of(new TargetAllocation("C1", "ACTIONS", BigDecimal.TEN)),
                LocalDate.of(2024, 1, 1));

        assertThat(rule.evaluate(context)).isEmpty();
    }

    @Test
    void isApplicableWhenBothClientReferenceAndAllocationsArePresent() {
        ValidationContext context = new ValidationContext(
                List.of(), List.of(client("C1")), List.of(),
                List.of(new TargetAllocation("C1", "ACTIONS", BigDecimal.TEN)),
                LocalDate.of(2024, 1, 1));

        assertThat(rule.isApplicable(context)).isTrue();
    }

    @Test
    void skipsANullOrBlankAllocationClientIdBecauseItIsAnotherRulesFinding() {
        ValidationContext nullClientId = new ValidationContext(
                List.of(), List.of(client("C1")), List.of(),
                List.of(new TargetAllocation(null, "ACTIONS", BigDecimal.TEN)),
                LocalDate.of(2024, 1, 1));
        ValidationContext blankClientId = new ValidationContext(
                List.of(), List.of(client("C1")), List.of(),
                List.of(new TargetAllocation("  ", "ACTIONS", BigDecimal.TEN)),
                LocalDate.of(2024, 1, 1));

        assertThat(rule.evaluate(nullClientId)).isEmpty();
        assertThat(rule.evaluate(blankClientId)).isEmpty();
    }

    private static Client client(String id) {
        return new Client(id, "Jane Doe", "EQUILIBRE", "EUR", LocalDate.of(2020, 1, 1), "advisor-1");
    }
}
