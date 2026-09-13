package com.wealthguard.quality.rules;

import com.wealthguard.quality.rules.business.AllocationSumEquals100Rule;
import com.wealthguard.quality.rules.business.AllocationWeightInRangeRule;
import com.wealthguard.quality.rules.business.ClientKnownRiskProfileRule;
import com.wealthguard.quality.rules.business.PositionConcentrationLimitRule;
import com.wealthguard.quality.rules.business.PositionCurrencyMatchesInstrumentRule;
import com.wealthguard.quality.rules.business.PositionPositivePurchasePriceRule;
import com.wealthguard.quality.rules.business.PositionPositiveQuantityRule;
import com.wealthguard.quality.rules.business.PositionQuantityPrecisionRule;
import com.wealthguard.quality.rules.business.PurchaseAfterOnboardingRule;
import com.wealthguard.quality.rules.business.PurchaseDateNotInFutureRule;
import com.wealthguard.quality.rules.completeness.PositionRequiredFieldsRule;
import com.wealthguard.quality.rules.referential.AllocationKnownClientRule;
import com.wealthguard.quality.rules.referential.PositionKnownClientRule;
import com.wealthguard.quality.rules.referential.PositionKnownInstrumentRule;
import com.wealthguard.quality.rules.uniqueness.ClientUniqueIdRule;
import com.wealthguard.quality.rules.uniqueness.PositionUniqueIdRule;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

/**
 * <strong>Factory</strong> pattern: turns a configured {@link RuleDefinition}
 * (an id plus parameters, read from {@code quality-rules.yml}) into the concrete
 * {@link QualityRule} strategy that implements it.
 *
 * <p>This is the one class that knows every concrete rule type. Everything else
 * in the engine -- {@code ValidationService}, the controller, {@link
 * ValidationContext} -- depends only on the {@link QualityRule} interface.
 * Adding rule number seventeen means adding one line to the registry below and
 * one entry to {@code quality-rules.yml}; no other class in the engine changes,
 * which is the point of pairing Factory with Strategy here.
 *
 * <p>The registry is a plain {@code Map<String, Function<RuleDefinition,
 * QualityRule>>} rather than a {@code switch} on the id: every rule constructor
 * has the identical {@code (RuleDefinition)} shape (enforced by {@link
 * AbstractQualityRule}), so a constructor reference is both shorter and, unlike a
 * growing switch statement, cannot fall through to the wrong case.
 */
public final class QualityRuleFactory {

    private final Map<String, Function<RuleDefinition, QualityRule>> constructors;

    public QualityRuleFactory() {
        Map<String, Function<RuleDefinition, QualityRule>> registry = new LinkedHashMap<>();

        registry.put(RuleIds.POS_REQUIRED_FIELDS, PositionRequiredFieldsRule::new);

        registry.put(RuleIds.POS_UNIQUE_ID, PositionUniqueIdRule::new);
        registry.put(RuleIds.CLI_UNIQUE_ID, ClientUniqueIdRule::new);

        registry.put(RuleIds.POS_KNOWN_CLIENT, PositionKnownClientRule::new);
        registry.put(RuleIds.POS_KNOWN_INSTRUMENT, PositionKnownInstrumentRule::new);
        registry.put(RuleIds.ALLOC_KNOWN_CLIENT, AllocationKnownClientRule::new);

        registry.put(RuleIds.POS_POSITIVE_QUANTITY, PositionPositiveQuantityRule::new);
        registry.put(RuleIds.POS_POSITIVE_PURCHASE_PRICE, PositionPositivePurchasePriceRule::new);
        registry.put(RuleIds.POS_PURCHASE_DATE_NOT_FUTURE, PurchaseDateNotInFutureRule::new);
        registry.put(RuleIds.POS_PURCHASE_AFTER_ONBOARDING, PurchaseAfterOnboardingRule::new);
        registry.put(RuleIds.POS_CURRENCY_MATCHES_INSTRUMENT, PositionCurrencyMatchesInstrumentRule::new);
        registry.put(RuleIds.POS_CONCENTRATION_LIMIT, PositionConcentrationLimitRule::new);
        registry.put(RuleIds.POS_QUANTITY_PRECISION, PositionQuantityPrecisionRule::new);
        registry.put(RuleIds.CLI_KNOWN_RISK_PROFILE, ClientKnownRiskProfileRule::new);
        registry.put(RuleIds.ALLOC_SUM_EQUALS_100, AllocationSumEquals100Rule::new);
        registry.put(RuleIds.ALLOC_WEIGHT_IN_RANGE, AllocationWeightInRangeRule::new);

        this.constructors = Map.copyOf(registry);
    }

    /**
     * Build the rule described by {@code definition}.
     *
     * @throws UnknownRuleException if {@code definition.id()} has no registered
     *                              constructor -- see the class it is thrown by
     *                              for why this is fatal rather than a skip.
     */
    public QualityRule create(RuleDefinition definition) {
        Function<RuleDefinition, QualityRule> constructor = constructors.get(definition.id());
        if (constructor == null) {
            throw new UnknownRuleException(definition.id(), knownRuleIds());
        }
        return constructor.apply(definition);
    }

    /** Every rule id this factory can build, for validation and diagnostics. */
    public Set<String> knownRuleIds() {
        return constructors.keySet();
    }
}
