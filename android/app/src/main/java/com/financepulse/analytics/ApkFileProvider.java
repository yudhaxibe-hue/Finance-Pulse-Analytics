package com.financepulse.analytics;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;

/**
 * Minimal scoped ContentProvider exposing downloaded APK update files to Android's package installer.
 */
public class ApkFileProvider extends ContentProvider {
    private static final String MIME_APK = "application/vnd.android.package-archive";
    private static final String[] DEFAULT_COLUMNS = {
            OpenableColumns.DISPLAY_NAME,
            OpenableColumns.SIZE
    };

    public static Uri uriForUpdateApk(Context context, File apkFile) {
        String authority = context.getPackageName() + ".apkprovider";
        return new Uri.Builder()
                .scheme("content")
                .authority(authority)
                .path("updates/" + apkFile.getName())
                .build();
    }

    private File resolveScopedFile(Uri uri) throws FileNotFoundException {
        Context ctx = getContext();
        if (ctx == null || uri == null) {
            throw new FileNotFoundException("Invalid context or URI");
        }
        String lastSeg = uri.getLastPathSegment();
        if (lastSeg == null || lastSeg.isEmpty() || lastSeg.contains("/") || lastSeg.contains("\\") || "..".equals(lastSeg)) {
            throw new FileNotFoundException("Invalid file name");
        }
        File updatesDir = new File(ctx.getFilesDir(), "updates");
        File target = new File(updatesDir, lastSeg);
        try {
            String dirCanon = updatesDir.getCanonicalPath() + File.separator;
            String targetCanon = target.getCanonicalPath();
            if (!targetCanon.startsWith(dirCanon) || !target.isFile()) {
                throw new FileNotFoundException("File not inside updates directory");
            }
            return target;
        } catch (IOException ex) {
            throw new FileNotFoundException("Canonical resolution failed");
        }
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public Cursor query(Uri uri, String[] projection, String selection, String[] selectionArgs, String sortOrder) {
        File file;
        try {
            file = resolveScopedFile(uri);
        } catch (FileNotFoundException ex) {
            return new MatrixCursor(DEFAULT_COLUMNS);
        }
        String[] cols = (projection == null || projection.length == 0) ? DEFAULT_COLUMNS : projection;
        Object[] row = new Object[cols.length];
        for (int i = 0; i < cols.length; i++) {
            if (OpenableColumns.DISPLAY_NAME.equals(cols[i])) {
                row[i] = file.getName();
            } else if (OpenableColumns.SIZE.equals(cols[i])) {
                row[i] = file.length();
            }
        }
        MatrixCursor cursor = new MatrixCursor(cols, 1);
        cursor.addRow(row);
        return cursor;
    }

    @Override
    public String getType(Uri uri) {
        return MIME_APK;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri uri, String mode) throws FileNotFoundException {
        if (mode == null || !mode.startsWith("r")) {
            throw new SecurityException("Read-only provider");
        }
        File file = resolveScopedFile(uri);
        return ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Uri insert(Uri uri, ContentValues values) {
        throw new UnsupportedOperationException("Read-only provider");
    }

    @Override
    public int delete(Uri uri, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("Read-only provider");
    }

    @Override
    public int update(Uri uri, ContentValues values, String selection, String[] selectionArgs) {
        throw new UnsupportedOperationException("Read-only provider");
    }
}
