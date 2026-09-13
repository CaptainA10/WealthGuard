package com.wealthguard.quality.api;

import com.wealthguard.quality.domain.Anomaly;
import com.wealthguard.quality.domain.Position;
import com.wealthguard.quality.domain.RuleCategory;
import com.wealthguard.quality.domain.Severity;
import com.wealthguard.quality.domain.ValidationContext;
import com.wealthguard.quality.domain.ValidationReport;
import com.wealthguard.quality.rules.RuleDefinition;
import com.wealthguard.quality.rules.RuleParameters;
import com.wealthguard.quality.service.ValidationService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ValidationController.class)
class ValidationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ValidationService validationService;

    @Test
    void postValidateReturnsTheReportBuiltByTheService() throws Exception {
        ValidationContext emptyContext = new ValidationContext(
                List.of(), List.of(), List.of(), List.of(), LocalDate.of(2024, 1, 1));
        ValidationReport report = ValidationReport.of(
                "report-1", Instant.parse("2024-01-01T00:00:00Z"), emptyContext,
                List.of("POS_REQUIRED_FIELDS"),
                List.of(new Anomaly(
                        "POS_REQUIRED_FIELDS", "label", RuleCategory.COMPLETUDE, Severity.BLOQUANT,
                        "positions", "position_id=P1", "clientId", null, "msg", "impact", "fix")),
                12L);
        when(validationService.validate(any(), any(), any(), any(), any())).thenReturn(report);

        mockMvc.perform(post("/api/v1/validate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "positions": [
                                    {"positionId": "P1", "clientId": null, "ticker": "AAPL",
                                     "quantity": 10, "purchasePrice": 100, "purchaseDate": "2024-01-01",
                                     "currency": "USD"}
                                  ],
                                  "evaluationDate": "2024-06-15"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reportId").value("report-1"))
                .andExpect(jsonPath("$.counts.anomalies").value(1))
                .andExpect(jsonPath("$.anomalies[0].ruleId").value("POS_REQUIRED_FIELDS"));

        verify(validationService).validate(
                any(), any(), any(), any(), eq(LocalDate.of(2024, 6, 15)));
    }

    @Test
    void postValidateDefaultsTheEvaluationDateWhenAbsent() throws Exception {
        ValidationContext emptyContext = new ValidationContext(
                List.of(), List.of(), List.of(), List.of(), LocalDate.now());
        when(validationService.validate(any(), any(), any(), any(), any()))
                .thenReturn(ValidationReport.of("r", Instant.now(), emptyContext, List.of(), List.of(), 0L));

        mockMvc.perform(post("/api/v1/validate")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isOk());

        verify(validationService).validate(eq(List.<Position>of()), any(), any(), any(), eq(LocalDate.now()));
    }

    @Test
    void getRulesFlattensParametersToAPlainMap() throws Exception {
        RuleDefinition definition = new RuleDefinition(
                "POS_POSITIVE_QUANTITY", "Quantite positive", RuleCategory.COHERENCE_METIER, Severity.BLOQUANT,
                "desc", RuleParameters.of(java.util.Map.of("minExclusive", "0"), "POS_POSITIVE_QUANTITY"));
        when(validationService.ruleDefinitions()).thenReturn(List.of(definition));

        mockMvc.perform(get("/api/v1/rules"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("POS_POSITIVE_QUANTITY"))
                .andExpect(jsonPath("$[0].parameters.minExclusive").value("0"));
    }
}
