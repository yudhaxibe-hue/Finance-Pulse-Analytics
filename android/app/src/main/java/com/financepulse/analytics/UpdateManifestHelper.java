package com.financepulse.analytics;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/**
 * Pure-Java version comparison, manifest URL constants, and zip-slip safety helpers.
 */
public final class UpdateManifestHelper {
    public static final String DEFAULT_MANIFEST_URL =
            "https://github.com/yudhaxibe-hue/Finance-Pulse-Analytics/releases/download/v1.0.0/version.json";
    public static final String BUNDLED_VERSION_NAME = "1.2.0";

    private static final Set<String> ALLOWED_OTA_ENTRIES = Collections.unmodifiableSet(new HashSet<>(Arrays.asList(
            "mobile_app.html",
            "mobile_app.css",
            "mobile_app.js",
            "sample_data.js",
            "chart.umd.min.js",
            "favicon.svg",
            "finance_pulse_sample.csv"
    )));

    private UpdateManifestHelper() {}

    public static int[] parseVersionTuple(String raw) {
        if (raw == null || raw.trim().isEmpty()) {
            return new int[]{0, 0, 0, 0};
        }
        String clean = raw.trim();
        String plusPart = "";
        int plusIdx = clean.indexOf('+');
        if (plusIdx >= 0) {
            plusPart = clean.substring(plusIdx + 1);
            clean = clean.substring(0, plusIdx);
        }
        int dashIdx = clean.indexOf('-');
        if (dashIdx >= 0) {
            clean = clean.substring(0, dashIdx);
        }
        String[] parts = clean.split("\\.");
        int major = parseSafeInt(parts.length > 0 ? parts[0] : "0");
        int minor = parseSafeInt(parts.length > 1 ? parts[1] : "0");
        int patch = parseSafeInt(parts.length > 2 ? parts[2] : "0");
        int build = parseSafeInt(plusPart);
        return new int[]{major, minor, patch, build};
    }

    private static int parseSafeInt(String s) {
        if (s == null) return 0;
        StringBuilder digits = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (Character.isDigit(ch)) {
                digits.append(ch);
            } else {
                break;
            }
        }
        if (digits.length() == 0) return 0;
        try {
            return Integer.parseInt(digits.toString());
        } catch (NumberFormatException ignored) {
            return 0;
        }
    }

    public static int compareVersions(String left, String right) {
        int[] a = parseVersionTuple(left);
        int[] b = parseVersionTuple(right);
        for (int i = 0; i < 4; i++) {
            if (a[i] != b[i]) {
                return Integer.compare(a[i], b[i]);
            }
        }
        return 0;
    }

    public static boolean isApkUpdateAvailable(int localCode, String localName, int remoteCode, String remoteName) {
        if (remoteCode > 0 && localCode > 0 && remoteCode != localCode) {
            return remoteCode > localCode;
        }
        return compareVersions(remoteName, localName) > 0;
    }

    public static boolean isOtaUpdateAvailable(String localOtaVersion, String remoteOtaVersion) {
        if (remoteOtaVersion == null || remoteOtaVersion.trim().isEmpty()) {
            return false;
        }
        if (localOtaVersion == null || localOtaVersion.trim().isEmpty()) {
            return true;
        }
        return compareVersions(remoteOtaVersion, localOtaVersion) > 0;
    }

    public static String normalizeZipAssetName(String rawEntryName) {
        if (rawEntryName == null) {
            return null;
        }
        String normalized = rawEntryName.replace('\\', '/').trim();
        while (normalized.startsWith("./")) {
            normalized = normalized.substring(2);
        }
        if (normalized.contains("..") || normalized.contains("/")) {
            return null;
        }
        if (ALLOWED_OTA_ENTRIES.contains(normalized)) {
            return normalized;
        }
        return null;
    }

    public static boolean isSafeOtaEntryName(String rawEntryName) {
        return normalizeZipAssetName(rawEntryName) != null;
    }

    public static String bytesToHex(byte[] digest) {
        if (digest == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder(digest.length * 2);
        for (byte b : digest) {
            sb.append(String.format(Locale.US, "%02x", b & 0xff));
        }
        return sb.toString();
    }
}
