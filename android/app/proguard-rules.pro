# Keep Android WebView JavascriptInterface methods intact if minification is enabled.
-keepclassmembers class * {
    @android.webkit.JavascriptInterface <methods>;
}
