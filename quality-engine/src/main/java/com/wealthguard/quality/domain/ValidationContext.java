package com.wealthguard.quality.domain;

import java.time.LocalDate;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Everything a rule needs to make a decision, plus the indexes it needs to do so
 * cheaply.
 *
 * <p><strong>Why indexes belong here and not in the rules.</strong> A naive
 * referential rule would scan the client list for every position: with P
 * positions and C clients that is O(P·C). On a 500-position batch against 45
 * clients that is fine; on a nightly 2-million-line custodian file it is not.
 * Building the lookup maps once in this constructor makes every rule O(P) with
 * O(1) lookups, and -- more importantly -- means a new rule author cannot
 * accidentally reintroduce the quadratic scan.
 *
 * <p>Construction cost: O(P + C + I + A). Memory: one map entry per record.
 *
 * <p>Duplicate keys: {@code clientsById} and {@code instrumentsByTicker} keep the
 * <em>first</em> occurrence. The uniqueness rules work off the raw lists, so a
 * duplicate is still reported; the index only has to be deterministic.
 */
public final class ValidationContext {

    private final List<Position> positions;
    private final List<Client> clients;
    private final List<Instrument> instruments;
    private final List<TargetAllocation> targetAllocations;
    private final LocalDate evaluationDate;

    private final Map<String, Client> clientsById;
    private final Map<String, Instrument> instrumentsByTicker;
    private final Map<String, List<Position>> positionsByClientId;
    private final Map<String, List<TargetAllocation>> allocationsByClientId;

    public ValidationContext(
            List<Position> positions,
            List<Client> clients,
            List<Instrument> instruments,
            List<TargetAllocation> targetAllocations,
            LocalDate evaluationDate) {

        this.positions = List.copyOf(Objects.requireNonNullElse(positions, List.of()));
        this.clients = List.copyOf(Objects.requireNonNullElse(clients, List.of()));
        this.instruments = List.copyOf(Objects.requireNonNullElse(instruments, List.of()));
        this.targetAllocations = List.copyOf(Objects.requireNonNullElse(targetAllocations, List.of()));
        this.evaluationDate = Objects.requireNonNull(evaluationDate, "evaluationDate");

        this.clientsById = indexUnique(this.clients, Client::clientId);
        this.instrumentsByTicker = indexUnique(this.instruments, Instrument::ticker);
        this.positionsByClientId = indexMulti(this.positions, Position::clientId);
        this.allocationsByClientId = indexMulti(this.targetAllocations, TargetAllocation::clientId);
    }

    private static <T> Map<String, T> indexUnique(List<T> items, java.util.function.Function<T, String> keyFn) {
        Map<String, T> index = new LinkedHashMap<>();
        for (T item : items) {
            String key = keyFn.apply(item);
            if (key != null && !key.isBlank()) {
                index.putIfAbsent(key, item);
            }
        }
        return Collections.unmodifiableMap(index);
    }

    private static <T> Map<String, List<T>> indexMulti(List<T> items, java.util.function.Function<T, String> keyFn) {
        Map<String, List<T>> index = new LinkedHashMap<>();
        for (T item : items) {
            String key = keyFn.apply(item);
            if (key != null && !key.isBlank()) {
                index.computeIfAbsent(key, k -> new java.util.ArrayList<>()).add(item);
            }
        }
        index.replaceAll((k, v) -> Collections.unmodifiableList(v));
        return Collections.unmodifiableMap(index);
    }

    public List<Position> positions() {
        return positions;
    }

    public List<Client> clients() {
        return clients;
    }

    public List<Instrument> instruments() {
        return instruments;
    }

    public List<TargetAllocation> targetAllocations() {
        return targetAllocations;
    }

    /**
     * The date "today" means for this validation run.
     *
     * <p>Injected rather than read from {@code LocalDate.now()} inside the rules:
     * a rule that reads the system clock cannot be unit-tested deterministically,
     * and {@code POS_PURCHASE_DATE_NOT_FUTURE} would become a test that passes
     * today and fails at midnight.
     */
    public LocalDate evaluationDate() {
        return evaluationDate;
    }

    public Client client(String clientId) {
        return clientId == null ? null : clientsById.get(clientId);
    }

    public boolean hasClient(String clientId) {
        return clientId != null && clientsById.containsKey(clientId);
    }

    public Instrument instrument(String ticker) {
        return ticker == null ? null : instrumentsByTicker.get(ticker);
    }

    public boolean hasInstrument(String ticker) {
        return ticker != null && instrumentsByTicker.containsKey(ticker);
    }

    public List<Position> positionsOf(String clientId) {
        return positionsByClientId.getOrDefault(clientId, List.of());
    }

    public Map<String, List<Position>> positionsByClientId() {
        return positionsByClientId;
    }

    public Map<String, List<TargetAllocation>> allocationsByClientId() {
        return allocationsByClientId;
    }

    /** True when the reference tables were supplied; referential rules skip otherwise. */
    public boolean hasClientReference() {
        return !clients.isEmpty();
    }

    public boolean hasInstrumentReference() {
        return !instruments.isEmpty();
    }
}
