package com.wealthguard.quality.domain;

import java.math.BigDecimal;

/**
 * One line of a client's target allocation, in percent, as maintained by the
 * advisors in their spreadsheet.
 *
 * <p>The weights of a client must sum to 100 ({@code ALLOC_SUM_EQUALS_100}) and
 * each must sit in [0, 100] ({@code ALLOC_WEIGHT_IN_RANGE}).
 */
public record TargetAllocation(
        String clientId,
        String assetClass,
        BigDecimal targetWeightPct) {

    public String recordKey() {
        return "client_id=" + clientId + "&asset_class=" + assetClass;
    }
}
