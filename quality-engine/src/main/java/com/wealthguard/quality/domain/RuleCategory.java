package com.wealthguard.quality.domain;

/**
 * The four families of quality control required by the cahier des charges §2.2.
 *
 * <p>Used to group a report by control family, which is how a data-quality
 * committee actually reads one ("we have a referential-integrity problem", not
 * "we have 42 anomalies").
 */
public enum RuleCategory {

    /** Mandatory fields are present and non-blank. */
    COMPLETUDE,

    /** Business keys appear at most once. */
    UNICITE,

    /** Foreign keys resolve against a reference table. */
    REFERENTIEL,

    /** Domain invariants: signs, ranges, chronology, allocation sums, concentration. */
    COHERENCE_METIER
}
