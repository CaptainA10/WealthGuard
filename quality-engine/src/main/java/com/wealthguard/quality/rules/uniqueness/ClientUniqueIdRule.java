package com.wealthguard.quality.rules.uniqueness;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Client;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractQualityRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Uniqueness: {@code client_id} must identify exactly one client record.
 *
 * <p>Worse than it looks. A duplicated client does not merely duplicate a name:
 * joining positions to clients on a duplicated key produces a fan-out, so every
 * position of that client is counted once per duplicate fiche. One extra CRM row
 * can therefore double a portfolio.
 *
 * <p>Complexity: O(C).
 */
public class ClientUniqueIdRule extends AbstractQualityRule {

    public ClientUniqueIdRule(RuleDefinition definition) {
        super(definition);
    }

    @Override
    public List<Anomaly> evaluate(ValidationContext context) {
        Map<String, List<Client>> byId = new LinkedHashMap<>();
        for (Client client : context.clients()) {
            String id = client.clientId();
            if (id != null && !id.isBlank()) {
                byId.computeIfAbsent(id, key -> new ArrayList<>()).add(client);
            }
        }

        List<Anomaly> found = new ArrayList<>();
        byId.forEach((id, occurrences) -> {
            if (occurrences.size() > 1) {
                int positionsAffected = context.positionsOf(id).size();
                found.add(anomaly(
                        "clients",
                        "client_id=" + id,
                        "clientId",
                        occurrences.size() + " occurrences: "
                                + occurrences.stream().map(Client::fullName).toList(),
                        "Identifiant client present " + occurrences.size() + " fois dans le referentiel.",
                        "Jointure en eventail : les " + positionsAffected
                                + " position(s) de ce client sont comptees " + occurrences.size()
                                + " fois, son encours est multiplie par " + occurrences.size() + ".",
                        "Fusionner les fiches dans le CRM et rejouer l'extraction ; en attendant, "
                                + "exclure ce client des agregats plutot que de choisir une fiche au hasard."));
            }
        });
        return found;
    }
}
