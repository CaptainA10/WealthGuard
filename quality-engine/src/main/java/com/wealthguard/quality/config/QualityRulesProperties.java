package com.wealthguard.quality.config;

import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;
import java.util.Map;

/**
 * Binds {@code quality-rules.yml} (imported into the environment via {@code
 * spring.config.import} in {@code application.yml}).
 *
 * <p>This is what makes the rule set "configurable, not hardcoded" (cahier des
 * charges §2.2): the set of active controls, their severity and their thresholds
 * all live in this one YAML file, not in Java. {@link
 * com.wealthguard.quality.rules.RuleParameters} keeps every parameter as a raw
 * {@code String} at this layer -- each rule implementation is responsible for
 * parsing its own parameters with a clear error message, rather than this class
 * guessing at everyone's types.
 */
@ConfigurationProperties(prefix = "wealthguard.quality")
public record QualityRulesProperties(List<RuleConfig> rules) {

    public QualityRulesProperties {
        rules = rules == null ? List.of() : List.copyOf(rules);
    }

    /** One entry of {@code quality-rules.yml}: a rule's configured identity. */
    public record RuleConfig(
            String id,
            String label,
            RuleCategory category,
            Severity severity,
            String description,
            Map<String, String> parameters) {

        public RuleConfig {
            parameters = parameters == null ? Map.of() : Map.copyOf(parameters);
        }
    }
}
