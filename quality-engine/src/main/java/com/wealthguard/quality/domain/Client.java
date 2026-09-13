package com.wealthguard.quality.domain;

import java.time.LocalDate;

/**
 * A client of the family office, as received from the CRM extract.
 *
 * <p>Nullable by design -- see {@link Position} for the rationale.
 */
public record Client(
        String clientId,
        String fullName,
        String riskProfile,
        String referenceCurrency,
        LocalDate onboardingDate,
        String advisor) {

    public String recordKey() {
        return "client_id=" + (clientId == null || clientId.isBlank() ? "<absent>" : clientId);
    }
}
