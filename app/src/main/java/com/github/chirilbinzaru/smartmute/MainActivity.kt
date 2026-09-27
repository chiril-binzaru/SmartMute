package com.github.chirilbinzaru.smartmute

import android.content.ComponentName
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import com.github.chirilbinzaru.smartmute.data.AppDatabase
import com.github.chirilbinzaru.smartmute.data.NotificationLog
import com.github.chirilbinzaru.smartmute.ui.theme.SmartMuteTheme
import java.text.DateFormat
import java.util.Date

class MainActivity : ComponentActivity() {
    private val listenerEnabled = mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val dao = AppDatabase.get(this).notificationLogDao()
        val recentLogs = dao.recent(RECENT_LIMIT)
        val logCount = dao.count()
        setContent {
            SmartMuteTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    val logs by recentLogs.collectAsState(initial = emptyList())
                    val count by logCount.collectAsState(initial = 0)
                    Column(
                        modifier = Modifier.padding(innerPadding).padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        ListenerStatus(
                            enabled = listenerEnabled.value,
                            onOpenSettings = ::openListenerSettings,
                        )
                        Text("Logged notifications: $count", style = MaterialTheme.typography.titleMedium)
                        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            items(logs, key = { it.messageId }) { LogRow(it) }
                        }
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // The user may have just come back from the settings screen.
        listenerEnabled.value = NotificationManagerCompat.getEnabledListenerPackages(this)
            .contains(packageName)
    }

    private fun openListenerSettings() {
        val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Intent(Settings.ACTION_NOTIFICATION_LISTENER_DETAIL_SETTINGS).putExtra(
                Settings.EXTRA_NOTIFICATION_LISTENER_COMPONENT_NAME,
                ComponentName(this, NotificationLoggerService::class.java).flattenToString(),
            )
        } else {
            Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
        }
        runCatching { startActivity(intent) }
            .onFailure { startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }
    }

    private companion object {
        const val RECENT_LIMIT = 100
    }
}

@Composable
private fun ListenerStatus(enabled: Boolean, onOpenSettings: () -> Unit) {
    if (enabled) {
        Text("Notification access: enabled", color = MaterialTheme.colorScheme.primary)
    } else {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                "SmartMute needs notification access to read incoming notifications. " +
                    "Everything stays on this device.",
            )
            Button(onClick = onOpenSettings) { Text("Grant notification access") }
        }
    }
}

@Composable
private fun LogRow(log: NotificationLog) {
    val time = DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.MEDIUM)
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(log.appPackage, style = MaterialTheme.typography.labelSmall)
            Text(log.senderId ?: "(no title)", style = MaterialTheme.typography.titleSmall)
            Text(log.messageText ?: "(no text)", maxLines = 3)
            val removed = log.removedAt?.let { removedAt ->
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
