package com.github.chirilbinzaru.smartmute

import com.github.chirilbinzaru.smartmute.data.NotificationLog
import org.junit.Assert.assertEquals
import org.junit.Test

class SelectNewMessagesTest {
    private data class Msg(val time: Long, val text: String?)

    private fun select(
        messages: List<Msg>,
        lastLoggedTime: Long? = null,
        textsAtLast: List<String?> = emptyList(),
        openV1Text: String? = null,
    ) = selectNewMessages(
        messages = messages,
        time = { it.time },
        text = { it.text },
        lastLoggedTime = lastLoggedTime,
        textsAtLastLoggedTime = textsAtLast,
        openV1Row = openV1Text?.let { v1Row(it) },
    ).map { it.text }

    private fun v1Row(text: String) = NotificationLog(
        notificationKey = "k", timestamp = 0, senderId = null, appPackage = "app", messageText = text,
        timeSinceLastMsgFromSenderSec = null, rawConversationTitle = null, rawSubText = null,
        rawIsGroupConversation = null, rawCategory = null, rawTemplate = null, rawHasPicture = false,
    )

    @Test
    fun firstPostLogsEveryMessage() {
        assertEquals(listOf("one", "two"), select(listOf(Msg(1, "one"), Msg(2, "two"))))
    }

    @Test
    fun repostLogsOnlyNewerMessages() {
        val messages = listOf(Msg(1, "one"), Msg(2, "two"), Msg(3, "three"))
        assertEquals(listOf("three"), select(messages, lastLoggedTime = 2, textsAtLast = listOf("two")))
    }

    @Test
    fun repostWithNothingNewLogsNothing() {
        val messages = listOf(Msg(1, "one"), Msg(2, "two"))
        assertEquals(emptyList<String>(), select(messages, lastLoggedTime = 2, textsAtLast = listOf("two")))
    }

    @Test
    fun sameSecondMessageWithNewTextIsLogged() {
        val messages = listOf(Msg(5, "a"), Msg(5, "b"))
        assertEquals(listOf("b"), select(messages, lastLoggedTime = 5, textsAtLast = listOf("a")))
    }

    @Test
    fun repeatedTextInSameSecondIsLoggedOncePerOccurrence() {
        val messages = listOf(Msg(5, "ok"), Msg(5, "ok"))
        assertEquals(listOf("ok"), select(messages, lastLoggedTime = 5, textsAtLast = listOf("ok")))
    }

    @Test
    fun openV1RowLogsOnlyNewestAndOnlyIfChanged() {
        val messages = listOf(Msg(1, "one"), Msg(2, "two"))
        assertEquals(listOf("two"), select(messages, openV1Text = "one"))
        assertEquals(emptyList<String>(), select(messages, openV1Text = "two"))
    }
}
