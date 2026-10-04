package com.github.chirilbinzaru.smartmute.data

import androidx.room.ColumnInfo
import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * One intercepted notification. Column names follow the "Data schema" section of CLAUDE.md
 * so a Room → CSV export feeds the Python pipeline unchanged.
 *
 * Fields that need a derivation step (content_type, chat_type, conversation_state,
 * user_reaction, decision) stay null for now; the raw_* columns keep the source data
 * those will be derived from.
 */
@Entity(
    tableName = "notification_log",
    indices = [Index("notification_key"), Index("sender_id")],
)
data class NotificationLog(
    // Unique per logged notification.
    @PrimaryKey(autoGenerate = true) @ColumnInfo(name = "message_id") val messageId: Long = 0,

    // Raw StatusBarNotification.key, used to match removal events. Not unique: messengers
    // re-post under the same key when a new message arrives in the same chat.
    @ColumnInfo(name = "notification_key") val notificationKey: String,
    @ColumnInfo(name = "timestamp") val timestamp: Long,
    @ColumnInfo(name = "sender_id") val senderId: String?,
    @ColumnInfo(name = "app_package") val appPackage: String,
    @ColumnInfo(name = "content_type") val contentType: String? = null,
    @ColumnInfo(name = "message_text") val messageText: String?,
    @ColumnInfo(name = "chat_type") val chatType: String? = null,
    @ColumnInfo(name = "time_since_last_msg_from_sender_sec") val timeSinceLastMsgFromSenderSec: Long?,
    @ColumnInfo(name = "conversation_state") val conversationState: String? = null,
    @ColumnInfo(name = "user_reaction") val userReaction: String? = null,
    @ColumnInfo(name = "time_to_open_sec") val timeToOpenSec: Long? = null,
    @ColumnInfo(name = "decision") val decision: String? = null,
    // [DEV ONLY] explicit feedback; never populated in production builds.
    @ColumnInfo(name = "feedback") val feedback: String? = null,
    @ColumnInfo(name = "corrected_decision") val correctedDecision: String? = null,

    // Raw source data for later feature derivation.
    @ColumnInfo(name = "raw_conversation_title") val rawConversationTitle: String?,
    @ColumnInfo(name = "raw_sub_text") val rawSubText: String?,
    @ColumnInfo(name = "raw_is_group_conversation") val rawIsGroupConversation: Boolean?,
    @ColumnInfo(name = "raw_category") val rawCategory: String?,
    @ColumnInfo(name = "raw_template") val rawTemplate: String?,
    @ColumnInfo(name = "raw_has_picture") val rawHasPicture: Boolean,

    // Filled by onNotificationRemoved.
    @ColumnInfo(name = "removed_at") val removedAt: Long? = null,
    // NotificationListenerService.REASON_* (API 26+); null if unknown.
    @ColumnInfo(name = "removal_reason") val removalReason: Int? = null,

    // MessagingStyle.Message timestamp (epoch ms): identifies the individual message inside
    // a notification that holds several. Null for non-MessagingStyle notifications. Added in
    // schema v2; kept last so migrated and fresh databases have the same column order.
    @ColumnInfo(name = "raw_message_time") val rawMessageTime: Long? = null,
)
