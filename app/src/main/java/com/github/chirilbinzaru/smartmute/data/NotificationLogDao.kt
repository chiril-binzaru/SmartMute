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

    @Query(
        "SELECT MAX(timestamp) FROM notification_log " +
            "WHERE app_package = :appPackage AND sender_id = :senderId AND timestamp < :before"
    )
    suspend fun lastTimestampFromSender(appPackage: String, senderId: String, before: Long): Long?

    /**
     * Marks every still-open row for this key as removed. time_to_open_sec is only set when
     * the user tapped the notification; other removal reasons (swipe, app cancel) leave it null.
     */
    @Query(
        "UPDATE notification_log SET removed_at = :removedAt, removal_reason = :reason, " +
            "time_to_open_sec = CASE WHEN :opened THEN (:removedAt - timestamp) / 1000 ELSE NULL END " +
            "WHERE notification_key = :key AND removed_at IS NULL"
    )
    suspend fun markRemoved(key: String, removedAt: Long, reason: Int?, opened: Boolean)

    @Query("SELECT * FROM notification_log ORDER BY timestamp DESC LIMIT :limit")
    fun recent(limit: Int): Flow<List<NotificationLog>>

    @Query("SELECT COUNT(*) FROM notification_log")
    fun count(): Flow<Int>
}
