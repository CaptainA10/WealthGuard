package com.wealthguard.quality.rules.completeness;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractQualityRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Completeness: every field listed in the {@code fields} parameter must be
 * present and non-blank on every position.
 *
 * <p>The list of mandatory fields is configuration, not code
 * ({@code quality-rules.yml}), because "mandatory" is a business decision that
 * differs per source system -- a custodian feed always carries a currency, an
 * advisor's spreadsheet often does not.
 *
 * <p><strong>Why this rule does not extend {@code AbstractPositionRule}.</strong>
 * That template allows at most one finding per line, which fits the other
 * position rules (a quantity is either positive or it is not). Completeness is
 * inherently multi-valued: a line missing both its ticker and its price has two
 * distinct problems, and collapsing them into one finding would under-report the
 * work a data steward has to do.
 *
 * <p>Complexity: O(P · F) with F the number of configured fields (7 here), i.e.
 * linear in the batch.
 */
public class PositionRequiredFieldsRule extends AbstractQualityRule {

    /**
     * Field name (as written in the YAML) to accessor.
     *
     * <p>A reflection-based lookup would avoid this map but would also make a typo
     * in the configuration a runtime surprise; here an unknown field name fails at
     * startup, and the set of fields a rule may police is explicit.
     */
    private static final Map<String, Function<Position, Object>> ACCESSORS = buildAccessors();

    private static Map<String, Function<Position, Object>> buildAccessors() {
        Map<String, Function<Position, Object>> accessors = new LinkedHashMap<>();
        accessors.put("positionId", Position::positionId);
        accessors.put("clientId", Position::clientId);
        accessors.put("ticker", Position::ticker);
        accessors.put("quantity", Position::quantity);
        accessors.put("purchasePrice", Position::purchasePrice);
        accessors.put("purchaseDate", Position::purchaseDate);
        accessors.put("currency", Position::currency);
        return Map.copyOf(accessors);
    }

    private final List<String> requiredFields;

    public PositionRequiredFieldsRule(RuleDefinition definition) {
        super(definition);
        this.requiredFields = parameters().requireStringList("fields");
        for (String field : requiredFields) {
            if (!ACCESSORS.containsKey(field)) {
                throw new IllegalStateException(
                        "Rule " + definition.id() + ": unknown field '" + field
                                + "' in parameter 'fields'. Known fields: " + ACCESSORS.keySet());
            }
        }
    }

    @Override
    public List<Anomaly> evaluate(ValidationContext context) {
        List<Anomaly> found = new ArrayList<>();
        for (Position position : context.positions()) {
            for (String field : requiredFields) {
                Object value = ACCESSORS.get(field).apply(position);
                if (isAbsent(value)) {
                    found.add(anomaly(
                            "positions",
                            position.recordKey(),
                            field,
                            null,
                            "Champ obligatoire '" + field + "' absent ou vide.",
                            impactOf(field),
                            "Reprendre la ligne dans l'extraction source ; si le champ est "
                                    + "structurellement absent du flux, le retirer du parametre 'fields' "
                                    + "de la regle plutot que de laisser passer des valeurs vides."));
                }
            }
        }
        return found;
    }

    /** A blank string is as absent as a null -- CSV exports produce both. */
    private static boolean isAbsent(Object value) {
        return value == null || (value instanceof String text && text.isBlank());
    }

    /** Field-specific consequence, so the report says what breaks rather than just "field missing". */
    private static String impactOf(String field) {
        return switch (field) {
            case "clientId" -> "Position non rattachable a un portefeuille : elle disparait de la valorisation client "
                    + "et le total cabinet ne reconcilie plus avec la somme des clients.";
            case "quantity" -> "Valorisation impossible : la ligne est ignoree ou comptee a zero, minorant l'encours.";
            case "purchasePrice" -> "Prix de revient inconnu : la plus-value latente de la ligne est incalculable.";
            case "purchaseDate" -> "Duree de detention inconnue : la performance annualisee ne peut pas etre calculee.";
            case "ticker" -> "Instrument inconnu : ni valorisation de marche ni classement par classe d'actif.";
            case "positionId" -> "Ligne non identifiable : tout rapprochement ou correction ulterieure est impossible.";
            case "currency" -> "Devise inconnue : agregation multi-devises non fiable.";
            default -> "Champ obligatoire manquant : traitement aval potentiellement incorrect.";
        };
    }
}
