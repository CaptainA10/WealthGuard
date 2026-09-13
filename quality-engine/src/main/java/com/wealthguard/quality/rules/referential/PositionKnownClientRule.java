package com.wealthguard.quality.rules.referential;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractPositionRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.Optional;

/**
 * Referential integrity: a position's {@code client_id} must resolve in the
 * client reference table.
 *
 * <p>An orphan position is invisible in every per-client report yet present in
 * the platform total, which is exactly the failure mode that makes a
 * reconciliation "off by a bit" with no traceable cause.
 *
 * <p>Complexity: O(P) -- one hash lookup per line against the index built in
 * {@link ValidationContext}, not a scan of the client list.
 */
public class PositionKnownClientRule extends AbstractPositionRule {

    public PositionKnownClientRule(RuleDefinition definition) {
        super(definition);
    }

    /**
     * Without a client reference table there is nothing to resolve against. The
     * engine then reports this rule as skipped rather than passed -- claiming
     * referential integrity when no reference was supplied would be a lie.
     */
    @Override
    public boolean isApplicable(ValidationContext context) {
        return context.hasClientReference();
    }

    /** A blank clientId belongs to POS_REQUIRED_FIELDS. */
    @Override
    protected boolean appliesTo(Position position) {
        return position.clientId() != null && !position.clientId().isBlank();
    }

    @Override
    protected Optional<Anomaly> evaluatePosition(Position position, ValidationContext context) {
        if (context.hasClient(position.clientId())) {
            return Optional.empty();
        }
        return Optional.of(anomaly(
                DATASET,
                position.recordKey(),
                "clientId",
                position.clientId(),
                "Le client '" + position.clientId() + "' n'existe pas dans le referentiel clients.",
                "Encours orphelin : la position alimente le total cabinet mais aucun reporting client, "
                        + "donc la somme des portefeuilles ne reconcilie plus avec le total.",
                "Verifier si le client a ete cree apres l'extraction du referentiel (rejouer l'extraction "
                        + "dans le bon ordre) ou s'il s'agit d'un identifiant errone cote custodian."));
    }
}
