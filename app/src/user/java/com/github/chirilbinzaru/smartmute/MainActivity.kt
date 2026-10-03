package com.github.chirilbinzaru.smartmute

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.github.chirilbinzaru.smartmute.ui.ListenerAccess
import com.github.chirilbinzaru.smartmute.ui.ListenerStatus
import com.github.chirilbinzaru.smartmute.ui.theme.SmartMuteTheme

/** User-facing screen: only the notification-access status. No logs, no dev tools. */
class MainActivity : ComponentActivity() {
    private val listenerEnabled = mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            SmartMuteTheme {
                Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
                    ListenerStatus(
                        enabled = listenerEnabled.value,
                        onOpenSettings = { ListenerAccess.openSettings(this) },
                        modifier = Modifier.padding(innerPadding).padding(16.dp),
                    )
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // The user may have just come back from the settings screen.
        listenerEnabled.value = ListenerAccess.isEnabled(this)
    }
}
