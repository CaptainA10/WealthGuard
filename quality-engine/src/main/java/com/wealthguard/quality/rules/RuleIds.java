package com.wealthguard.quality.rules;

/**
 * Canonical rule identifiers.
 *
 * <p>These strings are a contract with three other components: the factory
 * registry, {@code quality-rules.yml}, and the Python seed generator's anomaly
 * catalogue (which predicts, rule by rule, what the engine should report). A
 * constant here rather than a literal in four places means a rename cannot
 * silently desynchronise them -- the end-to-end test compares this set against
 * the seed manifest.
 */
public final class RuleIds {

    // --- Completeness ---
    public static final String POS_REQUIRED_FIELDS = "POS_REQUIRED_FIELDS";

    // --- Uniqueness ---
    public static final String POS_UNIQUE_ID = "POS_UNIQUE_ID";
    public static final String CLI_UNIQUE_ID = "CLI_UNIQUE_ID";

    // --- Referential integrity ---
    public static final String POS_KNOWN_CLIENT = "POS_KNOWN_CLIENT";
    public static final String POS_KNOWN_INSTRUMENT = "POS_KNOWN_INSTRUMENT";
    public static final String ALLOC_KNOWN_CLIENT = "ALLOC_KNOWN_CLIENT";

    // --- Business coherence ---
    public static final String POS_POSITIVE_QUANTITY = "POS_POSITIVE_QUANTITY";
    public static final String POS_POSITIVE_PURCHASE_PRICE = "POS_POSITIVE_PURCHASE_PRICE";
    public static final String POS_PURCHASE_DATE_NOT_FUTURE = "POS_PURCHASE_DATE_NOT_FUTURE";
    public static final String POS_PURCHASE_AFTER_ONBOARDING = "POS_PURCHASE_AFTER_ONBOARDING";
    public static final String POS_CURRENCY_MATCHES_INSTRUMENT = "POS_CURRENCY_MATCHES_INSTRUMENT";
    public static final String POS_CONCENTRATION_LIMIT = "POS_CONCENTRATION_LIMIT";
    public static final String POS_QUANTITY_PRECISION = "POS_QUANTITY_PRECISION";
    public static final String CLI_KNOWN_RISK_PROFILE = "CLI_KNOWN_RISK_PROFILE";
    public static final String ALLOC_SUM_EQUALS_100 = "ALLOC_SUM_EQUALS_100";
    public static final String ALLOC_WEIGHT_IN_RANGE = "ALLOC_WEIGHT_IN_RANGE";

    private RuleIds() {
    }
}
