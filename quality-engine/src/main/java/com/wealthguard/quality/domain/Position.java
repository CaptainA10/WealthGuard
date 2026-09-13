package com.wealthguard.quality.domain;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * One portfolio line as received from the source system.
 *
 * <p>Every field is deliberately nullable. This is the record <em>before</em>
 * validation: a null {@code quantity} or a blank {@code clientId} is precisely
 * what the completeness rules exist to find, so rejecting nulls at construction
 * time would make the engine unable to report them.
 *
 * <p>{@code quantity} and {@code purchasePrice} are {@link BigDecimal}, not
 * {@code double}: these are monetary/share amounts, and the
 * {@code POS_QUANTITY_PRECISION} rule needs the <em>declared scale</em> of the
 * incoming value, which a binary float destroys.
 */
public record Position(
        String positionId,
        String clientId,
        String ticker,
        BigDecimal quantity,
        BigDecimal purchasePrice,
        LocalDate purchaseDate,
        String currency) {

    /** Stable identifier used in anomaly reports as "the offending line". */
    public String recordKey() {
        return "position_id=" + (positionId == null || positionId.isBlank() ? "<absent>" : positionId);
    }

    /**
     * Cost basis of the line, or {@code null} when it cannot be computed.
     *
     * <p>Returns null rather than zero on missing data: zero would silently
     * shrink the denominator of the concentration rule and understate a real
     * breach.
     */
    public BigDecimal costBasis() {
        if (quantity == null || purchasePrice == null) {
            return null;
        }
        return quantity.multiply(purchasePrice);
    }

    /** True when the line carries a usable, strictly positive cost basis. */
    public boolean hasUsableCostBasis() {
        BigDecimal cost = costBasis();
        return cost != null
                && quantity.signum() > 0
                && purchasePrice.signum() > 0;
    }
}
