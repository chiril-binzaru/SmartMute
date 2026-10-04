package com.github.chirilbinzaru.smartmute.data

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import kotlinx.coroutines.flow.Flow

@Dao
interface NotificationLogDao {
    @Insert
    suspend fun insert(log: NotificationLog): Long

    @Query("SELECT * FROM notification_log WHERE notification_key = :key ORDER BY timestamp DESC LIMIT 1")
    suspend fun latestForKey(key: String): NotificationLog?

    /** Newest MessagingStyle message already logged for this key, to log only newer ones. */
    @Query("SELECT MAX(raw_message_time) FROM notification_log WHERE notification_key = :key")
    suspend fun latestMessageTimeForKey(key: String): Long?

    /** Texts already logged for this key at exactly [messageTime] (apps with 1 s precision). */
    @Query("SELECT message_text FROM notification_log WHERE notification_key = :key AND raw_message_time = :messageTime")
    suspend fun textsAtMessageTime(key: String, messageTime: Long): List<String?>

    /**
     * Some apps (Viber) clear all their notifications on restart (REASON_APP_CANCEL_ALL) and
     * then post the same unread messages again. Rows whose message is back on screen weren't
     * really removed, so they're reopened and get the outcome of the re-posted notification.
     */
    @Query(
        "UPDATE notification_log SET removed_at = NULL, removal_reason = NULL, time_to_open_sec = NULL " +
            "WHERE notification_key = :key AND removal_reason = 9 AND raw_message_time IN (:messageTimes)"
    )
    suspend fun reopenReposted(key: String, messageTimes: List<Long>)

    @Query(
        "SELECT MAX(timestamp) FROM notification_log " +
            "WHERE app_package = :appPackage AND sender_id = :senderId AND timestamp < :before"
    )
    suspend fun lastTimestampFromSender(appPackage: String, senderId: String, before: Long): Long?

    /**
     * Marks every still-open row for this key as removed. time_to_open_sec is only set when
     * [opened] (tapped, or read in the app); other reasons (swipe, clear-all) leave it null.
     */
    @Query(
        "UPDATE notification_log SET removed_at = :removedAt, removal_reason = :reason, " +
            "time_to_open_sec = CASE WHEN :opened THEN (:removedAt - timestamp) / 1000 ELSE NULL END " +
            "WHERE notification_key = :key AND removed_at IS NULL"
    )
    suspend fun markRemoved(key: String, removedAt: Long, reason: Int?, opened: Boolean)

    // Messages delivered in one notification share `timestamp`; message_id keeps their order.
    @Query("SELECT * FROM notification_log ORDER BY timestamp DESC, message_id DESC LIMIT :limit")
    fun recent(limit: Int): Flow<List<NotificationLog>>

    @Query("SELECT COUNT(*) FROM notification_log")
    fun count(): Flow<Int>
}
