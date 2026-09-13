package com.wealthguard.quality.rules.business;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Client;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractQualityRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * Business coherence: a client's risk profile must belong to the firm's
 * nomenclature.
 *
 * <p>The allowed set is a parameter, not an enum in code, because the
 * nomenclature is the firm's own vocabulary (e.g. {@code PRUDENT},
 * {@code EQUILIBRE}, {@code DYNAMIQUE}, {@code OFFENSIF}) and changes with
 * marketing or compliance decisions, not with a software release.
 *
 * <p>A missing or blank profile is out of scope for this control: whether a risk
 * profile is mandatory is a completeness question for a client-level
 * {@code CLI_REQUIRED_FIELDS} rule, which does not exist yet -- this rule only
 * judges a profile that was actually supplied.
 *
 * <p>Complexity: O(C).
 */
public class ClientKnownRiskProfileRule extends AbstractQualityRule {

    private final Set<String> allowedProfiles;

    public ClientKnownRiskProfileRule(RuleDefinition definition) {
        super(definition);
        this.allowedProfiles = parameters().requireStringSet("allowedProfiles");
    }

    @Override
    public List<Anomaly> evaluate(ValidationContext context) {
        List<Anomaly> found = new ArrayList<>();
        for (Client client : context.clients()) {
            String profile = client.riskProfile();
            if (profile == null || profile.isBlank() || allowedProfiles.contains(profile)) {
                continue;
            }
            found.add(anomaly(
                    "clients",
                    client.recordKey(),
                    "riskProfile",
                    profile,
                    "Profil de risque '" + profile + "' hors nomenclature. Profils attendus : "
                            + allowedProfiles + ".",
                    "Controle d'adequation impossible : l'allocation reelle du client ne peut pas "
                            + "etre comparee a la cible de son profil.",
                    "Verifier une faute de saisie ou une nomenclature obsolete cote CRM ; mettre a "
                            + "jour soit la fiche client, soit le parametre 'allowedProfiles' si un "
                            + "nouveau profil a ete introduit legitimement."));
        }
        return found;
    }
}
