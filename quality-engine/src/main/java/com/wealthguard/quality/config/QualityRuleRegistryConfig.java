package com.wealthguard.quality.config;

import com.wealthguard.quality.rules.QualityRule;
import com.wealthguard.quality.rules.QualityRuleFactory;
import com.wealthguard.quality.rules.RuleDefinition;
import com.wealthguard.quality.rules.RuleParameters;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.ArrayList;
import java.util.List;

/**
 * Wires {@code quality-rules.yml} to running {@link QualityRule} instances at
 * application startup.
 *
 * <p>Built once here, as an application-scoped singleton list, because rule
 * instances are stateless and must be shared across concurrent requests (see
 * {@link QualityRule}'s javadoc). A configuration typo -- an unknown rule id, or a
 * missing mandatory parameter -- fails bean creation and therefore stops the
 * application from starting, per the fail-fast rationale in {@link
 * com.wealthguard.quality.rules.UnknownRuleException}.
 */
@Configuration
@EnableConfigurationProperties(QualityRulesProperties.class)
public class QualityRuleRegistryConfig {

    @Bean
    public QualityRuleFactory qualityRuleFactory() {
        return new QualityRuleFactory();
    }

    @Bean
    public List<QualityRule> qualityRules(QualityRulesProperties properties, QualityRuleFactory factory) {
        List<QualityRule> rules = new ArrayList<>();
        for (QualityRulesProperties.RuleConfig config : properties.rules()) {
            RuleDefinition definition = new RuleDefinition(
                    config.id(),
                    config.label(),
                    config.category(),
                    config.severity(),
                    config.description(),
                    RuleParameters.of(config.parameters(), config.id()));
            rules.add(factory.create(definition));
        }
        return List.copyOf(rules);
    }
}
