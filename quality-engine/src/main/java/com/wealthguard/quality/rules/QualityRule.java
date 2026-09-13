package com.wealthguard.quality.rules;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.ValidationContext;

import java.util.List;

/**
 * <strong>Strategy</strong> pattern: one interchangeable quality control.
 *
 * <p>The engine ({@code ValidationService}) holds a {@code List<QualityRule>} and
 * knows nothing about any concrete control. Adding a rule means writing one
 * implementation and registering it in {@link QualityRuleFactory} -- no existing
 * class changes, which is the open/closed property the pattern buys us.
 *
 * <p><strong>Why the whole context, not one record.</strong> A per-record
 * signature ({@code evaluate(Position)}) looks tidier but cannot express the
 * rules that matter most here: uniqueness is a property of the batch, the
 * allocation sum is a property of a client's rows, and concentration needs the
 * client's other positions. Passing the {@link ValidationContext} makes the
 * interface uniform for record-level and aggregate-level controls alike;
 * {@link AbstractPositionRule} then gives record-level rules their per-record
 * convenience back without a second interface.
 *
 * <p>Implementations must be <em>stateless and thread-safe</em>: one instance is
 * built at startup and shared across concurrent HTTP requests.
 */
public interface QualityRule {

    /** Configured identity of this rule: id, label, category, severity, parameters. */
    RuleDefinition definition();

    /**
     * Evaluate the batch and return every anomaly found. Never {@code null};
     * an empty list means "this control passed".
     */
    List<Anomaly> evaluate(ValidationContext context);

    /**
     * Whether this rule can run at all against the supplied batch.
     *
     * <p>A referential rule has nothing to say when the reference table was not
     * sent. Returning {@code false} here makes the engine report the rule as
     * <em>skipped</em> instead of silently passing -- an important distinction: a
     * green report that skipped half its controls is worse than a red one.
     */
    default boolean isApplicable(ValidationContext context) {
        return true;
    }

    /** Convenience accessor used throughout the engine and its logs. */
    default String id() {
        return definition().id();
    }
}
