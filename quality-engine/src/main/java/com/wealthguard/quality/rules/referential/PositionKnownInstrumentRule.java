package com.wealthguard.quality.rules.referential;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractPositionRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.Optional;

/**
 * Referential integrity: a position's {@code ticker} must exist in the
 * instrument reference table.
 *
 * <p>An unknown ticker has no price series and no asset class, so the line can
 * neither be valued nor allocated. Unlike an orphan client, this defect is
 * usually a symptom of a corporate action (ticker change, merger, delisting)
 * rather than a typo -- hence the correction hypothesis.
 *
 * <p>Complexity: O(P).
 */
public class PositionKnownInstrumentRule extends AbstractPositionRule {

    public PositionKnownInstrumentRule(RuleDefinition definition) {
        super(definition);
    }

    @Override
    public boolean isApplicable(ValidationContext context) {
        return context.hasInstrumentReference();
    }

    @Override
    protected boolean appliesTo(Position position) {
        return position.ticker() != null && !position.ticker().isBlank();
    }

    @Override
    protected Optional<Anomaly> evaluatePosition(Position position, ValidationContext context) {
        if (context.hasInstrument(position.ticker())) {
            return Optional.empty();
        }
        return Optional.of(anomaly(
                DATASET,
                position.recordKey(),
                "ticker",
                position.ticker(),
                "Le ticker '" + position.ticker() + "' est absent du referentiel instruments.",
                "Ni valorisation de marche ni classe d'actif : la ligne est exclue de la valorisation "
                        + "et de l'allocation, minorant l'encours du client.",
                "Verifier une operation sur titre (changement de code, fusion, radiation) avant de "
                        + "conclure a une saisie erronee ; enrichir le referentiel si l'instrument est legitime."));
    }
}
