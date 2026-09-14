package com.wealthguard.quality.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import java.util.List;

/**
 * CORS for the React frontend (cahier des charges §2.5): the browser calls
 * {@code POST /api/v1/validate} directly from a different origin (the Vite
 * dev server, or wherever the built SPA is hosted), so without this every
 * request would be blocked by the browser before it ever reaches Spring.
 *
 * <p>The allowed origins are configuration, not a hardcoded {@code
 * localhost:5173}, so a deployed frontend only needs an environment variable
 * change, never a rebuild of this jar -- the same principle already applied
 * to the rule set in {@code quality-rules.yml}.
 */
@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final List<String> allowedOrigins;

    public WebConfig(
            @Value("${wealthguard.cors.allowed-origins:http://localhost:5173,http://localhost:4173}")
            List<String> allowedOrigins) {
        this.allowedOrigins = allowedOrigins;
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins(allowedOrigins.toArray(new String[0]))
                .allowedMethods("GET", "POST")
                .allowedHeaders("*");
    }
}
