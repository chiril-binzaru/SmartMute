package com.github.chirilbinzaru.smartmute

import android.app.Notification
import android.os.Build
import android.os.Bundle
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

        val messagingStyle = NotificationCompat.MessagingStyle
            .extractMessagingStyleFromNotification(notification)
        val messages = messagingStyle?.messages.orEmpty()
        // A null sender means the message is the user's own (e.g. an inline reply).
        val incoming = messages.filter { it.person != null }

        val base = NotificationLog(
            notificationKey = sbn.key,
            timestamp = sbn.postTime,
            senderId = title,
            appPackage = sbn.packageName,
            messageText = null,
            timeSinceLastMsgFromSenderSec = title?.let {
                dao.lastTimestampFromSender(sbn.packageName, it, sbn.postTime)
            }?.let { (sbn.postTime - it) / 1000 },
            rawConversationTitle = messagingStyle?.conversationTitle?.toString(),
            rawSubText = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString(),
            rawIsGroupConversation = messagingStyle?.isGroupConversation,
            rawCategory = notification.category,
            rawTemplate = extras.getString(Notification.EXTRA_TEMPLATE),
            rawHasPicture = extras.containsKey(Notification.EXTRA_PICTURE),
        )

        when {
            messages.isEmpty() -> logSingle(sbn, base, extras)
            // Only the user's own messages, e.g. the update after an inline reply: nothing new.
            incoming.isEmpty() -> return
            else -> logMessages(sbn, base, incoming)
        }
    }

    /**
     * Messengers keep every unread message of a chat in one MessagingStyle notification and
     * re-post it as messages arrive. Logs one row per message not logged before for this key,
     * so a burst of messages delivered together isn't collapsed into one row.
     */
    private suspend fun logMessages(
        sbn: StatusBarNotification,
        base: NotificationLog,
        messages: List<NotificationCompat.MessagingStyle.Message>,
    ) {
        dao.reopenReposted(sbn.key, messages.map { it.timestamp })
        val lastLogged = dao.latestMessageTimeForKey(sbn.key)
        val newMessages = selectNewMessages(
            messages = messages,
            time = { it.timestamp },
            text = { it.text?.toString() },
            lastLoggedTime = lastLogged,
            textsAtLastLoggedTime = lastLogged?.let { dao.textsAtMessageTime(sbn.key, it) }.orEmpty(),
            openV1Row = dao.latestForKey(sbn.key)?.takeIf { lastLogged == null && it.removedAt == null },
        )
        newMessages.forEachIndexed { i, message ->
            // Within a burst, the gap to the previous message of the same notification.
            val sinceLast = if (i == 0) {
                base.timeSinceLastMsgFromSenderSec
            } else {
                (message.timestamp - newMessages[i - 1].timestamp).coerceAtLeast(0) / 1000
            }
            dao.insert(
                base.copy(
                    messageText = message.text?.toString(),
                    timeSinceLastMsgFromSenderSec = sinceLast,
                    rawHasPicture = base.rawHasPicture || message.dataMimeType?.startsWith("image/") == true,
                    rawMessageTime = message.timestamp,
                )
            )
        }
        if (newMessages.isNotEmpty()) {
            Log.d(TAG, "Logged ${newMessages.size} message(s) ${sbn.packageName} from=${base.senderId}")
        }
    }

    /** Non-MessagingStyle notifications (Gmail, SMS on some phones, system apps): one row. */
    private suspend fun logSingle(sbn: StatusBarNotification, base: NotificationLog, extras: Bundle) {
        val text = (
            extras.getCharSequence(Notification.EXTRA_BIG_TEXT)
                ?: extras.getCharSequence(Notification.EXTRA_TEXT)
            )?.toString()

        // Apps re-post under the same key without new content (e.g. marking as alerted once).
        val previous = dao.latestForKey(sbn.key)
        if (previous != null && previous.removedAt == null &&
            previous.senderId == base.senderId && previous.messageText == text
        ) return

        dao.insert(base.copy(messageText = text))
        Log.d(TAG, "Logged ${sbn.packageName} from=${base.senderId}")
    }

    private fun logRemoved(sbn: StatusBarNotification, reason: Int?) {
        val removedAt = System.currentTimeMillis()
        // Tapped, or read inside the app (the app then cancels its own notification).
        // See "user_reaction" in docs/DATA_SCHEMA.md.
        val opened = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O &&
            (reason == REASON_CLICK || reason == REASON_APP_CANCEL)
        scope.launch {
            runCatching { dao.markRemoved(sbn.key, removedAt, reason, opened) }
                .onFailure { Log.e(TAG, "Failed to mark ${sbn.key} removed", it) }
        }
    }

    private companion object {
        const val TAG = "NotificationLogger"
    }
}

/**
 * Which messages of a MessagingStyle notification haven't been logged yet for its key.
 *
 * - [lastLoggedTime]: newest `raw_message_time` logged for the key. Messages after it are
 *   new; messages at exactly that time are new unless their text was logged then (Telegram
 *   stamps to the second, so several messages can share a time).
 * - [openV1Row]: still-open row from schema v1 (no message times). Its earlier messages
 *   are already logged, so only the newest message counts, and only if its text differs.
 * - Neither: nothing logged for this chat yet (or it was read), so all messages are new.
 */
internal fun <M> selectNewMessages(
    messages: List<M>,
    time: (M) -> Long,
    text: (M) -> String?,
    lastLoggedTime: Long?,
    textsAtLastLoggedTime: List<String?>,
    openV1Row: NotificationLog?,
): List<M> = when {
    lastLoggedTime != null -> {
        val remaining = textsAtLastLoggedTime.toMutableList()
        messages.filter {
            time(it) > lastLoggedTime || (time(it) == lastLoggedTime && !remaining.remove(text(it)))
        }
    }
    openV1Row != null -> listOfNotNull(messages.lastOrNull()).filter { text(it) != openV1Row.messageText }
    else -> messages
}
