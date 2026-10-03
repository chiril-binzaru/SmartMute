package com.github.chirilbinzaru.smartmute.export

import android.content.Context
import android.database.Cursor
import com.github.chirilbinzaru.smartmute.data.AppDatabase
import java.io.File
import java.io.Writer
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * [DEV ONLY] Dumps notification_log to CSV in the app's external files dir, for
 * `adb pull` into the Python pipeline. Lives in the dev flavor only.
 *
 * Columns are read from the table itself, so the header always matches the Room schema
 * (see docs/DATA_SCHEMA.md), plus a trailing removal_reason_name column.
 */
object CsvExporter {
    const val DIR = "exports"
    private const val REASON_COLUMN = "removal_reason"
    private const val STAMP_PATTERN = "yyyyMMdd_HHmmss"
    private val FILE_NAME = Regex("""notification_log_(\d{8}_\d{6})\.csv""")

    /** An export file on the device; [exportedAt] is when the export started (epoch ms). */
    data class ExportInfo(val fileName: String, val exportedAt: Long)

    /** Writes the export and returns the file. Blocking; call off the main thread. */
    fun export(context: Context): File {
        val dir = File(context.getExternalFilesDir(null), DIR).apply { mkdirs() }
        val stamp = SimpleDateFormat(STAMP_PATTERN, Locale.US).format(Date())
        val file = File(dir, "notification_log_$stamp.csv")
        val db = AppDatabase.get(context).openHelper.readableDatabase
        db.query("SELECT * FROM notification_log ORDER BY message_id").use { cursor ->
            file.bufferedWriter(Charsets.UTF_8).use { writeCsv(cursor, it) }
        }
        return file
    }

    /**
     * Exports currently on the device, newest first. Derived from the files themselves, so
     * deleting an export file also removes its marker. Blocking; call off the main thread.
     */
    fun listExports(context: Context): List<ExportInfo> {
        val dir = File(context.getExternalFilesDir(null), DIR)
        val format = SimpleDateFormat(STAMP_PATTERN, Locale.US)
        return dir.listFiles().orEmpty().mapNotNull { file ->
            val stamp = FILE_NAME.matchEntire(file.name)?.groupValues?.get(1) ?: return@mapNotNull null
            val exportedAt = runCatching { format.parse(stamp)?.time }.getOrNull() ?: file.lastModified()
            ExportInfo(file.name, exportedAt)
        }.sortedByDescending { it.exportedAt }
    }

    private fun writeCsv(cursor: Cursor, out: Writer) {
        val columns = cursor.columnNames.toList()
        val reasonIndex = columns.indexOf(REASON_COLUMN)
        writeRow(out, columns + "removal_reason_name")
        while (cursor.moveToNext()) {
            val values = columns.indices.map { cellValue(cursor, it) }
            val reasonName = if (reasonIndex >= 0 && !cursor.isNull(reasonIndex)) {
                removalReasonName(cursor.getInt(reasonIndex))
            } else {
                ""
            }
            writeRow(out, values + reasonName)
        }
    }

    // NULL becomes an empty field; booleans are already 0/1 in SQLite.
    private fun cellValue(cursor: Cursor, index: Int): String = when (cursor.getType(index)) {
        Cursor.FIELD_TYPE_NULL -> ""
        Cursor.FIELD_TYPE_INTEGER -> cursor.getLong(index).toString()
        Cursor.FIELD_TYPE_FLOAT -> cursor.getDouble(index).toString()
        else -> cursor.getString(index)
    }

    private fun writeRow(out: Writer, fields: List<String>) {
        fields.joinTo(out, separator = ",") { escape(it) }
        out.write("\r\n")
    }

    /** RFC 4180: quote fields containing a comma, quote, CR or LF; double inner quotes. */
    fun escape(field: String): String =
        if (field.any { it == ',' || it == '"' || it == '\n' || it == '\r' }) {
            "\"" + field.replace("\"", "\"\"") + "\""
        } else {
            field
        }

    /** NotificationListenerService.REASON_* names; table in docs/DATA_SCHEMA.md. */
    fun removalReasonName(code: Int): String = when (code) {
        1 -> "CLICK"
        2 -> "CANCEL"
        3 -> "CANCEL_ALL"
        4 -> "ERROR"
        5 -> "PACKAGE_CHANGED"
        6 -> "USER_STOPPED"
        7 -> "PACKAGE_BANNED"
        8 -> "APP_CANCEL"
        9 -> "APP_CANCEL_ALL"
        10 -> "LISTENER_CANCEL"
        11 -> "LISTENER_CANCEL_ALL"
        12 -> "GROUP_SUMMARY_CANCELED"
        13 -> "GROUP_OPTIMIZATION"
        14 -> "PACKAGE_SUSPENDED"
        15 -> "PROFILE_TURNED_OFF"
        16 -> "UNAUTOBUNDLED"
        17 -> "CHANNEL_BANNED"
        18 -> "SNOOZED"
        19 -> "TIMEOUT"
        20 -> "CHANNEL_REMOVED"
        21 -> "CLEAR_DATA"
        22 -> "ASSISTANT_CANCEL"
        23 -> "LOCKDOWN"
        24 -> "BUNDLE_DISMISSED"
        else -> "UNKNOWN_$code"
    }
}
