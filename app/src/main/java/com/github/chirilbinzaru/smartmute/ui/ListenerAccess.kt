package com.github.chirilbinzaru.smartmute.ui

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import com.github.chirilbinzaru.smartmute.NotificationLoggerService

/** Notification-listener permission, shared by the dev and user screens. */
object ListenerAccess {
    fun isEnabled(context: Context): Boolean =
        NotificationManagerCompat.getEnabledListenerPackages(context).contains(context.packageName)

    /** Opens this app's page in the notification-access settings (or the list, pre-Android 11). */
    fun openSettings(context: Context) {
        val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            Intent(Settings.ACTION_NOTIFICATION_LISTENER_DETAIL_SETTINGS).putExtra(
                Settings.EXTRA_NOTIFICATION_LISTENER_COMPONENT_NAME,
                ComponentName(context, NotificationLoggerService::class.java).flattenToString(),
            )
        } else {
            Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)
        }
        runCatching { context.startActivity(intent) }
            .onFailure { context.startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)) }
    }
}

@Composable
fun ListenerStatus(enabled: Boolean, onOpenSettings: () -> Unit, modifier: Modifier = Modifier) {
    if (enabled) {
        Text(
            "Notification access: enabled",
            modifier = modifier,
            color = MaterialTheme.colorScheme.primary,
        )
    } else {
        Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                "SmartMute needs notification access to read incoming notifications. " +
                    "Everything stays on this device.",
            )
            Button(onClick = onOpenSettings) { Text("Grant notification access") }
        }
    }
}
