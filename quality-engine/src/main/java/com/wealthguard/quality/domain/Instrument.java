package com.wealthguard.quality.domain;

/**
 * Reference data for a tradable instrument. Acts as the authority against which
 * referential-integrity rules resolve a position's {@code ticker}.
 */
public record Instrument(
        String ticker,
        String name,
        String instrumentType,
        String assetClass,
        String currency,
        String exchange) {
}
