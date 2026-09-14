package com.wealthguard.quality.config;

import com.wealthguard.quality.api.ValidationController;
import com.wealthguard.quality.service.ValidationService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * The React frontend calls {@code /api/v1/validate} from a different origin
 * (the Vite dev server): without {@link WebConfig}, the browser's CORS
 * preflight would be rejected before the request ever reaches the
 * controller. This drives a real preflight through MockMvc rather than
 * asserting on the configuration bean directly, so it fails the way an
 * actual browser call would if the mapping regressed.
 */
@WebMvcTest(ValidationController.class)
class WebConfigTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private ValidationService validationService;

    @Test
    void allowsAPreflightRequestFromTheDefaultViteDevServerOrigin() throws Exception {
        mockMvc.perform(options("/api/v1/validate")
                        .header(HttpHeaders.ORIGIN, "http://localhost:5173")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .andExpect(status().isOk())
                .andExpect(header().string(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, "http://localhost:5173"));
    }

    @Test
    void rejectsAPreflightRequestFromAnUnlistedOrigin() throws Exception {
        mockMvc.perform(options("/api/v1/validate")
                        .header(HttpHeaders.ORIGIN, "http://evil.example.com")
                        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST"))
                .andExpect(status().isForbidden());
    }
}
