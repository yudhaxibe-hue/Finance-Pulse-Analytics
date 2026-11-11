package com.financepulse.analytics;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.os.Build;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Coordinates automatic wireless sync config, Layer-1 OTA web-asset swaps,
 * and Layer-2 SHA-256 verified APK upgrades without leaving the app.
 */
public final class AppUpdater {
    public static final String PREFS_NAME = "finance_pulse_prefs";
    public static final String KEY_SERVER_URL = "server_url";
    public static final String KEY_SYNC_OVERRIDE = "sync_override_url";
    public static final String KEY_SYNC_MANIFEST = "sync_manifest_url";
    public static final String KEY_OTA_VERSION = "ota_version";
    public static final String KEY_OTA_APK_CODE = "ota_apk_code";

    private final Context context;
    private final SharedPreferences prefs;

    private volatile boolean checked = false;
    private volatile boolean checking = false;
    private volatile boolean otaReadyToReload = false;
    private volatile boolean apkUpdateAvailable = false;
    private volatile String latestVersionName = "";
    private volatile int latestVersionCode = 0;
    private volatile String latestApkUrl = "";
    private volatile String latestApkSha256 = "";
    private volatile String latestOtaVersion = "";
    private volatile String lastError = "";
    private volatile String downloadStatus = "idle";
    private volatile File downloadedApkFile = null;

    public interface UpdateListener {
        void onUpdateStateChanged(String statusJson);
    }

    public AppUpdater(Context context) {
        this.context = context.getApplicationContext();
        this.prefs = this.context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    public int getInstalledVersionCode() {
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                return (int) info.getLongVersionCode();
            }
            return info.versionCode;
        } catch (Exception ignored) {
            return BuildConfig.VERSION_CODE;
        }
    }

    public String getInstalledVersionName() {
        try {
            PackageInfo info = context.getPackageManager().getPackageInfo(context.getPackageName(), 0);
            if (info.versionName != null && !info.versionName.isEmpty()) {
                return info.versionName;
            }
        } catch (Exception ignored) {
        }
        return BuildConfig.VERSION_NAME;
    }

    public String getBaselineVersionString() {
        return getInstalledVersionName() + "+" + getInstalledVersionCode();
    }

    public String getActiveWebVersionString() {
        int otaForCode = prefs.getInt(KEY_OTA_APK_CODE, -1);
        String otaVer = prefs.getString(KEY_OTA_VERSION, "");
        if (otaForCode == getInstalledVersionCode() && !otaVer.isEmpty() && isValidOtaDir(otaLiveDir())) {
            return otaVer;
        }
        return getBaselineVersionString();
    }

    public File otaLiveDir() {
        return new File(context.getFilesDir(), "ota_live");
    }

    public String getLaunchAssetUrl() {
        int otaForCode = prefs.getInt(KEY_OTA_APK_CODE, -1);
        int localCode = getInstalledVersionCode();
        File liveDir = otaLiveDir();
        if (otaForCode == localCode && isValidOtaDir(liveDir)) {
            File index = new File(liveDir, "mobile_app.html");
            return "file://" + index.getAbsolutePath();
        }
        // Invalidate outdated OTA cache after native APK upgrade
        if (otaForCode > 0 && otaForCode != localCode) {
            deleteRecursive(liveDir);
            prefs.edit().remove(KEY_OTA_VERSION).remove(KEY_OTA_APK_CODE).apply();
        }
        return ServerUrlValidator.LOCAL_ASSET_URL;
    }

    public boolean isLocalWorkspaceUrl(String url) {
        if (url == null) return false;
        if (url.startsWith("file:///android_asset/")) return true;
        String otaPrefix = "file://" + otaLiveDir().getAbsolutePath();
        return url.startsWith(otaPrefix);
    }

    public String getSyncOverrideUrl() {
        return ServerUrlValidator.normalizeServerUrl(prefs.getString(KEY_SYNC_OVERRIDE, ""));
    }

    public String getManifestSyncUrl() {
        return ServerUrlValidator.normalizeServerUrl(prefs.getString(KEY_SYNC_MANIFEST, ""));
    }

    public String resolveEffectiveSyncUrl() {
        String overrideUrl = getSyncOverrideUrl();
        if (overrideUrl != null) return overrideUrl;
        String manifestSync = getManifestSyncUrl();
        return manifestSync == null ? "" : manifestSync;
    }

    public boolean setSyncOverrideUrl(String rawUrl) {
        String clean = rawUrl == null ? "" : rawUrl.trim();
        if (clean.isEmpty()) {
            prefs.edit().remove(KEY_SYNC_OVERRIDE).apply();
            return true;
        }
        String norm = ServerUrlValidator.normalizeServerUrl(clean);
        if (norm == null) {
            return false;
        }
        prefs.edit().putString(KEY_SYNC_OVERRIDE, norm).apply();
        return true;
    }

    public String getSyncStatusJson() {
        JSONObject out = new JSONObject();
        try {
            String overrideUrl = getSyncOverrideUrl();
            String manifestUrl = getManifestSyncUrl();
            String effective = resolveEffectiveSyncUrl();
            out.put("overrideUrl", overrideUrl == null ? "" : overrideUrl);
            out.put("manifestSyncUrl", manifestUrl == null ? "" : manifestUrl);
            out.put("effectiveUrl", effective);
            out.put("mode", overrideUrl != null ? "Manual override" : (!effective.isEmpty() ? "Automatic wireless sync" : "Offline local"));
            out.put("savedServerUrl", prefs.getString(KEY_SERVER_URL, ""));
        } catch (Exception ignored) {
        }
        return out.toString();
    }

    public String getStatusJson() {
        JSONObject out = new JSONObject();
        try {
            out.put("checked", checked);
            out.put("checking", checking);
            out.put("installedVersion", getInstalledVersionName());
            out.put("installedCode", getInstalledVersionCode());
            out.put("baselineVersion", getBaselineVersionString());
            out.put("activeOtaVersion", getActiveWebVersionString());
            out.put("otaReadyToReload", otaReadyToReload);
            out.put("apkUpdateAvailable", apkUpdateAvailable);
            out.put("updateAvailable", otaReadyToReload || apkUpdateAvailable);
            out.put("latestVersion", latestVersionName.isEmpty() ? getInstalledVersionName() : latestVersionName);
            out.put("latestCode", latestVersionCode > 0 ? latestVersionCode : getInstalledVersionCode());
            out.put("latestOtaVersion", latestOtaVersion);
            out.put("downloadStatus", downloadStatus);
            out.put("error", lastError);
            out.put("effectiveSyncUrl", resolveEffectiveSyncUrl());
        } catch (Exception ignored) {
        }
        return out.toString();
    }

    public void markOtaApplied() {
        otaReadyToReload = false;
    }

    public void checkInBackground(UpdateListener listener) {
        if (checking) return;
        new Thread(() -> {
            runUpdateCheck();
            if (listener != null) {
                listener.onUpdateStateChanged(getStatusJson());
            }
        }, "FP-AppUpdater").start();
    }

    public String runUpdateCheck() {
        checking = true;
        lastError = "";
        try {
            byte[] raw = downloadBytesWithRedirects(UpdateManifestHelper.DEFAULT_MANIFEST_URL, 5000, 1024 * 512);
            JSONObject manifest = new JSONObject(new String(raw, StandardCharsets.UTF_8));

            String manifestSync = ServerUrlValidator.normalizeServerUrl(manifest.optString("sync_server_url", ""));
            if (manifestSync != null) {
                prefs.edit().putString(KEY_SYNC_MANIFEST, manifestSync).apply();
            } else if (manifest.has("sync_server_url")) {
                prefs.edit().remove(KEY_SYNC_MANIFEST).apply();
            }

            JSONObject androidObj = manifest.optJSONObject("android");
            if (androidObj != null) {
                int remoteCode = androidObj.optInt("version_code", manifest.optInt("build_number", 0));
                String remoteName = androidObj.optString("version_name", manifest.optString("version", ""));
                String apkUrl = androidObj.optString("apk_url", "");
                String apkSha = androidObj.optString("apk_sha256", "");
                latestVersionCode = remoteCode;
                latestVersionName = remoteName;
                latestApkUrl = apkUrl;
                latestApkSha256 = apkSha;

                apkUpdateAvailable = !apkUrl.isEmpty() && UpdateManifestHelper.isApkUpdateAvailable(
                        getInstalledVersionCode(),
                        getInstalledVersionName(),
                        remoteCode,
                        remoteName
                );

                // Check Layer-1 OTA web assets bundle
                JSONObject otaObj = androidObj.optJSONObject("ota");
                if (otaObj != null) {
                    String remoteOtaVer = otaObj.optString("version", "");
                    String otaZipUrl = otaObj.optString("zip_url", "");
                    String otaZipSha = otaObj.optString("zip_sha256", "");
                    latestOtaVersion = remoteOtaVer;
                    String currentWebVer = getActiveWebVersionString();
                    if (!otaZipUrl.isEmpty() && UpdateManifestHelper.isOtaUpdateAvailable(currentWebVer, remoteOtaVer)) {
                        if (downloadAndStageOtaZip(otaZipUrl, otaZipSha, remoteOtaVer)) {
                            otaReadyToReload = true;
                        }
                    }
                }
            }
        } catch (Exception ex) {
            lastError = ex.getMessage() == null ? "Offline" : ex.getMessage();
        } finally {
            checked = true;
            checking = false;
        }
        return getStatusJson();
    }

    private boolean downloadAndStageOtaZip(String zipUrl, String expectedSha256, String remoteOtaVer) {
        if (zipUrl == null || !zipUrl.startsWith("https://")) {
            return false;
        }
        File updatesDir = new File(context.getFilesDir(), "updates");
        if (!updatesDir.exists()) updatesDir.mkdirs();
        File zipFile = new File(updatesDir, "ota_bundle.zip.part");
        File stagingDir = new File(context.getFilesDir(), "ota_staging");
        deleteRecursive(stagingDir);
        stagingDir.mkdirs();

        try {
            downloadFileVerified(zipUrl, zipFile, expectedSha256, 8000);
            try (ZipInputStream zis = new ZipInputStream(new FileInputStream(zipFile))) {
                byte[] buf = new byte[8192];
                ZipEntry entry;
                while ((entry = zis.getNextEntry()) != null) {
                    if (entry.isDirectory()) {
                        zis.closeEntry();
                        continue;
                    }
                    String safeName = UpdateManifestHelper.normalizeZipAssetName(entry.getName());
                    if (safeName != null) {
                        File outFile = new File(stagingDir, safeName);
                        try (FileOutputStream fos = new FileOutputStream(outFile)) {
                            int len;
                            while ((len = zis.read(buf)) > 0) {
                                fos.write(buf, 0, len);
                            }
                        }
                    }
                    zis.closeEntry();
                }
            }
            if (!isValidOtaDir(stagingDir)) {
                deleteRecursive(stagingDir);
                return false;
            }
            File liveDir = otaLiveDir();
            File backupDir = new File(context.getFilesDir(), "ota_prev");
            deleteRecursive(backupDir);
            boolean movedBackup = liveDir.exists() && liveDir.renameTo(backupDir);
            if (liveDir.exists()) {
                deleteRecursive(liveDir);
            }
            if (!stagingDir.renameTo(liveDir)) {
                deleteRecursive(stagingDir);
                if (movedBackup && !liveDir.exists()) {
                    backupDir.renameTo(liveDir);
                }
                return false;
            }
            deleteRecursive(backupDir);
            prefs.edit()
                    .putString(KEY_OTA_VERSION, remoteOtaVer)
                    .putInt(KEY_OTA_APK_CODE, getInstalledVersionCode())
                    .apply();
            zipFile.delete();
            return true;
        } catch (Exception ex) {
            lastError = "OTA skipped: " + ex.getMessage();
            deleteRecursive(stagingDir);
            zipFile.delete();
            return false;
        }
    }

    public File downloadVerifiedApkUpdate() {
        if (latestApkUrl == null || !latestApkUrl.startsWith("https://")) {
            downloadStatus = "error";
            lastError = "APK update URL unavailable.";
            return null;
        }
        File updatesDir = new File(context.getFilesDir(), "updates");
        if (!updatesDir.exists()) updatesDir.mkdirs();
        File partFile = new File(updatesDir, "FinancePulseAnalytics-update.apk.part");
        File finalApk = new File(updatesDir, "FinancePulseAnalytics-update.apk");
        downloadStatus = "downloading";
        try {
            downloadFileVerified(latestApkUrl, partFile, latestApkSha256, 30000);
            if (finalApk.exists()) finalApk.delete();
            if (!partFile.renameTo(finalApk)) {
                throw new IOException("Unable to finalize downloaded APK");
            }
            downloadedApkFile = finalApk;
            downloadStatus = "ready";
            lastError = "";
            return finalApk;
        } catch (Exception ex) {
            partFile.delete();
            downloadStatus = "error";
            lastError = ex.getMessage() == null ? "Download failed" : ex.getMessage();
            return null;
        }
    }

    public File getDownloadedApkFile() {
        return downloadedApkFile != null && downloadedApkFile.isFile() ? downloadedApkFile : null;
    }

    public String nativeHttpJson(String method, String urlStr, String bodyJson, String bearerToken) {
        JSONObject out = new JSONObject();
        String normMethod = "GET".equalsIgnoreCase(method) ? "GET" : "POST";
        String cleanUrl = urlStr == null ? "" : urlStr.trim();
        if (!(cleanUrl.startsWith("http://") || cleanUrl.startsWith("https://"))) {
            try {
                out.put("ok", false).put("status", 0).put("error", "Invalid HTTP URL");
            } catch (Exception ignored) {}
            return out.toString();
        }
        HttpURLConnection conn = null;
        try {
            URL url = new URL(cleanUrl);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod(normMethod);
            conn.setConnectTimeout(4500);
            conn.setReadTimeout(7000);
            conn.setRequestProperty("Accept", "application/json");
            conn.setRequestProperty("User-Agent", "FinancePulseAndroid/" + getInstalledVersionName());
            if (bearerToken != null && !bearerToken.isEmpty()) {
                conn.setRequestProperty("Authorization", "Bearer " + bearerToken);
            }
            if ("POST".equals(normMethod)) {
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
                byte[] payload = (bodyJson == null ? "{}" : bodyJson).getBytes(StandardCharsets.UTF_8);
                try (OutputStream os = conn.getOutputStream()) {
                    os.write(payload);
                }
            }
            int code = conn.getResponseCode();
            InputStream stream = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String respText = stream == null ? "{}" : new String(readAllBytes(stream, 1024 * 1024), StandardCharsets.UTF_8);
            out.put("ok", code >= 200 && code < 300);
            out.put("status", code);
            try {
                out.put("data", new JSONObject(respText));
            } catch (Exception ignored) {
                out.put("raw", respText);
            }
        } catch (Exception ex) {
            try {
                out.put("ok", false).put("status", 0).put("error", ex.getMessage() == null ? "Network unreachable" : ex.getMessage());
            } catch (Exception ignored) {}
        } finally {
            if (conn != null) conn.disconnect();
        }
        return out.toString();
    }

    private static boolean isValidOtaDir(File dir) {
        if (!dir.isDirectory()) return false;
        String[] req = {"mobile_app.html", "mobile_app.css", "mobile_app.js", "sample_data.js", "chart.umd.min.js"};
        for (String name : req) {
            File f = new File(dir, name);
            if (!f.isFile() || f.length() == 0) return false;
        }
        return true;
    }

    private static void deleteRecursive(File target) {
        if (target == null || !target.exists()) return;
        File[] children = target.listFiles();
        if (children != null) {
            for (File child : children) {
                deleteRecursive(child);
            }
        }
        target.delete();
    }

    private byte[] downloadBytesWithRedirects(String urlStr, int timeoutMs, int maxBytes) throws IOException {
        HttpURLConnection conn = openWithRedirects(urlStr, timeoutMs);
        try {
            int code = conn.getResponseCode();
            if (code != HttpURLConnection.HTTP_OK) {
                throw new IOException("HTTP " + code);
            }
            return readAllBytes(conn.getInputStream(), maxBytes);
        } finally {
            conn.disconnect();
        }
    }

    private void downloadFileVerified(String urlStr, File destFile, String expectedSha256, int timeoutMs) throws Exception {
        HttpURLConnection conn = openWithRedirects(urlStr, timeoutMs);
        try {
            int code = conn.getResponseCode();
            if (code != HttpURLConnection.HTTP_OK) {
                throw new IOException("Download HTTP " + code);
            }
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] buf = new byte[16384];
            try (InputStream in = conn.getInputStream(); FileOutputStream fos = new FileOutputStream(destFile)) {
                int n;
                while ((n = in.read(buf)) > 0) {
                    md.update(buf, 0, n);
                    fos.write(buf, 0, n);
                }
            }
            if (expectedSha256 != null && !expectedSha256.trim().isEmpty()) {
                String actual = UpdateManifestHelper.bytesToHex(md.digest());
                if (!actual.equalsIgnoreCase(expectedSha256.trim())) {
                    destFile.delete();
                    throw new IOException("SHA-256 mismatch");
                }
            }
        } finally {
            conn.disconnect();
        }
    }

    private HttpURLConnection openWithRedirects(String initialUrl, int timeoutMs) throws IOException {
        String current = initialUrl;
        for (int hops = 0; hops < 6; hops++) {
            URL url = new URL(current);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setInstanceFollowRedirects(false);
            conn.setConnectTimeout(timeoutMs);
            conn.setReadTimeout(timeoutMs * 2);
            conn.setRequestProperty("User-Agent", "FinancePulseAndroid/" + getInstalledVersionName());
            int code = conn.getResponseCode();
            if (code == HttpURLConnection.HTTP_MOVED_PERM
                    || code == HttpURLConnection.HTTP_MOVED_TEMP
                    || code == HttpURLConnection.HTTP_SEE_OTHER
                    || code == 307
                    || code == 308) {
                String loc = conn.getHeaderField("Location");
                conn.disconnect();
                if (loc == null || loc.isEmpty()) {
                    throw new IOException("Empty redirect location");
                }
                URL nextUrl = new URL(url, loc);
                if ("https".equalsIgnoreCase(url.getProtocol()) && !"https".equalsIgnoreCase(nextUrl.getProtocol())) {
                    throw new IOException("Blocked insecure redirect downgrade");
                }
                current = nextUrl.toString();
                continue;
            }
            return conn;
        }
        throw new IOException("Too many redirects");
    }

    private static byte[] readAllBytes(InputStream is, int maxBytes) throws IOException {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int total = 0;
        int n;
        while ((n = is.read(buf)) > 0) {
            total += n;
            if (total > maxBytes) {
                throw new IOException("Response exceeds max allowed size");
            }
            baos.write(buf, 0, n);
        }
        return baos.toByteArray();
    }
}
