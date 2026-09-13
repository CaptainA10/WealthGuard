package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Instrument;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractPositionRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.Optional;

/**
 * Business coherence: a position must be booked in the currency the instrument
 * actually trades in.
 *
 * <p>This is the quietest expensive defect in the set. Nothing looks wrong: the
 * quantity is positive, the price is plausible, the ticker resolves. But summing
 * a CHF-labelled amount into a EUR portfolio total without conversion silently
 * distorts every percentage allocation, and the error scales with the FX rate
 * rather than announcing itself.
 *
 * <p>Complexity: O(P).
 */
public class PositionCurrencyMatchesInstrumentRule extends AbstractPositionRule {

    public PositionCurrencyMatchesInstrumentRule(RuleDefinition definition) {
        super(definition);
    }

    @Override
    public boolean isApplicable(ValidationContext context) {
        return context.hasInstrumentReference();
    }

    /**
     * Needs a currency and a resolvable instrument. A missing currency belongs to
     * POS_REQUIRED_FIELDS, an unknown ticker to POS_KNOWN_INSTRUMENT.
     */
    @Override
    protected boolean appliesTo(Position position) {
        return position.currency() != null
                && !position.currency().isBlank()
                && position.ticker() != null;
    }

    @Override
    protected Optional<Anomaly> evaluatePosition(Position position, ValidationContext context) {
        Instrument instrument = context.instrument(position.ticker());
        if (instrument == null || instrument.currency() == null) {
            return Optional.empty();
        }
        if (instrument.currency().equalsIgnoreCase(position.currency())) {
            return Optional.empty();
        }
        return Optional.of(anomaly(
                DATASET,
                position.recordKey(),
                "currency",
                position.currency(),
                "Position libellee en " + position.currency() + " alors que " + position.ticker()
                        + " cote en " + instrument.currency() + " sur " + instrument.exchange() + ".",
                "Melange de devises non converti : la valorisation de la ligne est fausse d'un facteur "
                        + "egal au taux de change, et toutes les allocations en pourcentage du client "
                        + "s'en trouvent decalees.",
                "Verifier s'il s'agit d'une ligne cotee sur une place secondaire dans une autre devise "
                        + "(auquel cas le ticker est incomplet) ou d'une devise de reglement confondue "
                        + "avec la devise de cotation dans l'export."));
    }
}
