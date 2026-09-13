package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractPositionRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Optional;

/**
 * Business coherence: a purchase cannot be dated after the valuation date.
 *
 * <p>{@code toleranceDays} exists for a real operational reason: a custodian in a
 * later time zone, or a trade booked value-date instead of trade-date, can
 * legitimately produce a date one day ahead. Setting it to 0 makes the rule
 * strict; setting it to 1 suppresses a whole class of false positives.
 *
 * <p><strong>The clock is data, not ambient state.</strong> "Today" comes from
 * {@link ValidationContext#evaluationDate()}, never from
 * {@code LocalDate.now()}. A rule that reads the system clock cannot be tested
 * deterministically -- a test asserting "2026-10-28 is in the future" would pass
 * today and start failing on that date -- and it also makes it impossible to
 * re-run a past validation as of its original date.
 *
 * <p>Complexity: O(P).
 */
public class PurchaseDateNotInFutureRule extends AbstractPositionRule {

    private final int toleranceDays;

    public PurchaseDateNotInFutureRule(RuleDefinition definition) {
        super(definition);
        this.toleranceDays = parameters().requireInt("toleranceDays");
        if (toleranceDays < 0) {
            throw new IllegalStateException(
                    "Rule " + definition.id() + ": toleranceDays must be >= 0, got " + toleranceDays);
        }
    }

    @Override
    protected boolean appliesTo(Position position) {
        return position.purchaseDate() != null;
    }

    @Override
    protected Optional<Anomaly> evaluatePosition(Position position, ValidationContext context) {
        LocalDate limit = context.evaluationDate().plusDays(toleranceDays);
        LocalDate purchaseDate = position.purchaseDate();
        if (!purchaseDate.isAfter(limit)) {
            return Optional.empty();
        }
        long daysAhead = ChronoUnit.DAYS.between(context.evaluationDate(), purchaseDate);
        return Optional.of(anomaly(
                DATASET,
                position.recordKey(),
                "purchaseDate",
                purchaseDate,
                "Date d'achat posterieure a la date de valorisation ("
                        + context.evaluationDate() + "), soit " + daysAhead + " jour(s) dans le futur.",
                "Duree de detention negative : la performance annualisee de la ligne est invalide "
                        + "(division par une duree negative) et contamine la performance du portefeuille.",
                daysAhead <= 5
                        ? "Ecart faible : verifier une confusion date de valeur / date de negociation, "
                                + "ou un decalage de fuseau horaire du custodian. Augmenter 'toleranceDays' "
                                + "si le cas est structurel."
                        : "Ecart important : suspecter une erreur de saisie sur l'annee ou le mois, "
                                + "ou un ordre saisi par anticipation mais pas encore execute."));
    }
}
