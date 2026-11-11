package com.financepulse.analytics;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
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

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private static final String PREFS_NAME = "finance_pulse_prefs";
    private static final String KEY_SERVER_URL = "server_url";
    private static final int FILE_CHOOSER_REQUEST_CODE = 1001;

    private WebView webView;
    private Button returnOfflineBtn;
    private ValueCallback<Uri[]> filePathCallback;

    @SuppressLint({"SetJavaScriptEnabled"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setTitle(ServerUrlValidator.APP_TITLE);

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
                boolean isLocal = url != null && url.startsWith("file:///android_asset/");
                returnOfflineBtn.setVisibility(isLocal ? View.GONE : View.VISIBLE);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request != null && request.isForMainFrame()) {
                    String currentUrl = request.getUrl() != null ? request.getUrl().toString() : "";
                    if (!currentUrl.startsWith("file:///android_asset/")) {
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
        returnOfflineBtn.setText("Offline Mode");
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
    }

    private void loadLocalWorkspace() {
        webView.loadUrl(ServerUrlValidator.LOCAL_ASSET_URL);
    }

    private String getSavedServerUrl() {
        SharedPreferences prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        return ServerUrlValidator.normalizeServerUrl(prefs.getString(KEY_SERVER_URL, ""));
    }

    private void clearSavedServerUrl() {
        getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().remove(KEY_SERVER_URL).apply();
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
            getSharedPreferences(PREFS_NAME, MODE_PRIVATE).edit().putString(KEY_SERVER_URL, normalized).apply();
            runOnUiThread(() -> webView.loadUrl(normalized));
            return true;
        }

        @JavascriptInterface
        public void disconnectServer() {
            clearSavedServerUrl();
            runOnUiThread(MainActivity.this::loadLocalWorkspace);
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
