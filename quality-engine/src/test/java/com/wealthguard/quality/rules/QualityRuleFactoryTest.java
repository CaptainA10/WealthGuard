package com.wealthguard.quality.rules;

import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link RuleIds}' javadoc describes it as a contract shared by this factory, the
 * YAML configuration and the Python seed's anomaly catalogue. This test enforces
 * the Java side of that contract by reflection: every constant declared in
 * {@link RuleIds} must be buildable, and the factory must not silently know about
 * an id that {@link RuleIds} does not declare.
 */
class QualityRuleFactoryTest {

    private final QualityRuleFactory factory = new QualityRuleFactory();

    @Test
    void knowsExactlyTheIdsDeclaredInRuleIds() throws IllegalAccessException {
        Set<String> declared = new HashSet<>();
        for (Field field : RuleIds.class.getDeclaredFields()) {
            if (Modifier.isStatic(field.getModifiers()) && field.getType() == String.class) {
                declared.add((String) field.get(null));
            }
        }

        assertThat(factory.knownRuleIds()).containsExactlyInAnyOrderElementsOf(declared);
    }

    @Test
    void buildsARuleForEveryKnownId() {
        for (String id : factory.knownRuleIds()) {
            RuleDefinition definition = definitionFor(id);
            QualityRule rule = factory.create(definition);

            assertThat(rule).isNotNull();
            assertThat(rule.id()).isEqualTo(id);
        }
    }

    @Test
    void rejectsAnUnknownRuleIdWithTheListOfKnownOnes() {
        RuleDefinition unknown = new RuleDefinition(
                "NOT_A_REAL_RULE", "label", RuleCategory.COHERENCE_METIER, Severity.INFO, "desc", RuleParameters.empty());

        assertThatThrownBy(() -> factory.create(unknown))
                .isInstanceOf(UnknownRuleException.class)
                .hasMessageContaining("NOT_A_REAL_RULE");
    }

    /** Every parameterised rule's mandatory parameters, so every known id can be constructed. */
    private static RuleDefinition definitionFor(String id) {
        Map<String, String> parameters = switch (id) {
            case "POS_REQUIRED_FIELDS" -> Map.of("fields", "positionId,clientId");
            case "POS_POSITIVE_QUANTITY", "POS_POSITIVE_PURCHASE_PRICE" -> Map.of("minExclusive", "0");
            case "POS_PURCHASE_DATE_NOT_FUTURE", "POS_PURCHASE_AFTER_ONBOARDING" -> Map.of("toleranceDays", "0");
            case "POS_CONCENTRATION_LIMIT" -> Map.of("maxWeightPct", "40");
            case "POS_QUANTITY_PRECISION" -> Map.of("maxDecimals", "4");
            case "CLI_KNOWN_RISK_PROFILE" -> Map.of("allowedProfiles", "PRUDENT,EQUILIBRE");
            case "ALLOC_SUM_EQUALS_100" -> Map.of("tolerancePct", "0.5");
            case "ALLOC_WEIGHT_IN_RANGE" -> Map.of("minInclusive", "0", "maxInclusive", "100");
            default -> Map.of();
        };
        return new RuleDefinition(id, id, RuleCategory.COHERENCE_METIER, Severity.INFO, "desc",
                RuleParameters.of(parameters, id));
    }
}
