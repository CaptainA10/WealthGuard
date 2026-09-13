package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.TargetAllocation;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractQualityRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Business coherence: a client's target allocation weights must sum to 100%.
 *
 * <p>A property of the whole client, not of one row -- hence this rule works off
 * {@link ValidationContext#allocationsByClientId()} rather than extending
 * {@code AbstractPositionRule}'s per-record template. {@code tolerancePct} exists
 * because advisors maintain these weights by hand in a spreadsheet; a rounding
 * remainder of a few tenths of a point is normal and must not drown out a real
 * 7-point drift.
 *
 * <p>Complexity: O(A) -- one pass building the per-client sums (already indexed by
 * the context), one pass over the resulting per-client map.
 */
public class AllocationSumEquals100Rule extends AbstractQualityRule {

    private static final BigDecimal TARGET = BigDecimal.valueOf(100);

    private final BigDecimal tolerancePct;

    public AllocationSumEquals100Rule(RuleDefinition definition) {
        super(definition);
        this.tolerancePct = parameters().requireDecimal("tolerancePct");
    }

    @Override
    public boolean isApplicable(ValidationContext context) {
        return !context.targetAllocations().isEmpty();
    }

    @Override
    public List<Anomaly> evaluate(ValidationContext context) {
        List<Anomaly> found = new ArrayList<>();
        context.allocationsByClientId().forEach((clientId, allocations) -> {
            BigDecimal sum = allocations.stream()
                    .map(TargetAllocation::targetWeightPct)
                    .filter(Objects::nonNull)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
            BigDecimal deviation = sum.subtract(TARGET).abs();
            if (deviation.compareTo(tolerancePct) <= 0) {
                return;
            }
            found.add(anomaly(
                    "target_allocations",
                    "client_id=" + clientId,
                    "targetWeightPct",
                    sum,
                    "Somme des allocations cibles du client egale a " + sum.toPlainString()
                            + "%, attendue a 100% (tolerance +/- " + tolerancePct.toPlainString() + ").",
                    "Cible d'allocation inexploitable : tout ecart cible/reel calcule pour ce "
                            + "client est biaise d'autant.",
                    "Rapprocher le classeur d'allocation de l'avisor pour ce client : une classe "
                            + "d'actif a probablement ete ajoutee, retiree ou modifiee sans reequilibrer "
                            + "les autres lignes."));
        });
        return found;
    }
}
