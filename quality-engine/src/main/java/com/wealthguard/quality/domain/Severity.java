package com.wealthguard.quality.domain;

/**
 * Criticality of a detected anomaly (cahier des charges §2.2).
 *
 * <p>The three levels are not decoration: they drive what the pipeline does next.
 * {@link #BLOQUANT} means the record cannot be loaded at all -- valuing it would
 * produce a wrong number rather than a missing one. {@link #AVERTISSEMENT} means
 * the record loads but a business invariant is broken, so the figure is
 * publishable with a caveat. {@link #INFO} is a signal about upstream data
 * hygiene with no effect on any indicator.
 *
 * <p>Severity is assigned per rule <em>in configuration</em>
 * ({@code quality-rules.yml}), not in the rule's code, so a family office can
 * tighten or relax a control without a redeploy.
 */
public enum Severity {

    /** Record must be rejected: loading it would corrupt an indicator. */
    BLOQUANT(0, true),

    /** Record is loadable but a business invariant is violated. */
    AVERTISSEMENT(1, false),

    /** Informational: upstream data hygiene, no impact on indicators. */
    INFO(2, false);

    private final int rank;
    private final boolean blocking;

    Severity(int rank, boolean blocking) {
        this.rank = rank;
        this.blocking = blocking;
    }

    /** 0 = most critical. Used to sort a report so the worst findings come first. */
    public int rank() {
        return rank;
    }

    /** {@code true} when the offending record must not be loaded downstream. */
    public boolean isBlocking() {
        return blocking;
    }
}
