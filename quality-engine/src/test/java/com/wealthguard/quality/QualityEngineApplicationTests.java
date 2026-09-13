package com.wealthguard.quality;

import com.wealthguard.quality.rules.QualityRule;
import com.wealthguard.quality.rules.QualityRuleFactory;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Boots the full application context against the real {@code quality-rules.yml}.
 *
 * <p>This is the test that actually exercises the fail-fast contract described on
 * {@link com.wealthguard.quality.rules.UnknownRuleException}: if the shipped
 * configuration ever references a rule id the factory cannot build, or omits a
 * mandatory parameter, the context fails to start and this test fails -- exactly
 * the behaviour the engine is supposed to have in production.
 */
@SpringBootTest
class QualityEngineApplicationTests {

    @Autowired
    private List<QualityRule> qualityRules;

    @Autowired
    private QualityRuleFactory qualityRuleFactory;

    @Test
    void contextLoads() {
    }

    @Test
    void everyIdKnownToTheFactoryIsWiredIntoARunningRule() {
        List<String> wiredIds = qualityRules.stream().map(QualityRule::id).toList();

        assertThat(wiredIds).containsExactlyInAnyOrderElementsOf(qualityRuleFactory.knownRuleIds());
    }
}
