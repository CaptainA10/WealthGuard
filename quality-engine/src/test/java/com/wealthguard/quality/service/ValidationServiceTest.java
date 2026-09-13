package com.wealthguard.quality.service;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.domain.ValidationReport;
import com.wealthguard.quality.rules.QualityRule;
import com.wealthguard.quality.rules.RuleDefinition;
import com.wealthguard.quality.rules.RuleParameters;
import org.junit.jupiter.api.Test;

import java.time.LocalDate;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class ValidationServiceTest {

    private static final LocalDate EVALUATION_DATE = LocalDate.of(2024, 1, 1);

    @Test
    void aggregatesAnomaliesFromEveryApplicableRule() {
        QualityRule blocking = fakeRule("R1", Severity.BLOQUANT, true, 2);
        QualityRule warning = fakeRule("R2", Severity.AVERTISSEMENT, true, 1);
        ValidationService service = new ValidationService(List.of(blocking, warning));

        ValidationReport report = service.validate(List.of(), List.of(), List.of(), List.of(), EVALUATION_DATE);

        assertThat(report.counts().anomalies()).isEqualTo(3);
        assertThat(report.counts().blockingAnomalies()).isEqualTo(2);
        assertThat(report.hasBlockingAnomalies()).isTrue();
        assertThat(report.executedRules()).containsExactlyInAnyOrder("R1", "R2");
    }

    @Test
    void excludesANonApplicableRuleFromExecutedRulesRatherThanReportingItAsPassed() {
        QualityRule skipped = fakeRule("R1", Severity.BLOQUANT, false, 5);
        ValidationService service = new ValidationService(List.of(skipped));

        ValidationReport report = service.validate(List.of(), List.of(), List.of(), List.of(), EVALUATION_DATE);

        assertThat(report.executedRules()).isEmpty();
        assertThat(report.anomalies()).isEmpty();
    }

    @Test
    void sortsAnomaliesWorstSeverityFirst() {
        QualityRule warning = fakeRule("R2", Severity.AVERTISSEMENT, true, 1);
        QualityRule blocking = fakeRule("R1", Severity.BLOQUANT, true, 1);
        // Registered in a "wrong" order on purpose: the report must still sort worst-first.
        ValidationService service = new ValidationService(List.of(warning, blocking));

        ValidationReport report = service.validate(List.of(), List.of(), List.of(), List.of(), EVALUATION_DATE);

        assertThat(report.anomalies()).extracting(Anomaly::severity)
                .containsExactly(Severity.BLOQUANT, Severity.AVERTISSEMENT);
    }

    @Test
    void exposesRuleDefinitionsForDiscovery() {
        QualityRule rule = fakeRule("R1", Severity.INFO, true, 0);
        ValidationService service = new ValidationService(List.of(rule));

        assertThat(service.ruleDefinitions()).extracting(RuleDefinition::id).containsExactly("R1");
    }

    /** A minimal {@link QualityRule} double: reports {@code anomalyCount} identical findings. */
    private static QualityRule fakeRule(String id, Severity severity, boolean applicable, int anomalyCount) {
        RuleDefinition definition = new RuleDefinition(
                id, id, RuleCategory.COHERENCE_METIER, severity, "test", RuleParameters.empty());
        return new QualityRule() {
            @Override
            public RuleDefinition definition() {
                return definition;
            }

            @Override
            public List<Anomaly> evaluate(ValidationContext context) {
                return java.util.stream.IntStream.range(0, anomalyCount)
                        .mapToObj(i -> new Anomaly(
                                id, id, RuleCategory.COHERENCE_METIER, severity,
                                "positions", "position_id=P" + i, null, null, "msg", "impact", "fix"))
                        .toList();
            }

            @Override
            public boolean isApplicable(ValidationContext context) {
                return applicable;
            }
        };
    }
}
