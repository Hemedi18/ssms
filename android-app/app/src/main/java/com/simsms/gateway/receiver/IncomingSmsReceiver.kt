package com.simsms.gateway.receiver

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import android.telephony.SmsMessage
import android.util.Log
import com.simsms.gateway.GatewayApplication
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.security.MessageDigest

class IncomingSmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val app = context.applicationContext as? GatewayApplication ?: return
        val repository = app.repository

        val messages: Array<SmsMessage>? = try {
            Telephony.Sms.Intents.getMessagesFromIntent(intent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse SMS PDUs from intent: ${e.message}")
            null
        }

        if (messages.isNullOrEmpty()) return

        val pendingResult = goAsync()

        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Group multipart messages by originating address
                val messagesBySender = messages.groupBy { it.originatingAddress ?: "Unknown" }

                for ((sender, parts) in messagesBySender) {
                    val fullBody = parts.joinToString(separator = "") { it.messageBody ?: "" }
                    val timestamp = parts.firstOrNull()?.timestampMillis ?: System.currentTimeMillis()

                    val rawHash = computePduHash(sender, fullBody, timestamp)

                    Log.i(TAG, "Incoming SMS from $sender (${parts.size} parts): ${fullBody.take(20)}...")
                    repository.onIncomingSmsReceived(
                        sender = sender,
                        body = fullBody,
                        receivedAt = timestamp,
                        isMultipart = parts.size > 1,
                        totalParts = parts.size,
                        pduHash = rawHash
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error handling incoming SMS broadcast: ${e.message}", e)
            } finally {
                pendingResult.finish()
            }
        }
    }

    private fun computePduHash(sender: String, body: String, timestamp: Long): String {
        val input = "$sender:$body:$timestamp"
        val md = MessageDigest.getInstance("SHA-256")
        val bytes = md.digest(input.toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it) }
    }

    companion object {
        private const val TAG = "IncomingSmsReceiver"
    }
}
