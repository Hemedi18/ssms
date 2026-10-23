package com.simsms.gateway.data.repository

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.util.Log
import com.simsms.gateway.data.api.ApiClient
import com.simsms.gateway.data.api.GatewayApiService
import com.simsms.gateway.data.api.models.DeviceHeartbeatRequest
import com.simsms.gateway.data.api.models.DevicePairRequest
import com.simsms.gateway.data.api.models.DeviceSendResultRequest
import com.simsms.gateway.data.api.models.IncomingSmsReportRequest
import com.simsms.gateway.data.api.models.OutgoingMessageCreateRequest
import com.simsms.gateway.data.local.AppDatabase
import com.simsms.gateway.data.local.SecurePreferences
import com.simsms.gateway.data.local.entities.LocalIncomingMessage
import com.simsms.gateway.data.local.entities.LocalLog
import com.simsms.gateway.data.local.entities.LocalMessage
import com.simsms.gateway.service.RealSmsManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.UUID

class GatewayRepository(
    private val context: Context,
    val database: AppDatabase,
    val securePrefs: SecurePreferences,
    val smsManager: RealSmsManager
) {
    private val _isConnected = MutableStateFlow(false)
    val isConnected = _isConnected.asStateFlow()

    private val _lastError = MutableStateFlow<String?>(null)
    val lastError = _lastError.asStateFlow()

    private val apiService: GatewayApiService
        get() = ApiClient.getService(securePrefs.serverUrl)

    private val isoDateFormat = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US).apply {
        timeZone = TimeZone.getTimeZone("UTC")
    }

    // Flows for UI
    val allMessagesFlow: Flow<List<LocalMessage>> = database.messageDao().getAllFlow()
    val incomingMessagesFlow: Flow<List<LocalIncomingMessage>> = database.incomingDao().getAllFlow()
    val logsFlow: Flow<List<LocalLog>> = database.logDao().getAllFlow()

    val sentCountFlow: Flow<Int> = database.messageDao().getSentCountFlow()
    val deliveredCountFlow: Flow<Int> = database.messageDao().getDeliveredCountFlow()
    val pendingCountFlow: Flow<Int> = database.messageDao().getPendingCountFlow()
    val failedCountFlow: Flow<Int> = database.messageDao().getFailedCountFlow()
    val receivedCountFlow: Flow<Int> = database.incomingDao().getCountFlow()

    suspend fun logEvent(category: String, message: String, details: String? = null) {
        val safeMessage = redactSensitive(message)
        database.logDao().insert(
            LocalLog(category = category, message = safeMessage, details = details)
        )
    }

    private fun redactSensitive(text: String): String {
        return text.replace(Regex("(Bearer\\s+)[A-Za-z0-9_\\-\\.]+"), "$1[REDACTED]")
            .replace(Regex("dev_tok_[A-Za-z0-9_\\-]+"), "[REDACTED]")
            .replace(Regex("(\\+?[0-9]{3})[0-9]{4,}([0-9]{3})"), "$1****$2")
    }

    suspend fun testConnection(url: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            val service = ApiClient.getService(url)
            val response = service.healthCheck()
            if (response.isSuccessful && response.body() != null) {
                val body = response.body()!!
                _isConnected.value = true
                _lastError.value = null
                logEvent("Connection", "Server health check passed: ${body.service} v${body.version}")
                Result.success("Connected to ${body.service} (${body.version})")
            } else {
                val err = "HTTP ${response.code()}: ${response.errorBody()?.string() ?: "Server error"}"
                _isConnected.value = false
                _lastError.value = err
                logEvent("Error", "Server health check failed: $err")
                Result.failure(Exception(err))
            }
        } catch (e: Exception) {
            _isConnected.value = false
            val msg = e.message ?: "Connection failed"
            _lastError.value = msg
            logEvent("Error", "Server connection exception: $msg")
            Result.failure(e)
        }
    }

    suspend fun pairDevice(serverUrl: String, pairingCode: String, deviceName: String): Result<String> = withContext(Dispatchers.IO) {
        try {
            securePrefs.serverUrl = serverUrl
            val service = ApiClient.getService(serverUrl)

            val request = DevicePairRequest(
                pairingCode = pairingCode.trim().uppercase(),
                deviceName = deviceName.ifBlank { "Android Gateway Device" },
                model = "${Build.MANUFACTURER} ${Build.MODEL}",
                osVersion = "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})",
                appVersion = "1.0.0"
            )

            val response = service.pairDevice(request)
            if (response.isSuccessful && response.body() != null) {
                val data = response.body()!!
                securePrefs.deviceToken = data.deviceToken
                securePrefs.deviceId = data.deviceId
                securePrefs.deviceName = data.name
                securePrefs.lastSyncTimestamp = System.currentTimeMillis()

                _isConnected.value = true
                _lastError.value = null
                logEvent("Connection", "Device paired successfully with ID: ${data.deviceId}")
                Result.success(data.message)
            } else {
                val err = response.errorBody()?.string() ?: "Pairing rejected by server (HTTP ${response.code()})"
                _isConnected.value = false
                _lastError.value = err
                logEvent("Error", "Device pairing failed: $err")
                Result.failure(Exception(err))
            }
        } catch (e: Exception) {
            _isConnected.value = false
            _lastError.value = e.message
            logEvent("Error", "Device pairing error: ${e.message}")
            Result.failure(e)
        }
    }

    suspend fun sendHeartbeat(): Boolean = withContext(Dispatchers.IO) {
        val token = securePrefs.deviceToken ?: return@withContext false
        try {
            val batteryLevel = getBatteryLevel()
            val request = DeviceHeartbeatRequest(
                simReady = smsManager.isSimReady(),
                phoneNumber = smsManager.getSimPhoneNumber(),
                carrierName = smsManager.getSimCarrierName(),
                networkType = "Cellular",
                signalLevel = 4,
                batteryLevel = batteryLevel
            )
            val response = apiService.sendHeartbeat("Bearer $token", request)
            if (response.isSuccessful) {
                _isConnected.value = true
                securePrefs.lastSyncTimestamp = System.currentTimeMillis()
                true
            } else {
                if (response.code() == 401) {
                    _isConnected.value = false
                    logEvent("Error", "Device token unauthorized or revoked by server.")
                }
                false
            }
        } catch (e: Exception) {
            _isConnected.value = false
            false
        }
    }

    suspend fun pollAndExecuteNextJob(): Boolean = withContext(Dispatchers.IO) {
        val token = securePrefs.deviceToken ?: return@withContext false
        if (!smsManager.isSimReady()) {
            return@withContext false
        }

        try {
            val response = apiService.fetchNextJob("Bearer $token")
            if (response.code() == 204 || response.body() == null) {
                // Queue is empty
                return@withContext false
            }

            if (!response.isSuccessful) {
                return@withContext false
            }

            val job = response.body()!!
            logEvent("Sent", "Claimed queued SMS job ${job.jobId} for recipient ${job.to}")

            // 1. Record in local Room
            val localMessage = LocalMessage(
                id = job.jobId,
                to = job.to,
                body = job.body,
                status = "sending",
                partsCount = job.partsCount,
                leaseToken = job.leaseToken,
                createdAt = System.currentTimeMillis()
            )
            database.messageDao().insert(localMessage)

            // 2. Dispatch via physical SMS Manager
            val sendResult = smsManager.sendSms(
                messageId = job.jobId,
                destinationAddress = job.to,
                text = job.body
            )

            if (sendResult.isFailure) {
                val errorMsg = sendResult.exceptionOrNull()?.message ?: "Radio error"
                database.messageDao().updateStatus(job.jobId, "failed", errorMsg)
                reportSendResult(job.jobId, "failed", errorMsg)
            }

            true
        } catch (e: Exception) {
            logEvent("Error", "Job poll failed: ${e.message}")
            false
        }
    }

    suspend fun reportSendResult(jobId: String, status: String, errorMessage: String? = null) = withContext(Dispatchers.IO) {
        val token = securePrefs.deviceToken ?: return@withContext
        try {
            val req = DeviceSendResultRequest(
                status = status,
                errorMessage = errorMessage,
                timestamp = isoDateFormat.format(Date())
            )
            val res = apiService.submitJobResult("Bearer $token", jobId, req)
            if (res.isSuccessful) {
                logEvent("Sent", "Reported status '$status' for job $jobId to server.")
            }
        } catch (e: Exception) {
            logEvent("Error", "Failed to report result for $jobId: ${e.message}")
        }
    }

    suspend fun onSmsPartSent(messageId: String, partIndex: Int, totalParts: Int) {
        // If all parts sent, mark sent in Room and report to backend
        if (partIndex >= totalParts - 1) {
            database.messageDao().markSent(messageId)
            logEvent("Sent", "Message $messageId sent successfully ($totalParts parts).")
            reportSendResult(messageId, "sent")
        }
    }

    suspend fun onSmsSendFailed(messageId: String, errorDescription: String) {
        database.messageDao().updateStatus(messageId, "failed", errorDescription)
        logEvent("Error", "Message $messageId failed: $errorDescription")
        reportSendResult(messageId, "failed", errorDescription)
    }

    suspend fun onSmsDelivered(messageId: String) {
        database.messageDao().markDelivered(messageId)
        logEvent("Sent", "Carrier delivery report received for message $messageId.")
        reportSendResult(messageId, "delivered")
    }

    suspend fun onIncomingSmsReceived(
        sender: String,
        body: String,
        receivedAt: Long,
        isMultipart: Boolean,
        totalParts: Int,
        pduHash: String
    ) = withContext(Dispatchers.IO) {
        // 1. Deduplication check in Room
        val existing = database.incomingDao().findDuplicate(sender, pduHash)
        if (existing != null) {
            Log.d(TAG, "Duplicate incoming SMS broadcast ignored")
            return@withContext
        }

        // 2. Insert into Room
        val incoming = LocalIncomingMessage(
            fromNumber = sender,
            body = body,
            receivedAt = receivedAt,
            isSynced = false,
            isMultipart = isMultipart,
            totalParts = totalParts,
            rawPduHash = pduHash
        )
        val localId = database.incomingDao().insert(incoming)
        logEvent("Received", "Received SMS from $sender (${body.length} chars)")

        // 3. Sync with backend immediately if online
        syncIncomingMessage(localId, incoming)
    }

    private suspend fun syncIncomingMessage(localId: Long, msg: LocalIncomingMessage) {
        val token = securePrefs.deviceToken ?: return
        try {
            val req = IncomingSmsReportRequest(
                fromNumber = msg.fromNumber,
                body = msg.body,
                receivedAt = isoDateFormat.format(Date(msg.receivedAt)),
                deviceMessageId = localId.toString(),
                isMultipart = msg.isMultipart,
                totalParts = msg.totalParts,
                pduHash = msg.rawPduHash
            )
            val res = apiService.reportIncomingSms("Bearer $token", req)
            if (res.isSuccessful && res.body() != null) {
                database.incomingDao().markSynced(localId, res.body()!!.id)
                logEvent("Received", "Synchronized incoming SMS $localId with backend (ID ${res.body()!!.id})")
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to synchronize incoming SMS $localId: ${e.message}")
        }
    }

    suspend fun syncPendingIncomingMessages() = withContext(Dispatchers.IO) {
        val unsynced = database.incomingDao().getUnsynced()
        for (item in unsynced) {
            syncIncomingMessage(item.id, item)
        }
    }

    suspend fun sendManualSms(destination: String, text: String): Result<String> = withContext(Dispatchers.IO) {
        val msgId = UUID.randomUUID().toString()
        val localMessage = LocalMessage(
            id = msgId,
            to = destination,
            body = text,
            status = "sending",
            createdAt = System.currentTimeMillis()
        )
        database.messageDao().insert(localMessage)
        logEvent("Sent", "Manual SMS initiated to $destination")

        val sendRes = smsManager.sendSms(msgId, destination, text)
        if (sendRes.isSuccess) {
            Result.success(msgId)
        } else {
            val err = sendRes.exceptionOrNull()?.message ?: "SMS dispatch failed"
            database.messageDao().updateStatus(msgId, "failed", err)
            Result.failure(Exception(err))
        }
    }

    suspend fun retryFailedMessage(messageId: String): Result<Unit> = withContext(Dispatchers.IO) {
        val msg = database.messageDao().getById(messageId) ?: return@withContext Result.failure(Exception("Message not found"))
        database.messageDao().updateStatus(messageId, "sending", null)
        logEvent("Sent", "Retrying failed message $messageId to ${msg.to}")

        val sendRes = smsManager.sendSms(messageId, msg.to, msg.body)
        if (sendRes.isSuccess) {
            Result.success(Unit)
        } else {
            val err = sendRes.exceptionOrNull()?.message ?: "Retry failed"
            database.messageDao().updateStatus(messageId, "failed", err)
            Result.failure(Exception(err))
        }
    }

    private fun getBatteryLevel(): Int {
        val batteryStatus: Intent? = IntentFilter(Intent.ACTION_BATTERY_CHANGED).let { filter ->
            context.registerReceiver(null, filter)
        }
        val level: Int = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale: Int = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        return if (level >= 0 && scale > 0) (level * 100 / scale) else 100
    }

    companion object {
        private const val TAG = "GatewayRepository"
    }
}
