package com.github.chirilbinzaru.smartmute

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.lifecycleScope
import com.github.chirilbinzaru.smartmute.data.AppDatabase
import com.github.chirilbinzaru.smartmute.export.CsvExporter
import com.github.chirilbinzaru.smartmute.ui.ListenerAccess
import com.github.chirilbinzaru.smartmute.settings.SmartMuteSettings
import com.github.chirilbinzaru.smartmute.ui.LOG_LIST_LIMIT
import com.github.chirilbinzaru.smartmute.ui.ListenerStatus
import com.github.chirilbinzaru.smartmute.ui.LogList
import com.github.chirilbinzaru.smartmute.ui.LogRow
import com.github.chirilbinzaru.smartmute.ui.SmartMuteToggle
import com.github.chirilbinzaru.smartmute.ui.theme.SmartMuteTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** [DEV] Log viewer with CSV export. The user flavor has its own minimal MainActivity. */
class MainActivity : ComponentActivity() {
    private val listenerEnabled = mutableStateOf(false)
    private val exportStatus = mutableStateOf<String?>(null)
    private val smartMuteEnabled = mutableStateOf(true)
    // null until first loaded; the list waits for both so it never starts out partial.
    private val exports = mutableStateOf<List<CsvExporter.ExportInfo>?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        smartMuteEnabled.value = SmartMuteSettings.isEnabled(this)
        val dao = AppDatabase.get(this).notificationLogDao()
        val recentLogs = dao.recent(LOG_LIST_LIMIT)
        val logCount = dao.count()
        setContent {
            SmartMuteTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    val logs by recentLogs.collectAsState(initial = null)
                    val count by logCount.collectAsState(initial = 0)
                    Column(
                        modifier = Modifier.padding(innerPadding).padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        ListenerStatus(
                            enabled = listenerEnabled.value,
                            onOpenSettings = { ListenerAccess.openSettings(this@MainActivity) },
                        )
                        SmartMuteToggle(
                            enabled = smartMuteEnabled.value,
                            onEnabledChange = {
                                smartMuteEnabled.value = it
                                SmartMuteSettings.setEnabled(this@MainActivity, it)
                            },
                        )
                        Text("Logged notifications: $count", style = MaterialTheme.typography.titleMedium)
                        DevExport(status = exportStatus.value, onExport = ::exportCsv)
                        val loadedLogs = logs ?: return@Column
                        val loadedExports = exports.value ?: return@Column
                        val items = mergeWithExports(
                            logs = loadedLogs,
                            exports = loadedExports,
                            isComplete = loadedLogs.size < LOG_LIST_LIMIT,
                        )
                        LogList(topKey = items.firstOrNull()?.key) {
                            items(items, key = { it.key }) { item ->
                                when (item) {
                                    is LogListItem.Log -> LogRow(item.log, showRemoval = true)
                                    is LogListItem.ExportMarker -> ExportMarkerRow(item.export.fileName)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // The user may have just come back from the settings screen.
        listenerEnabled.value = ListenerAccess.isEnabled(this)
        refreshExports()
    }

    // Export files may have been deleted (e.g. via adb) while we were in the background.
    private fun refreshExports() {
        lifecycleScope.launch {
            exports.value = withContext(Dispatchers.IO) {
                runCatching { CsvExporter.listExports(applicationContext) }.getOrDefault(emptyList())
            }
        }
    }

    private fun exportCsv() {
        exportStatus.value = "Exporting…"
        lifecycleScope.launch {
            exportStatus.value = runCatching {
                withContext(Dispatchers.IO) { CsvExporter.export(applicationContext) }
            }.fold(
                onSuccess = { "Saved ${it.name}\nadb pull ${it.absolutePath}" },
                onFailure = { "Export failed: ${it.message}" },
            )
            refreshExports()
        }
    }
}

@Composable
private fun DevExport(status: String?, onExport: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        OutlinedButton(onClick = onExport) { Text("Export CSV") }
        status?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable
private fun ExportMarkerRow(fileName: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        HorizontalDivider(modifier = Modifier.weight(1f), color = MaterialTheme.colorScheme.tertiary)
        Text(
            "Export $fileName",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.tertiary,
        )
        HorizontalDivider(modifier = Modifier.weight(1f), color = MaterialTheme.colorScheme.tertiary)
    }
}
