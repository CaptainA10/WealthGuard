package com.wealthguard.quality.rules;

import java.util.Collection;

/**
 * Thrown at startup when {@code quality-rules.yml} references a rule id the
 * factory cannot build.
 *
 * <p>Deliberately fatal: a configuration typo must stop the application from
 * booting. The alternative -- skipping the unknown id -- would silently disable a
 * control, and a data-quality platform that quietly stops checking something is
 * worse than one that is down.
 */
public class UnknownRuleException extends RuntimeException {

    public UnknownRuleException(String ruleId, Collection<String> known) {
        super("Unknown quality rule id '" + ruleId + "' in configuration. Known ids: " + known);
    }
}
