package com.simsms.gateway.data.local

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

class SecurePreferences(context: Context) {

    private val prefs: SharedPreferences = try {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            "secure_gateway_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (e: Exception) {
        Log.w("SecurePreferences", "EncryptedSharedPreferences fallback to standard: ${e.message}")
        context.getSharedPreferences("standard_gateway_prefs", Context.MODE_PRIVATE)
    }

    var serverUrl: String
        get() = prefs.getString(KEY_SERVER_URL, "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000"
        set(value) = prefs.edit().putString(KEY_SERVER_URL, value.trimEnd('/')).apply()

    var deviceToken: String?
        get() = prefs.getString(KEY_DEVICE_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_DEVICE_TOKEN, value).apply()

    var deviceId: String?
        get() = prefs.getString(KEY_DEVICE_ID, null)
        set(value) = prefs.edit().putString(KEY_DEVICE_ID, value).apply()

    var deviceName: String
        get() = prefs.getString(KEY_DEVICE_NAME, "Android Gateway Phone") ?: "Android Gateway Phone"
        set(value) = prefs.edit().putString(KEY_DEVICE_NAME, value).apply()

    var isPaired: Boolean
        get() = !deviceToken.isNullOrBlank() && !deviceId.isNullOrBlank()
        set(value) {
            if (!value) {
                deviceToken = null
                deviceId = null
            }
        }

    var autoSyncEnabled: Boolean
        get() = prefs.getBoolean(KEY_AUTO_SYNC, true)
        set(value) = prefs.edit().putBoolean(KEY_AUTO_SYNC, value).apply()

    var syncIntervalSeconds: Int
        get() = prefs.getInt(KEY_SYNC_INTERVAL, 5)
        set(value) = prefs.edit().putInt(KEY_SYNC_INTERVAL, value).apply()

    var notificationsEnabled: Boolean
        get() = prefs.getBoolean(KEY_NOTIFICATIONS, true)
        set(value) = prefs.edit().putBoolean(KEY_NOTIFICATIONS, value).apply()

    var lastSyncTimestamp: Long
        get() = prefs.getLong(KEY_LAST_SYNC, 0L)
        set(value) = prefs.edit().putLong(KEY_LAST_SYNC, value).apply()

    var isServiceRunning: Boolean
        get() = prefs.getBoolean(KEY_SERVICE_RUNNING, false)
        set(value) = prefs.edit().putBoolean(KEY_SERVICE_RUNNING, value).apply()

    var dailySentCount: Int
        get() = prefs.getInt(KEY_DAILY_SENT_COUNT, 0)
        set(value) = prefs.edit().putInt(KEY_DAILY_SENT_COUNT, value).apply()

    // AI Control preferences
    fun isAiEnabledForContact(phone: String): Boolean {
        val disabledSet = prefs.getStringSet(KEY_AI_DISABLED_NUMBERS, emptySet()) ?: emptySet()
        val cleanPhone = phone.trim().replace(" ", "")
        return !disabledSet.contains(cleanPhone)
    }

    fun setAiEnabledForContact(phone: String, enabled: Boolean) {
        val cleanPhone = phone.trim().replace(" ", "")
        val disabledSet = (prefs.getStringSet(KEY_AI_DISABLED_NUMBERS, emptySet()) ?: emptySet()).toMutableSet()
        if (enabled) {
            disabledSet.remove(cleanPhone)
        } else {
            disabledSet.add(cleanPhone)
        }
        prefs.edit().putStringSet(KEY_AI_DISABLED_NUMBERS, disabledSet).apply()
    }

    fun isContactBlocked(phone: String): Boolean {
        val blockedSet = prefs.getStringSet(KEY_BLOCKED_NUMBERS, emptySet()) ?: emptySet()
        val cleanPhone = phone.trim().replace(" ", "")
        return blockedSet.contains(cleanPhone)
    }

    fun setContactBlocked(phone: String, blocked: Boolean) {
        val cleanPhone = phone.trim().replace(" ", "")
        val blockedSet = (prefs.getStringSet(KEY_BLOCKED_NUMBERS, emptySet()) ?: emptySet()).toMutableSet()
        if (blocked) {
            blockedSet.add(cleanPhone)
            // If blocked, also disable AI
            setAiEnabledForContact(cleanPhone, false)
        } else {
            blockedSet.remove(cleanPhone)
        }
        prefs.edit().putStringSet(KEY_BLOCKED_NUMBERS, blockedSet).apply()
    }

    fun clearCredentials() {
        prefs.edit()
            .remove(KEY_DEVICE_TOKEN)
            .remove(KEY_DEVICE_ID)
            .remove(KEY_LAST_SYNC)
            .apply()
    }

    companion object {
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_DEVICE_TOKEN = "device_token"
        private const val KEY_DEVICE_ID = "device_id"
        private const val KEY_DEVICE_NAME = "device_name"
        private const val KEY_AUTO_SYNC = "auto_sync"
        private const val KEY_SYNC_INTERVAL = "sync_interval"
        private const val KEY_NOTIFICATIONS = "notifications_enabled"
        private const val KEY_LAST_SYNC = "last_sync_timestamp"
        private const val KEY_SERVICE_RUNNING = "service_running"
        private const val KEY_DAILY_SENT_COUNT = "daily_sent_count"
        private const val KEY_AI_DISABLED_NUMBERS = "ai_disabled_numbers"
        private const val KEY_BLOCKED_NUMBERS = "blocked_numbers"
    }
}
