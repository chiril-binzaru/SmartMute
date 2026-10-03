package com.github.chirilbinzaru.smartmute.settings

import android.content.Context
import androidx.core.content.edit

/**
 * User-facing On/Off switch. Off means SmartMute stops changing notification sounds;
 * logging continues either way so passive signals keep accumulating.
 *
 * Nothing reads this yet: it takes effect once the decision engine + reposting (step 2)
 * exist, which must skip cancel/repost when [isEnabled] is false.
 */
object SmartMuteSettings {
    private const val PREFS = "settings"
    private const val KEY_ENABLED = "enabled"

    fun isEnabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_ENABLED, true)

    fun setEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean(KEY_ENABLED, enabled) }
    }
}
