package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractPositionRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.Optional;

/**
 * Business coherence (informational): a quantity declared with more than the
 * configured number of decimals signals a degraded upstream export, typically a
 * value round-tripped through a 64-bit float.
 *
 * <p>Deliberately reads {@link java.math.BigDecimal#scale()} of the value exactly
 * as received rather than stripping trailing zeros: the point is to catch how the
 * source system <em>declared</em> the number (see {@link Position}'s rationale for
 * using {@code BigDecimal} in the first place), not to judge its mathematical
 * value. This control has no effect on any computed indicator -- hence
 * {@code INFO} severity in configuration -- it only flags upstream data hygiene.
 *
 * <p>Complexity: O(P).
 */
public class PositionQuantityPrecisionRule extends AbstractPositionRule {

    private final int maxDecimals;

    public PositionQuantityPrecisionRule(RuleDefinition definition) {
        super(definition);
        this.maxDecimals = parameters().requireInt("maxDecimals");
        if (maxDecimals < 0) {
            throw new IllegalStateException(
                    "Rule " + definition.id() + ": maxDecimals must be >= 0, got " + maxDecimals);
        }
    }

    /** A null quantity is POS_REQUIRED_FIELDS' finding. */
    @Override
    protected boolean appliesTo(Position position) {
        return position.quantity() != null;
    }

    @Override
    protected Optional<Anomaly> evaluatePosition(Position position, ValidationContext context) {
        int scale = position.quantity().scale();
        if (scale <= maxDecimals) {
            return Optional.empty();
        }
        return Optional.of(anomaly(
                DATASET,
                position.recordKey(),
                "quantity",
                position.quantity(),
                "Quantite declaree avec " + scale + " decimales, attendu au plus " + maxDecimals + ".",
                "Aucun impact de valorisation, mais signale un export amont degrade (arrondi flottant, "
                        + "conversion binaire).",
                "Verifier la chaine d'extraction du custodian : une quantite entiere ou a "
                        + maxDecimals + " decimales convertie en float64 puis re-serialisee produit ce "
                        + "bruit ; forcer un type decimal de bout en bout plutot que de tronquer ici."));
    }
}
