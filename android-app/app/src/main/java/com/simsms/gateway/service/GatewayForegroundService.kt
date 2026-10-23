package com.simsms.gateway.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.simsms.gateway.GatewayApplication
import com.simsms.gateway.MainActivity
import com.simsms.gateway.R
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class GatewayForegroundService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.IO + Job())
    private var loopJob: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "GatewayForegroundService onCreate")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP_SERVICE) {
            stopForegroundService()
            return START_NOT_STICKY
        }

        startForegroundNotification()
        startPollingLoop()

        val app = applicationContext as? GatewayApplication
        app?.securePrefs?.isServiceRunning = true

        return START_STICKY
    }

    private fun startForegroundNotification() {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val notification: Notification = NotificationCompat.Builder(this, GatewayApplication.CHANNEL_ID_GATEWAY)
            .setContentTitle("SIM SMS Gateway Active")
            .setContentText("Listening for queued messages & synchronizing SMS...")
            .setSmallIcon(R.drawable.ic_sms_logo)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                GatewayApplication.NOTIFICATION_ID_SERVICE,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(GatewayApplication.NOTIFICATION_ID_SERVICE, notification)
        }
    }

    private fun startPollingLoop() {
        loopJob?.cancel()
        loopJob = serviceScope.launch {
            val app = applicationContext as? GatewayApplication ?: return@launch
            val repository = app.repository
            val prefs = app.securePrefs

            var heartbeatCounter = 0

            while (isActive) {
                try {
                    if (prefs.isPaired && prefs.autoSyncEnabled) {
                        // 1. Poll for next job
                        repository.pollAndExecuteNextJob()

                        // 2. Sync unsynced incoming SMS
                        repository.syncPendingIncomingMessages()

                        // 3. Heartbeat every 30 seconds
                        heartbeatCounter++
                        if (heartbeatCounter >= 6) {
                            repository.sendHeartbeat()
                            heartbeatCounter = 0
                        }
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Error in gateway service loop: ${e.message}")
                }

                val intervalSec = prefs.syncIntervalSeconds.coerceAtLeast(3)
                delay(intervalSec * 1000L)
            }
        }
    }

    private fun stopForegroundService() {
        Log.i(TAG, "Stopping GatewayForegroundService")
        loopJob?.cancel()
        val app = applicationContext as? GatewayApplication
        app?.securePrefs?.isServiceRunning = false

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            stopForeground(STOP_FOREGROUND_REMOVE)
        } else {
            @Suppress("DEPRECATION")
            stopForeground(true)
        }
        stopSelf()
    }

    override fun onDestroy() {
        super.onDestroy()
        loopJob?.cancel()
        val app = applicationContext as? GatewayApplication
        app?.securePrefs?.isServiceRunning = false
        Log.i(TAG, "GatewayForegroundService onDestroy")
    }

    companion object {
        private const val TAG = "GatewayService"
        const val ACTION_START_SERVICE = "com.simsms.gateway.START_SERVICE"
        const val ACTION_STOP_SERVICE = "com.simsms.gateway.STOP_SERVICE"

        fun start(context: Context) {
            val intent = Intent(context, GatewayForegroundService::class.java).apply {
                action = ACTION_START_SERVICE
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            val intent = Intent(context, GatewayForegroundService::class.java).apply {
                action = ACTION_STOP_SERVICE
            }
            context.startService(intent)
        }
    }
}
