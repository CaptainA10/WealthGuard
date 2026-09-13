package com.wealthguard.quality.rules;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalStateException;

/**
 * Direct tests of the fail-fast accessor every rule's constructor relies on --
 * the error paths here are exercised by no rule in the happy path, so they need
 * their own coverage.
 */
class RuleParametersTest {

    @Test
    void hasReflectsPresenceOfANonEmptyValue() {
        RuleParameters params = RuleParameters.of(Map.of("threshold", "40"), "TEST_RULE");

        assertThat(params.has("threshold")).isTrue();
        assertThat(params.has("missing")).isFalse();
    }

    @Test
    void emptyHasNoParameters() {
        assertThat(RuleParameters.empty().has("anything")).isFalse();
        assertThat(RuleParameters.empty().asMap()).isEmpty();
    }

    @Test
    void requireDecimalParsesAValidValue() {
        RuleParameters params = RuleParameters.of(Map.of("minExclusive", "0.5"), "TEST_RULE");

        assertThat(params.requireDecimal("minExclusive")).isEqualByComparingTo(new BigDecimal("0.5"));
    }

    @Test
    void requireDecimalFailsFastOnAMalformedValue() {
        RuleParameters params = RuleParameters.of(Map.of("minExclusive", "not-a-number"), "TEST_RULE");

        assertThatIllegalStateException()
                .isThrownBy(() -> params.requireDecimal("minExclusive"))
                .withMessageContaining("TEST_RULE")
                .withMessageContaining("minExclusive");
    }

    @Test
    void requireIntParsesAValidValue() {
        RuleParameters params = RuleParameters.of(Map.of("toleranceDays", "3"), "TEST_RULE");

        assertThat(params.requireInt("toleranceDays")).isEqualTo(3);
    }

    @Test
    void requireIntFailsFastOnAMalformedValue() {
        RuleParameters params = RuleParameters.of(Map.of("toleranceDays", "3.5"), "TEST_RULE");

        assertThatIllegalStateException()
                .isThrownBy(() -> params.requireInt("toleranceDays"))
                .withMessageContaining("toleranceDays");
    }

    @Test
    void requireFailsFastWhenTheParameterIsMissingEntirely() {
        RuleParameters params = RuleParameters.of(Map.of(), "TEST_RULE");

        assertThatIllegalStateException()
                .isThrownBy(() -> params.requireInt("toleranceDays"))
                .withMessageContaining("missing mandatory parameter");
    }

    @Test
    void requireStringSetParsesAndTrimsACommaSeparatedList() {
        RuleParameters params = RuleParameters.of(Map.of("allowedProfiles", "PRUDENT, EQUILIBRE ,DYNAMIQUE"), "TEST_RULE");

        assertThat(params.requireStringSet("allowedProfiles"))
                .containsExactly("PRUDENT", "EQUILIBRE", "DYNAMIQUE");
    }

    @Test
    void requireStringSetFailsFastWhenOnlySeparatorsAreSupplied() {
        RuleParameters params = RuleParameters.of(Map.of("fields", " , , "), "TEST_RULE");

        assertThatIllegalStateException()
                .isThrownBy(() -> params.requireStringSet("fields"))
                .withMessageContaining("must list at least one value");
    }

    @Test
    void requireStringListPreservesTheSetContract() {
        RuleParameters params = RuleParameters.of(Map.of("fields", "positionId,clientId"), "TEST_RULE");

        assertThat(params.requireStringList("fields")).containsExactly("positionId", "clientId");
    }

    @Test
    void ofSanitisesKeysAndValuesAndIgnoresNullEntries() {
        Map<String, String> raw = new java.util.HashMap<>();
        raw.put(" spaced ", " value ");
        raw.put(null, "ignored-key");
        raw.put("ignored-value", null);
        RuleParameters params = RuleParameters.of(raw, "TEST_RULE");

        assertThat(params.asMap()).containsExactly(Map.entry("spaced", "value"));
    }

    @Test
    void ofToleratesANullMap() {
        assertThat(RuleParameters.of(null, "TEST_RULE").asMap()).isEmpty();
    }
}
