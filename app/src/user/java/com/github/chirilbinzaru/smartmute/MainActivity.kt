package com.github.chirilbinzaru.smartmute

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.github.chirilbinzaru.smartmute.data.AppDatabase
import com.github.chirilbinzaru.smartmute.data.NotificationLog
import com.github.chirilbinzaru.smartmute.settings.SmartMuteSettings
import com.github.chirilbinzaru.smartmute.ui.ListenerAccess
import com.github.chirilbinzaru.smartmute.ui.ListenerStatus
import com.github.chirilbinzaru.smartmute.ui.LOG_LIST_LIMIT
import com.github.chirilbinzaru.smartmute.ui.LogList
import com.github.chirilbinzaru.smartmute.ui.LogRow
import com.github.chirilbinzaru.smartmute.ui.SmartMuteToggle
import com.github.chirilbinzaru.smartmute.ui.theme.SmartMuteTheme
import kotlinx.coroutines.flow.Flow

/**
 * User-facing app: an On/Off switch, plus a read-only history the user can open if they
 * want to. No feedback controls — see "Architectural constraint" in CLAUDE.md.
 */
class MainActivity : ComponentActivity() {
    private val listenerEnabled = mutableStateOf(false)
    private val smartMuteEnabled = mutableStateOf(true)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        smartMuteEnabled.value = SmartMuteSettings.isEnabled(this)
        val recentLogs = AppDatabase.get(this).notificationLogDao().recent(LOG_LIST_LIMIT)
        setContent {
            SmartMuteTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    var showHistory by rememberSaveable { mutableStateOf(false) }
                    BackHandler(enabled = showHistory) { showHistory = false }
                    val contentModifier = Modifier.padding(innerPadding).padding(16.dp)
                    if (showHistory) {
                        HistoryScreen(recentLogs, onBack = { showHistory = false }, modifier = contentModifier)
                    } else {
                        HomeScreen(onShowHistory = { showHistory = true }, modifier = contentModifier)
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // The user may have just come back from the settings screen.
        listenerEnabled.value = ListenerAccess.isEnabled(this)
    }

    @Composable
    private fun HomeScreen(onShowHistory: () -> Unit, modifier: Modifier) {
        Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(16.dp)) {
            if (!listenerEnabled.value) {
                ListenerStatus(enabled = false, onOpenSettings = { ListenerAccess.openSettings(this@MainActivity) })
                return@Column
            }
            SmartMuteToggle(
                enabled = smartMuteEnabled.value,
                onEnabledChange = {
                    smartMuteEnabled.value = it
                    SmartMuteSettings.setEnabled(this@MainActivity, it)
                },
            )
            TextButton(onClick = onShowHistory) { Text("View history") }
        }
    }
}

@Composable
private fun HistoryScreen(recentLogs: Flow<List<NotificationLog>>, onBack: () -> Unit, modifier: Modifier) {
    // null until the first query returns, so the list never starts out empty and then jumps.
    val logs by recentLogs.collectAsState(initial = null)
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        TextButton(onClick = onBack) { Text("← Back") }
        Text("History", style = MaterialTheme.typography.titleLarge)
        val loaded = logs ?: return@Column
        if (loaded.isEmpty()) {
            Text("No notifications yet.")
        } else {
            LogList(topKey = loaded.first().messageId) {
                items(loaded, key = { it.messageId }) { LogRow(it) }
            }
        }
    }
}
