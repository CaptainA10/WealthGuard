package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractPositionRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.math.BigDecimal;
import java.util.Optional;

/**
 * Business coherence: on a long-only mandate a quantity must be strictly greater
 * than the configured floor (0 by default).
 *
 * <p>The threshold is a parameter rather than a literal {@code 0} because a firm
 * that also books short positions would legitimately want this rule disabled or
 * re-floored, and that must not require a code change.
 *
 * <p>Zero is treated as a violation, not a pass: a zero-quantity line is a closed
 * position that the source system forgot to remove, and leaving it in inflates
 * the position count in every report.
 *
 * <p>Complexity: O(P).
 */
public class PositionPositiveQuantityRule extends AbstractPositionRule {

    private final BigDecimal minExclusive;

    public PositionPositiveQuantityRule(RuleDefinition definition) {
        super(definition);
        this.minExclusive = parameters().requireDecimal("minExclusive");
    }

    /** A null quantity is POS_REQUIRED_FIELDS' finding. */
    @Override
    protected boolean appliesTo(Position position) {
        return position.quantity() != null;
    }

    @Override
    protected Optional<Anomaly> evaluatePosition(Position position, ValidationContext context) {
        BigDecimal quantity = position.quantity();
        if (quantity.compareTo(minExclusive) > 0) {
            return Optional.empty();
        }
        boolean isZero = quantity.signum() == 0;
        return Optional.of(anomaly(
                DATASET,
                position.recordKey(),
                "quantity",
                quantity,
                "Quantite " + (isZero ? "nulle" : "negative") + " (" + quantity.toPlainString()
                        + "), attendue strictement superieure a " + minExclusive.toPlainString() + ".",
                isZero
                        ? "Ligne fantome : position soldee non purgee cote source, le nombre de lignes du "
                                + "portefeuille est surevalue."
                        : "Valorisation negative de " + estimatedImpactAmount(position)
                                + " : l'encours du client est minore d'autant.",
                isZero
                        ? "Purger les positions soldees a la source, ou filtrer les quantites nulles a "
                                + "l'ingestion si le custodian les conserve par conception."
                        : "Verifier une inversion de signe dans l'export custodian (les ventes sont parfois "
                                + "exportees en quantite negative au lieu d'etre nettees de la position)."));
    }

    /** Rough monetary impact, when the price is available to compute one. */
    private static String estimatedImpactAmount(Position position) {
        BigDecimal cost = position.costBasis();
        return cost == null
                ? "montant indeterminable (prix d'achat absent)"
                : cost.abs().setScale(2, java.math.RoundingMode.HALF_UP).toPlainString()
                        + " " + (position.currency() == null ? "" : position.currency());
    }
}
