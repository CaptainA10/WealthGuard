package com.wealthguard.quality.rules.uniqueness;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractQualityRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Uniqueness: {@code position_id} is the business key of a portfolio line and
 * must appear at most once in a batch.
 *
 * <p>This is the single most expensive defect in the dataset: a duplicated
 * position is counted twice in assets under management, so the firm reports an
 * AUM it does not manage. It is also the hardest to spot by eye, because both
 * rows look individually valid.
 *
 * <p>One finding per duplicated <em>key</em>, not per extra row: the steward has
 * one decision to make ("which of these two is the real one?"), so one line in
 * the report.
 *
 * <p>Complexity: O(P) time, O(P) additional memory for the occurrence map --
 * versus the O(P²) pairwise comparison that this rule exists to avoid.
 */
public class PositionUniqueIdRule extends AbstractQualityRule {

    public PositionUniqueIdRule(RuleDefinition definition) {
        super(definition);
    }

    @Override
    public List<Anomaly> evaluate(ValidationContext context) {
        Map<String, List<Position>> byId = new LinkedHashMap<>();
        for (Position position : context.positions()) {
            String id = position.positionId();
            // A blank id is POS_REQUIRED_FIELDS' finding, not ours.
            if (id != null && !id.isBlank()) {
                byId.computeIfAbsent(id, key -> new ArrayList<>()).add(position);
            }
        }

        List<Anomaly> found = new ArrayList<>();
        byId.forEach((id, occurrences) -> {
            if (occurrences.size() > 1) {
                found.add(anomaly(
                        "positions",
                        "position_id=" + id,
                        "positionId",
                        occurrences.size() + " occurrences",
                        "Identifiant de position present " + occurrences.size() + " fois dans le lot.",
                        "Double comptage de l'encours : " + describeDivergence(occurrences),
                        "Conserver l'occurrence la plus recente cote source et rejeter les autres ; "
                                + "si les quantites divergent, le lot doit etre rejete en totalite car on "
                                + "ne peut pas deviner laquelle est exacte."));
            }
        });
        return found;
    }

    /**
     * Say whether the duplicates agree, because the remediation differs: identical
     * rows can be de-duplicated automatically, divergent ones need a human.
     */
    private static String describeDivergence(List<Position> occurrences) {
        boolean sameQuantity = occurrences.stream()
                .map(Position::quantity)
                .distinct()
                .count() == 1;
        if (sameQuantity) {
            return "doublon strict, l'encours de la ligne est compte deux fois a l'identique.";
        }
        return "doublon avec des quantites differentes ("
                + occurrences.stream().map(p -> String.valueOf(p.quantity())).toList()
                + "), l'encours retenu est arbitraire.";
    }
}
