package com.github.chirilbinzaru.smartmute

import com.github.chirilbinzaru.smartmute.data.NotificationLog
import com.github.chirilbinzaru.smartmute.export.CsvExporter
import org.junit.Assert.assertEquals
import org.junit.Test

class LogListItemsTest {
    private fun log(id: Long, timestamp: Long) = NotificationLog(
        messageId = id,
        notificationKey = "k$id",
        timestamp = timestamp,
        senderId = null,
        appPackage = "app",
        messageText = null,
        timeSinceLastMsgFromSenderSec = null,
        rawConversationTitle = null,
        rawSubText = null,
        rawIsGroupConversation = null,
        rawCategory = null,
        rawTemplate = null,
        rawHasPicture = false,
    )

    private fun export(name: String, at: Long) = CsvExporter.ExportInfo(name, at)

    private fun keys(items: List<LogListItem>) = items.map { it.key }

    @Test
    fun markerSitsAboveTheRowsItIncluded() {
        val logs = listOf(log(3, 300), log(2, 200), log(1, 100))
        val items = mergeWithExports(logs, listOf(export("a.csv", 250)), isComplete = true)
        assertEquals(listOf("log_3", "export_a.csv", "log_2", "log_1"), keys(items))
    }

    @Test
    fun markerGoesAboveRowWithSameTimestamp() {
        val items = mergeWithExports(listOf(log(1, 100)), listOf(export("a.csv", 100)), isComplete = true)
        assertEquals(listOf("export_a.csv", "log_1"), keys(items))
    }

    @Test
    fun oldMarkersAreDroppedWhenListIsTruncated() {
        val logs = listOf(log(2, 200), log(1, 100))
        val exports = listOf(export("new.csv", 150), export("old.csv", 50))
        assertEquals(
            listOf("log_2", "export_new.csv", "log_1"),
            keys(mergeWithExports(logs, exports, isComplete = false)),
        )
        assertEquals(
            listOf("log_2", "export_new.csv", "log_1", "export_old.csv"),
            keys(mergeWithExports(logs, exports, isComplete = true)),
        )
    }
}
