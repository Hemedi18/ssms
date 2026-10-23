package com.simsms.gateway

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import com.simsms.gateway.data.local.AppDatabase
import com.simsms.gateway.data.local.SecurePreferences
import com.simsms.gateway.data.repository.GatewayRepository
import com.simsms.gateway.service.RealSmsManager

class GatewayApplication : Application() {

    lateinit var database: AppDatabase
        private set

    lateinit var securePrefs: SecurePreferences
        private set

    lateinit var smsManager: RealSmsManager
        private set

    lateinit var repository: GatewayRepository
        private set

    override fun onCreate() {
        super.onCreate()

        database = AppDatabase.getDatabase(this)
        securePrefs = SecurePreferences(this)
        smsManager = RealSmsManager(this)
        repository = GatewayRepository(this, database, securePrefs, smsManager)

        createNotificationChannels()
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID_GATEWAY,
                getString(R.string.channel_name),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = getString(R.string.channel_description)
                setShowBadge(false)
            }

            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager?.createNotificationChannel(channel)
        }
    }

    companion object {
        const val CHANNEL_ID_GATEWAY = "sim_sms_gateway_service_channel"
        const val NOTIFICATION_ID_SERVICE = 1001
    }
}
