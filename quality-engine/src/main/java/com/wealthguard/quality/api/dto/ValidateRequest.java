package com.wealthguard.quality.api.dto;

import com.wealthguard.quality.domain.Client;
import com.wealthguard.quality.domain.Instrument;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.TargetAllocation;

import java.time.LocalDate;
import java.util.List;

/**
 * Request body of {@code POST /api/v1/validate}.
 *
 * <p>A batch may legitimately omit {@code clients}, {@code instruments} or {@code
 * targetAllocations}: the pipeline can validate positions alone before the
 * reference extracts are available, and every referential rule already handles
 * that via {@code isApplicable} rather than failing on missing input.
 *
 * <p>{@code evaluationDate} defaults to the server's current date when absent --
 * a controller-boundary concern, not a rule reading the ambient clock (compare
 * {@link com.wealthguard.quality.domain.ValidationContext#evaluationDate()}).
 */
public record ValidateRequest(
        List<Position> positions,
        List<Client> clients,
        List<Instrument> instruments,
        List<TargetAllocation> targetAllocations,
        LocalDate evaluationDate) {

    public List<Position> positionsOrEmpty() {
        return positions == null ? List.of() : positions;
    }

    public List<Client> clientsOrEmpty() {
        return clients == null ? List.of() : clients;
    }

    public List<Instrument> instrumentsOrEmpty() {
        return instruments == null ? List.of() : instruments;
    }

    public List<TargetAllocation> targetAllocationsOrEmpty() {
        return targetAllocations == null ? List.of() : targetAllocations;
    }

    public LocalDate evaluationDateOrToday() {
        return evaluationDate == null ? LocalDate.now() : evaluationDate;
    }
}
