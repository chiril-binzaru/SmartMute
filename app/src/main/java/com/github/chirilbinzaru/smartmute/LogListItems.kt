package com.github.chirilbinzaru.smartmute

import com.github.chirilbinzaru.smartmute.data.NotificationLog
import com.github.chirilbinzaru.smartmute.export.CsvExporter

/** Rows of the main screen's log list: logged notifications plus [DEV] export markers. */
sealed interface LogListItem {
    val key: String

    data class Log(val log: NotificationLog) : LogListItem {
        override val key get() = "log_${log.messageId}"
    }

    data class ExportMarker(val export: CsvExporter.ExportInfo) : LogListItem {
        override val key get() = "export_${export.fileName}"
    }
}

/**
 * Interleaves export markers into [logs] (newest first), placing each marker above the
 * rows it included. When [logs] is truncated ([isComplete] false), markers older than the
 * oldest shown row are dropped, since their position can't be shown.
 */
fun mergeWithExports(
    logs: List<NotificationLog>,
    exports: List<CsvExporter.ExportInfo>,
    isComplete: Boolean,
): List<LogListItem> {
    val oldestShown = logs.minOfOrNull { it.timestamp }
    val visibleExports = exports.filter {
        isComplete || oldestShown == null || it.exportedAt >= oldestShown
    }
    val items = logs.map { LogListItem.Log(it) to it.timestamp } +
        visibleExports.map { LogListItem.ExportMarker(it) to it.exportedAt }
    // On a timestamp tie the marker goes first (above): that row was in the export.
    return items
        .sortedWith(
            compareByDescending<Pair<LogListItem, Long>> { it.second }
                .thenBy { if (it.first is LogListItem.ExportMarker) 0 else 1 }
        )
        .map { it.first }
}
