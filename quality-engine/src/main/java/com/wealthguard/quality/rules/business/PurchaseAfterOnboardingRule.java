package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Client;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractPositionRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Optional;

/**
 * Business coherence: a position cannot be bought before its client entered into
 * a relationship with the firm.
 *
 * <p>The interesting property of this control is that both sides of the
 * inequality may be the culprit, and the engine cannot tell which -- so the
 * finding is an AVERTISSEMENT, and the correction hypothesis names both
 * candidates. Assets transferred in from another bank are the common legitimate
 * case, which is precisely why this is a warning and not a rejection:
 * automatically dropping those lines would erase real holdings.
 *
 * <p>Complexity: O(P) -- the client lookup is indexed.
 */
public class PurchaseAfterOnboardingRule extends AbstractPositionRule {

    private final int toleranceDays;

    public PurchaseAfterOnboardingRule(RuleDefinition definition) {
        super(definition);
        this.toleranceDays = parameters().requireInt("toleranceDays");
        if (toleranceDays < 0) {
            throw new IllegalStateException(
                    "Rule " + definition.id() + ": toleranceDays must be >= 0, got " + toleranceDays);
        }
    }

    @Override
    public boolean isApplicable(ValidationContext context) {
        return context.hasClientReference();
    }

    /**
     * Needs both dates and a resolvable client. An unknown client is
     * POS_KNOWN_CLIENT's finding; reporting it twice would tell the steward
     * nothing new.
     */
    @Override
    protected boolean appliesTo(Position position) {
        return position.purchaseDate() != null
                && position.clientId() != null
                && !position.clientId().isBlank();
    }

    @Override
    protected Optional<Anomaly> evaluatePosition(Position position, ValidationContext context) {
        Client client = context.client(position.clientId());
        if (client == null || client.onboardingDate() == null) {
            return Optional.empty();
        }
        LocalDate floor = client.onboardingDate().minusDays(toleranceDays);
        if (!position.purchaseDate().isBefore(floor)) {
            return Optional.empty();
        }
        long daysBefore = ChronoUnit.DAYS.between(position.purchaseDate(), client.onboardingDate());
        return Optional.of(anomaly(
                DATASET,
                position.recordKey(),
                "purchaseDate",
                position.purchaseDate(),
                "Achat le " + position.purchaseDate() + ", soit " + daysBefore
                        + " jour(s) avant l'entree en relation du client " + position.clientId()
                        + " (" + client.onboardingDate() + ").",
                "Incoherence chronologique : la performance depuis l'entree en relation est calculee "
                        + "sur une periode ou le client n'etait pas encore suivi, ce qui attribue au "
                        + "cabinet une performance qu'il n'a pas produite.",
                "Cas legitime le plus frequent : titres transferes d'un autre etablissement, la date "
                        + "d'achat d'origine etant conservee. Verifier alors que la date d'onboarding est "
                        + "la bonne. Sinon, la position appartient probablement a un autre client."));
    }
}
