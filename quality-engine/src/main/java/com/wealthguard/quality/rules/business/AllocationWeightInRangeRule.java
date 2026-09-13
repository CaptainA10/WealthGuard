package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.TargetAllocation;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractQualityRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

/**
 * Business coherence: a single target-allocation weight must sit within
 * {@code [minInclusive, maxInclusive]} (0 to 100 by default).
 *
 * <p>Deliberately independent of {@link AllocationSumEquals100Rule}: a negative
 * weight offset by an oversized positive one can still sum to exactly 100%, which
 * is precisely the seed dataset's {@code ALLOCATION_WEIGHT_OUT_OF_RANGE} case. A
 * sum-only check would miss it, so this is a per-row control, not an aggregate.
 *
 * <p>Complexity: O(A).
 */
public class AllocationWeightInRangeRule extends AbstractQualityRule {

    private final BigDecimal minInclusive;
    private final BigDecimal maxInclusive;

    public AllocationWeightInRangeRule(RuleDefinition definition) {
        super(definition);
        this.minInclusive = parameters().requireDecimal("minInclusive");
        this.maxInclusive = parameters().requireDecimal("maxInclusive");
    }

    @Override
    public List<Anomaly> evaluate(ValidationContext context) {
        List<Anomaly> found = new ArrayList<>();
        for (TargetAllocation allocation : context.targetAllocations()) {
            BigDecimal weight = allocation.targetWeightPct();
            if (weight == null) {
                continue;
            }
            if (weight.compareTo(minInclusive) >= 0 && weight.compareTo(maxInclusive) <= 0) {
                continue;
            }
            found.add(anomaly(
                    "target_allocations",
                    allocation.recordKey(),
                    "targetWeightPct",
                    weight,
                    "Poids cible " + weight.toPlainString() + " hors de l'intervalle ["
                            + minInclusive.toPlainString() + ", " + maxInclusive.toPlainString() + "].",
                    "Cible negative ou superieure a 100% impossible : revele une inversion de "
                            + "signe ou une erreur de saisie dans l'outil amont, et fausse tout ecart "
                            + "cible/reel calcule sur cette ligne.",
                    "Verifier le classeur d'allocation cible de l'avisor pour ce client et cette "
                            + "classe d'actif ; corriger le signe ou la valeur avant tout calcul d'ecart."));
        }
        return found;
    }
}
