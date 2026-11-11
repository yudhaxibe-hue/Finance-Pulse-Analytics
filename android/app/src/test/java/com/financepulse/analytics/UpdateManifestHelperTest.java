package com.financepulse.analytics;

import org.junit.Test;
import static org.junit.Assert.*;

public class UpdateManifestHelperTest {
    @Test
    public void comparesBuildAndSemverVersionsAccurately() {
        assertTrue(UpdateManifestHelper.isApkUpdateAvailable(2, "1.1.0", 18, "1.1.0"));
        assertFalse(UpdateManifestHelper.isApkUpdateAvailable(18, "1.1.0", 18, "1.1.0"));
        assertFalse(UpdateManifestHelper.isApkUpdateAvailable(19, "1.1.0", 18, "1.1.0"));
        assertTrue(UpdateManifestHelper.isApkUpdateAvailable(0, "1.1.0", 0, "1.2.0"));

        assertTrue(UpdateManifestHelper.isOtaUpdateAvailable("", "1.1.0+18"));
        assertTrue(UpdateManifestHelper.isOtaUpdateAvailable("1.1.0+2", "1.1.0+18"));
        assertFalse(UpdateManifestHelper.isOtaUpdateAvailable("1.1.0+18", "1.1.0+18"));
        assertFalse(UpdateManifestHelper.isOtaUpdateAvailable("1.2.0+20", "1.1.0+19"));
    }

    @Test
    public void preventsZipSlipAndDisallowedOtaEntries() {
        assertEquals("mobile_app.html", UpdateManifestHelper.normalizeZipAssetName("./mobile_app.html"));
        assertEquals("mobile_app.js", UpdateManifestHelper.normalizeZipAssetName("mobile_app.js"));
        assertNull(UpdateManifestHelper.normalizeZipAssetName("../mobile_app.html"));
        assertNull(UpdateManifestHelper.normalizeZipAssetName("nested/mobile_app.js"));
        assertNull(UpdateManifestHelper.normalizeZipAssetName("classes.dex"));
        assertTrue(UpdateManifestHelper.isSafeOtaEntryName("chart.umd.min.js"));
        assertFalse(UpdateManifestHelper.isSafeOtaEntryName("..\\secret.txt"));
    }

    @Test
    public void formatsShaHexLowercase() {
        assertEquals("000aff", UpdateManifestHelper.bytesToHex(new byte[]{0x00, 0x0a, (byte) 0xff}));
        assertTrue(UpdateManifestHelper.DEFAULT_MANIFEST_URL.startsWith("https://github.com/"));
        assertEquals("1.2.0", UpdateManifestHelper.BUNDLED_VERSION_NAME);
    }
}
