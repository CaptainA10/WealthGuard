package com.wealthguard.quality.rules;

import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatNullPointerException;

/**
 * The compact constructor is what normalises a rule's configured identity
 * (cahier des charges §2.2: rules are configured, not hardcoded) -- these tests
 * cover every branch of that normalisation.
 */
class RuleDefinitionTest {

    @Test
    void fallsBackToTheIdWhenNoLabelIsSupplied() {
        RuleDefinition definition = new RuleDefinition(
                "POS_UNIQUE_ID", null, RuleCategory.UNICITE, Severity.BLOQUANT, "desc", RuleParameters.empty());

        assertThat(definition.label()).isEqualTo("POS_UNIQUE_ID");
    }

    @Test
    void fallsBackToTheIdWhenTheLabelIsBlank() {
        RuleDefinition definition = new RuleDefinition(
                "POS_UNIQUE_ID", "   ", RuleCategory.UNICITE, Severity.BLOQUANT, "desc", RuleParameters.empty());

        assertThat(definition.label()).isEqualTo("POS_UNIQUE_ID");
    }

    @Test
    void keepsAnExplicitNonBlankLabel() {
        RuleDefinition definition = new RuleDefinition(
                "POS_UNIQUE_ID", "Unicite de la position", RuleCategory.UNICITE, Severity.BLOQUANT,
                "desc", RuleParameters.empty());

        assertThat(definition.label()).isEqualTo("Unicite de la position");
    }

    @Test
    void defaultsToEmptyParametersWhenNoneAreSupplied() {
        RuleDefinition definition = new RuleDefinition(
                "POS_UNIQUE_ID", "label", RuleCategory.UNICITE, Severity.BLOQUANT, "desc", null);

        assertThat(definition.parameters().asMap()).isEmpty();
    }

    @Test
    void defaultsToAnEmptyDescriptionWhenNoneIsSupplied() {
        RuleDefinition definition = new RuleDefinition(
                "POS_UNIQUE_ID", "label", RuleCategory.UNICITE, Severity.BLOQUANT, null, RuleParameters.empty());

        assertThat(definition.description()).isEmpty();
    }

    @Test
    void rejectsANullId() {
        assertThatNullPointerException().isThrownBy(() -> new RuleDefinition(
                null, "label", RuleCategory.UNICITE, Severity.BLOQUANT, "desc", RuleParameters.empty()));
    }

    @Test
    void rejectsANullCategory() {
        assertThatNullPointerException().isThrownBy(() -> new RuleDefinition(
                "ID", "label", null, Severity.BLOQUANT, "desc", RuleParameters.empty()));
    }

    @Test
    void rejectsANullSeverity() {
        assertThatNullPointerException().isThrownBy(() -> new RuleDefinition(
                "ID", "label", RuleCategory.UNICITE, null, "desc", RuleParameters.empty()));
    }
}
