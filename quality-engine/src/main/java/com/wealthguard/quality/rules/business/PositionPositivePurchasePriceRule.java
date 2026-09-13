package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractPositionRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.math.BigDecimal;
import java.util.Optional;

/**
 * Business coherence: the purchase price must be strictly above the configured
 * floor (0 by default).
 *
 * <p>Zero is the case that matters. A naive {@code price < 0} check lets it
 * through, and a zero cost basis makes the latent gain of the line equal to its
 * entire market value -- a portfolio that appears to have made infinite return.
 * That is why the seed dataset injects an exact zero alongside the negatives.
 *
 * <p>Complexity: O(P).
 */
public class PositionPositivePurchasePriceRule extends AbstractPositionRule {

    private final BigDecimal minExclusive;

    public PositionPositivePurchasePriceRule(RuleDefinition definition) {
        super(definition);
        this.minExclusive = parameters().requireDecimal("minExclusive");
    }

    @Override
    protected boolean appliesTo(Position position) {
        return position.purchasePrice() != null;
    }

    @Override
    protected Optional<Anomaly> evaluatePosition(Position position, ValidationContext context) {
        BigDecimal price = position.purchasePrice();
        if (price.compareTo(minExclusive) > 0) {
            return Optional.empty();
        }
        boolean isZero = price.signum() == 0;
        return Optional.of(anomaly(
                DATASET,
                position.recordKey(),
                "purchasePrice",
                price,
                "Prix d'achat " + (isZero ? "nul" : "negatif") + " (" + price.toPlainString()
                        + "), attendu strictement superieur a " + minExclusive.toPlainString() + ".",
                isZero
                        ? "Prix de revient nul : la plus-value latente de la ligne devient egale a sa "
                                + "valeur de marche, la performance du portefeuille est aberrante a la hausse."
                        : "Prix de revient negatif : la plus-value latente change de signe, la performance "
                                + "du portefeuille est fausse dans les deux sens.",
                isZero
                        ? "Chercher un titre recu par apport, donation ou attribution gratuite : le prix "
                                + "de revient existe mais n'a pas ete repris dans l'export. A defaut, "
                                + "reconstituer le prix de revient fiscal."
                        : "Verifier un remboursement ou un avoir comptabilise comme un prix unitaire "
                                + "plutot que comme un flux separe."));
    }
}
