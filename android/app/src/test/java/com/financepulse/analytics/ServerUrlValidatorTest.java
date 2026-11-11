package com.financepulse.analytics;

import org.junit.Test;
import static org.junit.Assert.*;

public class ServerUrlValidatorTest {
    @Test
    public void normalizesHttpAndHttpsUrlsAndRejectsInvalidOnes() {
        assertEquals("http://192.168.1.25:5000", ServerUrlValidator.normalizeServerUrl("192.168.1.25:5000/"));
        assertEquals("https://pulse.example.com", ServerUrlValidator.normalizeServerUrl("  https://pulse.example.com/// "));
        assertNull(ServerUrlValidator.normalizeServerUrl(""));
        assertNull(ServerUrlValidator.normalizeServerUrl("ftp://example.com"));
        assertNull(ServerUrlValidator.normalizeServerUrl("javascript:alert(1)"));
    }

    @Test
    public void buildsHealthEndpointAndSafeExportFilename() {
        assertEquals("https://pulse.example.com/health", ServerUrlValidator.healthEndpoint("https://pulse.example.com/"));
        assertNull(ServerUrlValidator.healthEndpoint("   "));
        assertEquals("report_2026.csv", ServerUrlValidator.safeCsvFilename("report 2026"));
        assertEquals("finance_pulse_export.csv", ServerUrlValidator.safeCsvFilename(".."));
    }

    @Test
    public void preservesExactCanonicalTitle() {
        assertEquals(
            "Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform",
            ServerUrlValidator.APP_TITLE
        );
    }
}
