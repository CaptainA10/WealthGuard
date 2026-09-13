package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractQualityRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

/**
 * Business coherence: no single line should dominate a client's portfolio beyond
 * the configured limit, expressed as a share of the portfolio's total cost basis.
 *
 * <p>Cost basis, not market value, is the denominator: market value would need the
 * pipeline's valuation step to have already run, which the quality engine must not
 * assume. Cost basis is available on the raw position and is exactly what the
 * seed anomaly ("une ligne depasse 40% du prix de revient du portefeuille")
 * describes.
 *
 * <p>Lines without a usable cost basis (missing or non-positive quantity/price --
 * another rule's finding) are excluded from both the numerator and the
 * denominator: including them would either crash the division or silently dilute
 * every other line's computed share.
 *
 * <p><strong>An unresolved client is not a portfolio.</strong> {@link
 * ValidationContext#positionsByClientId()} groups strictly by the raw {@code
 * clientId} string, with no idea whether it resolves to a real client -- so a
 * batch of orphan positions that all happen to share one bad id (the common
 * case: a stale placeholder, or several rows corrupted the same way) would
 * otherwise be scored as "one client's portfolio" and can easily trip this
 * rule by accident. Those positions already get their own finding from
 * {@code POS_KNOWN_CLIENT}; scoring them here too would be noise, not signal,
 * so a {@code clientId} that does not resolve is skipped entirely, mirroring
 * how {@link PurchaseAfterOnboardingRule} treats an unresolved client.
 *
 * <p>Complexity: O(P) -- one pass per client to sum the denominator, one pass to
 * evaluate each line, both driven by the {@link ValidationContext#positionsByClientId()}
 * index built once at context construction.
 */
public class PositionConcentrationLimitRule extends AbstractQualityRule {

    private final BigDecimal maxWeightPct;

    public PositionConcentrationLimitRule(RuleDefinition definition) {
        super(definition);
        this.maxWeightPct = parameters().requireDecimal("maxWeightPct");
    }

    /** Without any client reference at all, a real client cannot be told apart
     * from a typo, so this control cannot say anything meaningful. */
    @Override
    public boolean isApplicable(ValidationContext context) {
        return context.hasClientReference();
    }

    @Override
    public List<Anomaly> evaluate(ValidationContext context) {
        List<Anomaly> found = new ArrayList<>();
        context.positionsByClientId().forEach((clientId, positions) -> {
            if (!context.hasClient(clientId)) {
                return;
            }
            BigDecimal totalCostBasis = positions.stream()
                    .filter(Position::hasUsableCostBasis)
                    .map(Position::costBasis)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
            if (totalCostBasis.signum() <= 0) {
                return;
            }
            for (Position position : positions) {
                if (!position.hasUsableCostBasis()) {
                    continue;
                }
                BigDecimal weightPct = position.costBasis()
                        .multiply(BigDecimal.valueOf(100))
                        .divide(totalCostBasis, 4, RoundingMode.HALF_UP);
                if (weightPct.compareTo(maxWeightPct) <= 0) {
                    continue;
                }
                found.add(anomaly(
                        "positions",
                        position.recordKey(),
                        "quantity",
                        weightPct.toPlainString() + "%",
                        "Ligne representant " + weightPct.toPlainString()
                                + "% du prix de revient du portefeuille du client " + clientId
                                + ", au-dela du seuil de " + maxWeightPct.toPlainString() + "%.",
                        "Risque de concentration contraire a la politique d'investissement : le "
                                + "portefeuille n'est plus diversifie comme attendu, alerte conformite.",
                        "Verifier aupres du conseiller si la concentration est assumee (conviction "
                                + "forte, apport en titres) ou si elle resulte d'une erreur de quantite "
                                + "ou de prix a corriger."));
            }
        });
        return found;
    }
}
