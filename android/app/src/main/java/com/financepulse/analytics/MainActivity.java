package com.financepulse.analytics;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER_REQUEST_CODE = 1001;

    private WebView webView;
    private Button returnOfflineBtn;
    private ValueCallback<Uri[]> filePathCallback;
    private AppUpdater updater;
    private File pendingInstallAfterPermission;

    @SuppressLint({"SetJavaScriptEnabled"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setTitle(getString(R.string.app_name));
        updater = new AppUpdater(this);

        FrameLayout root = new FrameLayout(this);
        root.setLayoutParams(new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        webView = new WebView(this);
        webView.setLayoutParams(new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        ));

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowFileAccessFromFileURLs(true);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);

        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true);

        webView.addJavascriptInterface(new AndroidBridge(), "AndroidBridge");

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                boolean isLocal = updater.isLocalWorkspaceUrl(url);
                returnOfflineBtn.setVisibility(isLocal ? View.GONE : View.VISIBLE);
                if (isLocal) {
                    pushUpdateStateToWebView(updater.getStatusJson());
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request != null && request.isForMainFrame()) {
                    String currentUrl = request.getUrl() != null ? request.getUrl().toString() : "";
                    if (!updater.isLocalWorkspaceUrl(currentUrl)) {
                        Toast.makeText(
                                MainActivity.this,
                                "Server unreachable. Returned to local offline workspace.",
                                Toast.LENGTH_LONG
                        ).show();
                        loadLocalWorkspace();
                    }
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                    WebView view,
                    ValueCallback<Uri[]> callback,
                    FileChooserParams fileChooserParams
            ) {
                if (filePathCallback != null) {
                    filePathCallback.onReceiveValue(null);
                }
                filePathCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{
                        "text/csv", "text/comma-separated-values", "application/json",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "text/plain"
                });
                try {
                    startActivityForResult(intent, FILE_CHOOSER_REQUEST_CODE);
                } catch (Exception ex) {
                    filePathCallback = null;
                    Toast.makeText(MainActivity.this, "No file picker available on device.", Toast.LENGTH_SHORT).show();
                    return false;
                }
                return true;
            }
        });

        webView.setDownloadListener(new DownloadListener() {
            @Override
            public void onDownloadStart(
                    String url,
                    String userAgent,
                    String contentDisposition,
                    String mimetype,
                    long contentLength
            ) {
                if (url == null || url.startsWith("blob:") || url.startsWith("file:")) {
                    return;
                }
                try {
                    DownloadManager.Request request = new DownloadManager.Request(Uri.parse(url));
                    request.setMimeType(mimetype);
                    String cookies = CookieManager.getInstance().getCookie(url);
                    if (cookies != null) {
                        request.addRequestHeader("Cookie", cookies);
                    }
                    request.addRequestHeader("User-Agent", userAgent);
                    String filename = URLUtil.guessFileName(url, contentDisposition, mimetype);
                    request.setTitle(filename);
                    request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                    request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, filename);
                    DownloadManager dm = (DownloadManager) getSystemService(Context.DOWNLOAD_SERVICE);
                    if (dm != null) {
                        dm.enqueue(request);
                        Toast.makeText(MainActivity.this, "Downloading " + filename, Toast.LENGTH_SHORT).show();
                    }
                } catch (Exception ex) {
                    Toast.makeText(MainActivity.this, "Download unavailable: " + ex.getMessage(), Toast.LENGTH_SHORT).show();
                }
            }
        });

        returnOfflineBtn = new Button(this);
        returnOfflineBtn.setText("Return Local");
        returnOfflineBtn.setAllCaps(false);
        returnOfflineBtn.setTextSize(12f);
        returnOfflineBtn.setTextColor(0xFFFFFFFF);
        returnOfflineBtn.setBackgroundColor(0xE61D1D1F);
        int padH = Math.round(14 * getResources().getDisplayMetrics().density);
        int padV = Math.round(7 * getResources().getDisplayMetrics().density);
        returnOfflineBtn.setPadding(padH, padV, padH, padV);
        FrameLayout.LayoutParams btnParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT,
                ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.END
        );
        int margin = Math.round(16 * getResources().getDisplayMetrics().density);
        btnParams.setMargins(margin, margin, margin, margin);
        returnOfflineBtn.setLayoutParams(btnParams);
        returnOfflineBtn.setVisibility(View.GONE);
        returnOfflineBtn.setOnClickListener(v -> {
            clearSavedServerUrl();
            loadLocalWorkspace();
        });

        root.addView(webView);
        root.addView(returnOfflineBtn);
        setContentView(root);

        String savedServer = getSavedServerUrl();
        if (savedServer != null) {
            webView.loadUrl(savedServer);
        } else {
            loadLocalWorkspace();
        }

        updater.checkInBackground(this::pushUpdateStateToWebView);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (pendingInstallAfterPermission != null
                && (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || getPackageManager().canRequestPackageInstalls())) {
            File ready = pendingInstallAfterPermission;
            pendingInstallAfterPermission = null;
            launchApkInstaller(ready);
        }
    }

    private void loadLocalWorkspace() {
        String launchUrl = updater.getLaunchAssetUrl();
        try {
            webView.loadUrl(launchUrl);
        } catch (Exception ignored) {
            webView.loadUrl(ServerUrlValidator.LOCAL_ASSET_URL);
        }
    }

    private void pushUpdateStateToWebView(String statusJson) {
        if (webView == null || statusJson == null) return;
        runOnUiThread(() -> {
            String currentUrl = webView.getUrl();
            if (currentUrl == null || updater.isLocalWorkspaceUrl(currentUrl)) {
                String jsArg = JSONObject.quote(statusJson);
                webView.evaluateJavascript(
                        "if(window.onNativeUpdateState){window.onNativeUpdateState(" + jsArg + ");}",
                        null
                );
            }
        });
    }

    private void launchApkInstaller(File apkFile) {
        if (apkFile == null || !apkFile.isFile()) return;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !getPackageManager().canRequestPackageInstalls()) {
            pendingInstallAfterPermission = apkFile;
            Toast.makeText(
                    this,
                    "Enable 'Install unknown apps' to finish updating " + getString(R.string.app_name),
                    Toast.LENGTH_LONG
            ).show();
            try {
                Intent permIntent = new Intent(
                        Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                        Uri.parse("package:" + getPackageName())
                );
                startActivity(permIntent);
            } catch (Exception ex) {
                pendingInstallAfterPermission = null;
            }
            return;
        }
        try {
            Uri contentUri = ApkFileProvider.uriForUpdateApk(this, apkFile);
            Intent installIntent = new Intent(Intent.ACTION_VIEW);
            installIntent.setDataAndType(contentUri, "application/vnd.android.package-archive");
            installIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            startActivity(installIntent);
        } catch (Exception ex) {
            Toast.makeText(this, "Installer failed to launch: " + ex.getMessage(), Toast.LENGTH_LONG).show();
        }
    }

    private String getSavedServerUrl() {
        SharedPreferences prefs = getSharedPreferences(AppUpdater.PREFS_NAME, MODE_PRIVATE);
        return ServerUrlValidator.normalizeServerUrl(prefs.getString(AppUpdater.KEY_SERVER_URL, ""));
    }

    private void clearSavedServerUrl() {
        getSharedPreferences(AppUpdater.PREFS_NAME, MODE_PRIVATE).edit().remove(AppUpdater.KEY_SERVER_URL).apply();
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER_REQUEST_CODE && filePathCallback != null) {
            Uri[] results = null;
            if (resultCode == Activity.RESULT_OK && data != null && data.getData() != null) {
                results = new Uri[]{data.getData()};
            }
            filePathCallback.onReceiveValue(results);
            filePathCallback = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }

    public class AndroidBridge {
        @JavascriptInterface
        public String getAppName() {
            return getString(R.string.app_name);
        }

        @JavascriptInterface
        public String getAppTitle() {
            return ServerUrlValidator.APP_TITLE;
        }

        @JavascriptInterface
        public String getSavedServer() {
            String saved = getSavedServerUrl();
            return saved == null ? "" : saved;
        }

        @JavascriptInterface
        public boolean connectServer(String rawUrl) {
            String normalized = ServerUrlValidator.normalizeServerUrl(rawUrl);
            if (normalized == null) {
                return false;
            }
            getSharedPreferences(AppUpdater.PREFS_NAME, MODE_PRIVATE).edit().putString(AppUpdater.KEY_SERVER_URL, normalized).apply();
            runOnUiThread(() -> webView.loadUrl(normalized));
            return true;
        }

        @JavascriptInterface
        public void disconnectServer() {
            clearSavedServerUrl();
            runOnUiThread(MainActivity.this::loadLocalWorkspace);
        }

        @JavascriptInterface
        public String getUpdateStatusJson() {
            return updater.getStatusJson();
        }

        @JavascriptInterface
        public void checkForUpdates() {
            new Thread(() -> {
                String json = updater.runUpdateCheck();
                pushUpdateStateToWebView(json);
            }, "FP-ManualCheck").start();
        }

        @JavascriptInterface
        public void applyOtaNow() {
            updater.markOtaApplied();
            runOnUiThread(MainActivity.this::loadLocalWorkspace);
        }

        @JavascriptInterface
        public void installApkUpdate() {
            new Thread(() -> {
                File apk = updater.downloadVerifiedApkUpdate();
                pushUpdateStateToWebView(updater.getStatusJson());
                if (apk != null) {
                    runOnUiThread(() -> launchApkInstaller(apk));
                }
            }, "FP-ApkDownload").start();
        }

        @JavascriptInterface
        public String getSyncStatusJson() {
            return updater.getSyncStatusJson();
        }

        @JavascriptInterface
        public boolean setSyncOverrideUrl(String rawUrl) {
            boolean ok = updater.setSyncOverrideUrl(rawUrl);
            if (ok) {
                pushUpdateStateToWebView(updater.getStatusJson());
            }
            return ok;
        }

        @JavascriptInterface
        public String nativeHttpJson(String method, String urlStr, String bodyJson, String bearerToken) {
            return updater.nativeHttpJson(method, urlStr, bodyJson, bearerToken);
        }

        @JavascriptInterface
        public void nativeHttpAsync(String reqId, String method, String urlStr, String bodyJson, String bearerToken) {
            new Thread(() -> {
                String resJson = updater.nativeHttpJson(method, urlStr, bodyJson, bearerToken);
                runOnUiThread(() -> {
                    if (webView != null) {
                        String quotedId = JSONObject.quote(reqId == null ? "" : reqId);
                        String quotedRes = JSONObject.quote(resJson == null ? "{}" : resJson);
                        webView.evaluateJavascript(
                                "if(window.__fpNativeHttpCb){window.__fpNativeHttpCb(" + quotedId + "," + quotedRes + ");}",
                                null
                        );
                    }
                });
            }, "FP-HttpSync").start();
        }

        @JavascriptInterface
        public boolean saveCsvExport(String rawFilename, String csvContent) {
            String filename = ServerUrlValidator.safeCsvFilename(rawFilename);
            try {
                File outDir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                if (outDir == null) {
                    outDir = getFilesDir();
                }
                if (!outDir.exists()) {
                    outDir.mkdirs();
                }
                File outFile = new File(outDir, filename);
                try (FileOutputStream fos = new FileOutputStream(outFile)) {
                    fos.write((csvContent == null ? "" : csvContent).getBytes(StandardCharsets.UTF_8));
                }
                runOnUiThread(() -> Toast.makeText(
                        MainActivity.this,
                        "Saved export to " + outFile.getAbsolutePath(),
                        Toast.LENGTH_LONG
                ).show());
                return true;
            } catch (Exception ex) {
                runOnUiThread(() -> Toast.makeText(
                        MainActivity.this,
                        "Export failed: " + ex.getMessage(),
                        Toast.LENGTH_SHORT
                ).show());
                return false;
            }
        }
    }
}
