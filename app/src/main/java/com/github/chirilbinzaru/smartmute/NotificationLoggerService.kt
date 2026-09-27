package com.github.chirilbinzaru.smartmute

import android.app.Notification
import android.os.Build
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import androidx.core.app.NotificationCompat
import com.github.chirilbinzaru.smartmute.data.AppDatabase
import com.github.chirilbinzaru.smartmute.data.NotificationLog
import com.github.chirilbinzaru.smartmute.data.NotificationLogDao
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Step 1: log every incoming notification to Room and record when it goes away.
 * No decisions, no reposting.
 */
class NotificationLoggerService : NotificationListenerService() {

    // Single-threaded so a post and its removal are always written in order.
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO.limitedParallelism(1))
    private lateinit var dao: NotificationLogDao

    override fun onCreate() {
        super.onCreate()
        dao = AppDatabase.get(this).notificationLogDao()
    }

    override fun onDestroy() {
        scope.cancel()
        super.onDestroy()
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        if (!shouldLog(sbn)) return
        scope.launch {
            runCatching { logPosted(sbn) }.onFailure { Log.e(TAG, "Failed to log ${sbn.key}", it) }
        }
    }

    // Called on API 26+; the system routes to the 2-arg overload below on older versions.
    override fun onNotificationRemoved(sbn: StatusBarNotification, rankingMap: RankingMap, reason: Int) {
        logRemoved(sbn, reason)
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        logRemoved(sbn, null)
    }

    private fun shouldLog(sbn: StatusBarNotification): Boolean {
        if (sbn.packageName == packageName) return false
        val flags = sbn.notification.flags
        // Group summaries duplicate their children; ongoing ones are media players, downloads, etc.
        if (flags and Notification.FLAG_GROUP_SUMMARY != 0) return false
        if (flags and Notification.FLAG_ONGOING_EVENT != 0) return false
        if (flags and Notification.FLAG_FOREGROUND_SERVICE != 0) return false
        return true
    }

    private suspend fun logPosted(sbn: StatusBarNotification) {
        val notification = sbn.notification
        val extras = notification.extras
        val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()

        // Messengers put the conversation in MessagingStyle; the last message is the new one.
        val messagingStyle = NotificationCompat.MessagingStyle
            .extractMessagingStyleFromNotification(notification)
        val lastMessage = messagingStyle?.messages?.lastOrNull()
        val text = (
            lastMessage?.text
                ?: extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
                ?: extras.getCharSequence(Notification.EXTRA_TEXT)
            )?.toString()

        // Apps re-post under the same key without new content (e.g. marking as alerted once).
        val previous = dao.latestForKey(sbn.key)
        if (previous != null && previous.removedAt == null &&
            previous.senderId == title && previous.messageText == text
        ) return

        val sinceLast = title?.let {
            dao.lastTimestampFromSender(sbn.packageName, it, sbn.postTime)
        }?.let { (sbn.postTime - it) / 1000 }

        val hasPicture = extras.containsKey(Notification.EXTRA_PICTURE) ||
            lastMessage?.dataMimeType?.startsWith("image/") == true

        dao.insert(
            NotificationLog(
                notificationKey = sbn.key,
                timestamp = sbn.postTime,
                senderId = title,
                appPackage = sbn.packageName,
                messageText = text,
                timeSinceLastMsgFromSenderSec = sinceLast,
                rawConversationTitle = messagingStyle?.conversationTitle?.toString(),
                rawSubText = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString(),
                rawIsGroupConversation = messagingStyle?.isGroupConversation,
                rawCategory = notification.category,
                rawTemplate = extras.getString(Notification.EXTRA_TEMPLATE),
                rawHasPicture = hasPicture,
            )
        )
        Log.d(TAG, "Logged ${sbn.packageName} from=$title")
    }

    private fun logRemoved(sbn: StatusBarNotification, reason: Int?) {
        val removedAt = System.currentTimeMillis()
        val opened = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && reason == REASON_CLICK
        scope.launch {
            runCatching { dao.markRemoved(sbn.key, removedAt, reason, opened) }
                .onFailure { Log.e(TAG, "Failed to mark ${sbn.key} removed", it) }
        }
    }

    private companion object {
        const val TAG = "NotificationLogger"
    }
}
