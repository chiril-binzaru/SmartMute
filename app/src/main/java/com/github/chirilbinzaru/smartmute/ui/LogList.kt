package com.github.chirilbinzaru.smartmute.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.github.chirilbinzaru.smartmute.data.NotificationLog
import java.text.DateFormat
import java.util.Date

/** How many of the newest rows the log screens load. */
const val LOG_LIST_LIMIT = 100

/**
 * LazyColumn with the always-visible scrollbar, shared by the dev log and user history.
 *
 * [topKey] is the key of the first item. LazyColumn keeps the current first item in place
 * when items are inserted above it, which hides new rows; so if the list was at the very
 * top when [topKey] changed, it scrolls back up to show them.
 */
@Composable
fun LogList(topKey: Any?, modifier: Modifier = Modifier, content: LazyListScope.() -> Unit) {
    val listState = rememberLazyListState()
    // Read during composition, i.e. from the layout before the new items are measured.
    val wasAtTop by remember {
        derivedStateOf { listState.firstVisibleItemIndex == 0 && listState.firstVisibleItemScrollOffset == 0 }
    }
    val scrollUp = wasAtTop
    LaunchedEffect(topKey) {
        if (scrollUp) listState.scrollToItem(0)
    }
    LazyColumn(
        state = listState,
        modifier = modifier.verticalScrollbar(
            state = listState,
            color = MaterialTheme.colorScheme.outline,
        ),
        contentPadding = PaddingValues(end = 10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        content = content,
    )
}

/** One logged notification. [showRemoval] adds the removal time and raw reason code (dev). */
@Composable
fun LogRow(log: NotificationLog, showRemoval: Boolean = false) {
    val time = DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.MEDIUM)
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(log.appPackage, style = MaterialTheme.typography.labelSmall)
            Text(log.senderId ?: "(no title)", style = MaterialTheme.typography.titleSmall)
            Text(log.messageText ?: "(no text)", maxLines = 3)
            val removed = log.removedAt?.takeIf { showRemoval }?.let { removedAt ->
                val opened = log.timeToOpenSec?.let { " · opened after ${it}s" } ?: ""
                " · removed ${time.format(Date(removedAt))} (reason ${log.removalReason})$opened"
            } ?: ""
            Text(
                time.format(Date(log.timestamp)) + removed,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
