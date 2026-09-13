package com.wealthguard.quality.service;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Client;
import com.wealthguard.quality.domain.Instrument;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.TargetAllocation;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.domain.ValidationReport;
import com.wealthguard.quality.rules.QualityRule;
import com.wealthguard.quality.rules.RuleDefinition;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Orchestrates a validation run: builds the {@link ValidationContext}, runs every
 * configured rule over it, and assembles the {@link ValidationReport}.
 *
 * <p>This is the layer the cahier des charges (§7) asks to keep separate from the
 * HTTP concern (the controller) and from any one control's logic (the rules
 * themselves) -- so that a batch can also be validated from a test or a future
 * CLI without going through Spring MVC.
 *
 * <p>A rule that declines to run ({@link QualityRule#isApplicable(ValidationContext)}
 * returns {@code false}) is left out of {@link ValidationReport#executedRules()}
 * entirely, which is what lets a report distinguish "this control passed" from
 * "this control did not run" -- see {@link QualityRule#isApplicable} for why that
 * distinction matters.
 */
@Service
public class ValidationService {

    private final List<QualityRule> rules;

    public ValidationService(List<QualityRule> rules) {
        this.rules = List.copyOf(rules);
    }

    public ValidationReport validate(
            List<Position> positions,
            List<Client> clients,
            List<Instrument> instruments,
            List<TargetAllocation> targetAllocations,
            LocalDate evaluationDate) {

        ValidationContext context = new ValidationContext(
                positions, clients, instruments, targetAllocations, evaluationDate);

        long startNanos = System.nanoTime();
        List<String> executedRules = new ArrayList<>();
        List<Anomaly> anomalies = new ArrayList<>();
        for (QualityRule rule : rules) {
            if (!rule.isApplicable(context)) {
                continue;
            }
            executedRules.add(rule.id());
            anomalies.addAll(rule.evaluate(context));
        }
        long durationMillis = (System.nanoTime() - startNanos) / 1_000_000;

        return ValidationReport.of(
                UUID.randomUUID().toString(),
                Instant.now(),
                context,
                executedRules,
                anomalies,
                durationMillis);
    }

    /** The configured rules, for a diagnostics/discovery endpoint. */
    public List<RuleDefinition> ruleDefinitions() {
        return rules.stream().map(QualityRule::definition).toList();
    }
}
