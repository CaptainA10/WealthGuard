package com.wealthguard.quality.rules.referential;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.TargetAllocation;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.rules.AbstractQualityRule;
import com.wealthguard.quality.rules.RuleDefinition;

import java.util.ArrayList;
import java.util.List;

/**
 * Referential integrity on the advisors' allocation spreadsheet: every
 * {@code client_id} it mentions must exist in the client reference table.
 *
 * <p>This is the rule that catches a stale spreadsheet -- a target allocation
 * kept for a client who left the firm, or a typo in a manually entered id. The
 * target then contributes to firm-level target-versus-actual gaps for a
 * portfolio that does not exist.
 *
 * <p>Complexity: O(A).
 */
public class AllocationKnownClientRule extends AbstractQualityRule {

    public AllocationKnownClientRule(RuleDefinition definition) {
        super(definition);
    }

    @Override
    public boolean isApplicable(ValidationContext context) {
        return context.hasClientReference() && !context.targetAllocations().isEmpty();
    }

    @Override
    public List<Anomaly> evaluate(ValidationContext context) {
        List<Anomaly> found = new ArrayList<>();
        for (TargetAllocation allocation : context.targetAllocations()) {
            String clientId = allocation.clientId();
            if (clientId == null || clientId.isBlank() || context.hasClient(clientId)) {
                continue;
            }
            found.add(anomaly(
                    "target_allocations",
                    allocation.recordKey(),
                    "clientId",
                    clientId,
                    "Allocation cible rattachee au client inexistant '" + clientId + "'.",
                    "Cible fantome : les ecarts cible/reel agreges au niveau cabinet integrent un "
                            + "portefeuille qui n'existe pas.",
                    "Rapprocher le fichier d'allocation du referentiel clients : soit le client est sorti "
                            + "et la ligne doit etre archivee, soit l'identifiant a ete saisi a la main de "
                            + "travers dans le classeur."));
        }
        return found;
    }
}
