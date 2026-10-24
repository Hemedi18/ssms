package com.simsms.gateway.receiver

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.SmsManager
import android.util.Log
import com.simsms.gateway.GatewayApplication
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class SmsStatusReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        // CRITICAL: Capture resultCode immediately on the main thread before background dispatch
        val capturedResultCode = resultCode
        val action = intent.action ?: return
        val messageId = intent.getStringExtra(EXTRA_MESSAGE_ID) ?: return
        val partIndex = intent.getIntExtra(EXTRA_PART_INDEX, 0)
        val totalParts = intent.getIntExtra(EXTRA_TOTAL_PARTS, 1)

        val app = context.applicationContext as? GatewayApplication ?: return
        val repository = app.repository

        val pendingResult = goAsync()

        CoroutineScope(Dispatchers.IO).launch {
            try {
                when (action) {
                    ACTION_SMS_SENT -> {
                        if (capturedResultCode == Activity.RESULT_OK) {
                            Log.i(TAG, "SMS part $partIndex/$totalParts sent OK for message $messageId")
                            repository.onSmsPartSent(messageId, partIndex, totalParts)
                        } else {
                            val errorDesc = getSmsErrorDescription(capturedResultCode)
                            Log.e(TAG, "SMS part $partIndex/$totalParts failed ($errorDesc, code=$capturedResultCode) for message $messageId")
                            repository.onSmsSendFailed(messageId, errorDesc)
                        }
                    }
                    ACTION_SMS_DELIVERED -> {
                        if (capturedResultCode == Activity.RESULT_OK) {
                            Log.i(TAG, "Carrier delivery report confirmed for message $messageId")
                            repository.onSmsDelivered(messageId)
                        } else {
                            Log.w(TAG, "Delivery receipt reported code $capturedResultCode for message $messageId")
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error processing SMS status callback: ${e.message}", e)
            } finally {
                pendingResult.finish()
            }
        }
    }

    private fun getSmsErrorDescription(resultCode: Int): String {
        return when (resultCode) {
            SmsManager.RESULT_ERROR_GENERIC_FAILURE -> "Generic carrier failure (RESULT_ERROR_GENERIC_FAILURE)"
            SmsManager.RESULT_ERROR_RADIO_OFF -> "Radio transmitter off or airplane mode (RESULT_ERROR_RADIO_OFF)"
            SmsManager.RESULT_ERROR_NULL_PDU -> "Null PDU payload (RESULT_ERROR_NULL_PDU)"
            SmsManager.RESULT_ERROR_NO_SERVICE -> "No cellular service or emergency only (RESULT_ERROR_NO_SERVICE)"
            SmsManager.RESULT_ERROR_LIMIT_EXCEEDED -> "SMS rate limit exceeded by OS (RESULT_ERROR_LIMIT_EXCEEDED)"
            else -> "Transmission error code: $resultCode"
        }
    }

    companion object {
        const val ACTION_SMS_SENT = "com.simsms.gateway.SMS_SENT"
        const val ACTION_SMS_DELIVERED = "com.simsms.gateway.SMS_DELIVERED"
        const val EXTRA_MESSAGE_ID = "extra_message_id"
        const val EXTRA_PART_INDEX = "extra_part_index"
        const val EXTRA_TOTAL_PARTS = "extra_total_parts"
        private const val TAG = "SmsStatusReceiver"
    }
}
