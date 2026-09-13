package com.wealthguard.quality.rules;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.ValidationContext;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Template for record-level position rules: iterate once, evaluate each line.
 *
 * <p>Complexity: O(P) with O(1) work per line, because every lookup a subclass
 * needs is already indexed in {@link ValidationContext}.
 *
 * <p><strong>The null contract.</strong> Each rule owns exactly one defect. A
 * position with a null {@code quantity} is the business of
 * {@code POS_REQUIRED_FIELDS}; {@code POS_POSITIVE_QUANTITY} must stay silent on
 * it rather than report "quantity is not positive" as well. Subclasses therefore
 * override {@link #appliesTo(Position)} to declare the preconditions they need,
 * and the template skips lines that do not meet them.
 *
 * <p>That is what keeps the report readable: one broken value produces one
 * finding, so the anomaly count is a count of problems rather than a count of
 * rules that happened to trip over the same cell.
 */
public abstract class AbstractPositionRule extends AbstractQualityRule {

    protected static final String DATASET = "positions";

    protected AbstractPositionRule(RuleDefinition definition) {
        super(definition);
    }

    @Override
    public final List<Anomaly> evaluate(ValidationContext context) {
        List<Anomaly> found = new ArrayList<>();
        for (Position position : context.positions()) {
            if (!appliesTo(position)) {
                continue;
            }
            evaluatePosition(position, context).ifPresent(found::add);
        }
        return found;
    }

    /**
     * Preconditions this rule needs before it can judge a line. Default: always.
     *
     * <p>Override to return {@code false} when a field this rule reads is absent --
     * the missing field is another rule's finding.
     */
    protected boolean appliesTo(Position position) {
        return true;
    }

    /** Judge one line. {@link Optional#empty()} means the line is fine. */
    protected abstract Optional<Anomaly> evaluatePosition(Position position, ValidationContext context);
}
