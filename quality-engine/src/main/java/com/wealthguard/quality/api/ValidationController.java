package com.wealthguard.quality.api;

import com.wealthguard.quality.api.dto.RuleSummary;
import com.wealthguard.quality.api.dto.ValidateRequest;
import com.wealthguard.quality.domain.ValidationReport;
import com.wealthguard.quality.service.ValidationService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

/**
 * HTTP boundary of the quality engine (cahier des charges §2.2: {@code POST
 * /validate}). Deliberately thin: request mapping and defaulting only,
 * everything else delegates to {@link ValidationService}, so this class has no
 * business logic to unit-test on its own -- only the mapping, which is what
 * {@code ValidationControllerTest} checks.
 */
@RestController
@RequestMapping("/api/v1")
public class ValidationController {

    private final ValidationService validationService;

    public ValidationController(ValidationService validationService) {
        this.validationService = validationService;
    }

    @PostMapping("/validate")
    public ValidationReport validate(@RequestBody ValidateRequest request) {
        return validationService.validate(
                request.positionsOrEmpty(),
                request.clientsOrEmpty(),
                request.instrumentsOrEmpty(),
                request.targetAllocationsOrEmpty(),
                request.evaluationDateOrToday());
    }

    /** Discovery endpoint: what the engine currently checks, and with which parameters. */
    @GetMapping("/rules")
    public List<RuleSummary> rules() {
        return validationService.ruleDefinitions().stream().map(RuleSummary::from).toList();
    }
}
