package com.simsms.gateway.ui.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.simsms.gateway.GatewayApplication
import com.simsms.gateway.data.local.entities.LocalIncomingMessage
import com.simsms.gateway.data.local.entities.LocalLog
import com.simsms.gateway.data.local.entities.LocalMessage
import com.simsms.gateway.service.GatewayForegroundService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class GatewayStats(
    val sentCount: Int = 0,
    val deliveredCount: Int = 0,
    val pendingCount: Int = 0,
    val failedCount: Int = 0,
    val receivedCount: Int = 0
)

class GatewayViewModel(application: Application) : AndroidViewModel(application) {

    private val app = application as GatewayApplication
    val repository = app.repository
    val prefs = app.securePrefs

    // Database flows
    val messages: StateFlow<List<LocalMessage>> = repository.allMessagesFlow.stateIn(
        viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList()
    )

    val incomingMessages: StateFlow<List<LocalIncomingMessage>> = repository.incomingMessagesFlow.stateIn(
        viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList()
    )

    val logs: StateFlow<List<LocalLog>> = repository.logsFlow.stateIn(
        viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList()
    )

    val isConnected: StateFlow<Boolean> = repository.isConnected

    // Local UI states
    private val _isPaired = MutableStateFlow(prefs.isPaired)
    val isPaired = _isPaired.asStateFlow()

    private val _isServiceRunning = MutableStateFlow(prefs.isServiceRunning)
    val isServiceRunning = _isServiceRunning.asStateFlow()

    private val _isConnecting = MutableStateFlow(false)
    val isConnecting = _isConnecting.asStateFlow()

    private val _connectionResult = MutableStateFlow<String?>(null)
    val connectionResult = _connectionResult.asStateFlow()

    private val _connectionError = MutableStateFlow<String?>(null)
    val connectionError = _connectionError.asStateFlow()

    private val _isSendingSms = MutableStateFlow(false)
    val isSendingSms = _isSendingSms.asStateFlow()

    private val _sendResult = MutableStateFlow<Pair<Boolean, String>?>(null)
    val sendResult = _sendResult.asStateFlow()

    // SIM state
    val isSimReady: Boolean
        get() = repository.smsManager.isSimReady()

    val simCarrierName: String?
        get() = repository.smsManager.getSimCarrierName()

    val simPhoneNumber: String?
        get() = repository.smsManager.getSimPhoneNumber()

    fun testConnection(url: String) {
        viewModelScope.launch {
            _isConnecting.value = true
            _connectionResult.value = null
            _connectionError.value = null
            val result = repository.testConnection(url)
            _isConnecting.value = false
            if (result.isSuccess) {
                _connectionResult.value = result.getOrNull()
            } else {
                _connectionError.value = result.exceptionOrNull()?.message
            }
        }
    }

    fun pairDevice(serverUrl: String, pairingCode: String, deviceName: String, onSuccess: () -> Unit) {
        viewModelScope.launch {
            _isConnecting.value = true
            _connectionResult.value = null
            _connectionError.value = null
            val result = repository.pairDevice(serverUrl, pairingCode, deviceName)
            _isConnecting.value = false
            if (result.isSuccess) {
                _isPaired.value = true
                _connectionResult.value = result.getOrNull()
                // Auto start foreground service once paired
                toggleGatewayService(true)
                onSuccess()
            } else {
                _connectionError.value = result.exceptionOrNull()?.message
            }
        }
    }

    fun toggleGatewayService(start: Boolean) {
        if (start) {
            GatewayForegroundService.start(app)
            _isServiceRunning.value = true
        } else {
            GatewayForegroundService.stop(app)
            _isServiceRunning.value = false
        }
    }

    fun sendManualSms(destination: String, text: String) {
        viewModelScope.launch {
            _isSendingSms.value = true
            _sendResult.value = null
            val result = repository.sendManualSms(destination, text)
            _isSendingSms.value = false
            if (result.isSuccess) {
                _sendResult.value = Pair(true, "SMS queued and dispatched with ID: ${result.getOrNull()}")
            } else {
                _sendResult.value = Pair(false, result.exceptionOrNull()?.message ?: "Failed to send SMS")
            }
        }
    }

    fun retryMessage(messageId: String) {
        viewModelScope.launch {
            repository.retryFailedMessage(messageId)
        }
    }

    fun disconnectServer() {
        viewModelScope.launch {
            toggleGatewayService(false)
            prefs.clearCredentials()
            _isPaired.value = false
            repository.logEvent("Connection", "Device disconnected and local credentials purged.")
        }
    }

    fun updateSettings(autoSync: Boolean, intervalSeconds: Int, notifications: Boolean) {
        prefs.autoSyncEnabled = autoSync
        prefs.syncIntervalSeconds = intervalSeconds
        prefs.notificationsEnabled = notifications
    }

    fun clearSendResult() {
        _sendResult.value = null
    }

    fun clearLogs() {
        viewModelScope.launch {
            repository.database.logDao().clearAll()
            repository.logEvent("System", "Diagnostic logs cleared by user.")
        }
    }
}
