package com.financepulse.analytics;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;

/**
 * Pure URL and filename validation helpers for Finance Pulse Analytics Android wrapper.
 */
public final class ServerUrlValidator {
    public static final String LOCAL_ASSET_URL = "file:///android_asset/mobile_app.html";
    public static final String APP_TITLE =
        "Finance Pulse Analytics: Enterprise Financial Performance Intelligence and Profitability Optimization Analytics Platform";

    private ServerUrlValidator() {}

    /**
     * Normalize a user-supplied server URL into a safe http:// or https:// base URL.
     * Returns null if empty or invalid.
     */
    public static String normalizeServerUrl(String raw) {
        if (raw == null) {
            return null;
        }
        String trimmed = raw.trim();
        if (trimmed.isEmpty()) {
            return null;
        }
        String lower = trimmed.toLowerCase(Locale.US);
        if (lower.startsWith("javascript:") || lower.startsWith("data:") || lower.startsWith("vbscript:")) {
            return null;
        }
        if (trimmed.contains("://")) {
            if (!lower.startsWith("http://") && !lower.startsWith("https://")) {
                return null;
            }
        } else {
            trimmed = "http://" + trimmed;
        }
        while (trimmed.endsWith("/")) {
            trimmed = trimmed.substring(0, trimmed.length() - 1);
        }
        try {
            URI uri = new URI(trimmed);
            String scheme = uri.getScheme();
            String host = uri.getHost();
            if (scheme == null || host == null || host.trim().isEmpty()) {
                return null;
            }
            if (!"http".equalsIgnoreCase(scheme) && !"https".equalsIgnoreCase(scheme)) {
                return null;
            }
            return trimmed;
        } catch (URISyntaxException ignored) {
            return null;
        }
    }

    /**
     * Build health check URL for a normalized or raw server URL.
     */
    public static String healthEndpoint(String raw) {
        String normalized = normalizeServerUrl(raw);
        return normalized == null ? null : normalized + "/health";
    }

    /**
     * Return a safe CSV filename fallback for exports.
     */
    public static String safeCsvFilename(String candidate) {
        String cleaned = candidate == null ? "" : candidate.replaceAll("[^A-Za-z0-9._-]", "_");
        if (cleaned.isEmpty() || ".".equals(cleaned) || "..".equals(cleaned)) {
            return "finance_pulse_export.csv";
        }
        if (!cleaned.toLowerCase(Locale.US).endsWith(".csv")) {
            cleaned = cleaned + ".csv";
        }
        return cleaned;
    }
}
