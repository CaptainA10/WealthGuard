package com.wealthguard.quality.rules;

import java.math.BigDecimal;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.LinkedHashSet;

/**
 * Typed, fail-fast accessor over a rule's YAML parameters.
 *
 * <p>YAML gives us {@code Map<String, String>}. Rules need
 * {@code BigDecimal}, {@code int} and {@code Set<String>}. Doing that conversion
 * here, once, with a clear error message, beats sixteen copies of
 * {@code Integer.parseInt(params.get("maxScale"))} that each fail with a bare
 * {@code NumberFormatException} at request time.
 *
 * <p>All accessors that "require" a parameter throw
 * {@link IllegalStateException} at <em>construction</em> time (the factory builds
 * every rule at startup), so a typo in the configuration stops the application
 * from booting rather than silently disabling a control.
 */
public final class RuleParameters {

    private static final RuleParameters EMPTY = new RuleParameters(Map.of(), "<unknown>");

    private final Map<String, String> values;
    private final String ruleId;

    private RuleParameters(Map<String, String> values, String ruleId) {
        this.values = Map.copyOf(values);
        this.ruleId = ruleId;
    }

    public static RuleParameters of(Map<String, String> values, String ruleId) {
        return new RuleParameters(values == null ? Map.of() : sanitise(values), ruleId);
    }

    public static RuleParameters empty() {
        return EMPTY;
    }

    private static Map<String, String> sanitise(Map<String, String> raw) {
        Map<String, String> cleaned = new LinkedHashMap<>();
        raw.forEach((key, value) -> {
            if (key != null && value != null) {
                cleaned.put(key.trim(), value.trim());
            }
        });
        return cleaned;
    }

    public boolean has(String name) {
        return values.containsKey(name) && !values.get(name).isEmpty();
    }

    public BigDecimal requireDecimal(String name) {
        String raw = require(name);
        try {
            return new BigDecimal(raw);
        } catch (NumberFormatException exc) {
            throw new IllegalStateException(
                    "Rule " + ruleId + ": parameter '" + name + "' must be a decimal, got '" + raw + "'", exc);
        }
    }

    public int requireInt(String name) {
        String raw = require(name);
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException exc) {
            throw new IllegalStateException(
                    "Rule " + ruleId + ": parameter '" + name + "' must be an integer, got '" + raw + "'", exc);
        }
    }

    /**
     * Comma-separated list parameter, e.g. {@code allowedProfiles: PRUDENT,EQUILIBRE}.
     *
     * <p>Returns an insertion-ordered set so that an error message listing the
     * allowed values reads the same way as the configuration file.
     */
    public Set<String> requireStringSet(String name) {
        String raw = require(name);
        Set<String> parsed = new LinkedHashSet<>();
        for (String token : raw.split(",")) {
            String trimmed = token.trim();
            if (!trimmed.isEmpty()) {
                parsed.add(trimmed);
            }
        }
        if (parsed.isEmpty()) {
            throw new IllegalStateException(
                    "Rule " + ruleId + ": parameter '" + name + "' must list at least one value");
        }
        // LinkedHashSet, not Set.copyOf: Set.copyOf does not preserve insertion
        // order, and the order is what makes an error message readable.
        return java.util.Collections.unmodifiableSet(parsed);
    }

    /** Required field names, e.g. {@code fields: positionId,clientId,ticker}. */
    public List<String> requireStringList(String name) {
        return List.copyOf(requireStringSet(name));
    }

    private String require(String name) {
        String raw = values.get(name);
        if (raw == null || raw.isEmpty()) {
            throw new IllegalStateException(
                    "Rule " + ruleId + ": missing mandatory parameter '" + name + "'. "
                            + "Declared parameters: " + Arrays.toString(values.keySet().toArray()));
        }
        return raw;
    }

    public Map<String, String> asMap() {
        return values;
    }
}
