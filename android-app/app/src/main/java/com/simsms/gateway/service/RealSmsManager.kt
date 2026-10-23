package com.simsms.gateway.service

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.telephony.SmsManager
import android.telephony.SubscriptionManager
import android.telephony.TelephonyManager
import android.util.Log
import com.simsms.gateway.receiver.SmsStatusReceiver

class RealSmsManager(private val context: Context) {

    private val telephonyManager = context.getSystemService(Context.TELEPHONY_SERVICE) as? TelephonyManager

    fun isSimReady(): Boolean {
        return telephonyManager?.simState == TelephonyManager.SIM_STATE_READY
    }

    fun getSimCarrierName(): String? {
        return telephonyManager?.simOperatorName?.takeIf { it.isNotBlank() }
            ?: telephonyManager?.networkOperatorName?.takeIf { it.isNotBlank() }
    }

    fun getSimPhoneNumber(): String? {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val subscriptionManager = context.getSystemService(SubscriptionManager::class.java)
                val defaultSubId = SubscriptionManager.getDefaultSubscriptionId()
                subscriptionManager?.getPhoneNumber(defaultSubId)?.takeIf { it.isNotBlank() }
            } else {
                @Suppress("DEPRECATION")
                telephonyManager?.line1Number?.takeIf { it.isNotBlank() }
            }
        } catch (e: SecurityException) {
            Log.w(TAG, "Cannot read phone number: missing permission READ_PHONE_NUMBERS or READ_PHONE_STATE")
            null
        }
    }

    fun sendSms(
        messageId: String,
        destinationAddress: String,
        text: String,
        subscriptionId: Int? = null
    ): Result<Int> {
        return try {
            val smsManager: SmsManager = if (subscriptionId != null && subscriptionId != SubscriptionManager.INVALID_SUBSCRIPTION_ID) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    context.getSystemService(SmsManager::class.java).createForSubscriptionId(subscriptionId)
                } else {
                    @Suppress("DEPRECATION")
                    SmsManager.getSmsManagerForSubscriptionId(subscriptionId)
                }
            } else {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    context.getSystemService(SmsManager::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    SmsManager.getDefault()
                }
            }

            val parts = smsManager.divideMessage(text)
            val partsCount = parts.size

            val flags = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            } else {
                PendingIntent.FLAG_UPDATE_CURRENT
            }

            val sentIntents = ArrayList<PendingIntent>()
            val deliveryIntents = ArrayList<PendingIntent>()

            for (i in 0 until partsCount) {
                val sentIntent = Intent(context, SmsStatusReceiver::class.java).apply {
                    action = SmsStatusReceiver.ACTION_SMS_SENT
                    putExtra(SmsStatusReceiver.EXTRA_MESSAGE_ID, messageId)
                    putExtra(SmsStatusReceiver.EXTRA_PART_INDEX, i)
                    putExtra(SmsStatusReceiver.EXTRA_TOTAL_PARTS, partsCount)
                }
                sentIntents.add(PendingIntent.getBroadcast(context, messageId.hashCode() + i, sentIntent, flags))

                val deliveryIntent = Intent(context, SmsStatusReceiver::class.java).apply {
                    action = SmsStatusReceiver.ACTION_SMS_DELIVERED
                    putExtra(SmsStatusReceiver.EXTRA_MESSAGE_ID, messageId)
                    putExtra(SmsStatusReceiver.EXTRA_PART_INDEX, i)
                    putExtra(SmsStatusReceiver.EXTRA_TOTAL_PARTS, partsCount)
                }
                deliveryIntents.add(PendingIntent.getBroadcast(context, messageId.hashCode() + 1000 + i, deliveryIntent, flags))
            }

            if (partsCount > 1) {
                Log.i(TAG, "Dispatching multipart SMS ($partsCount parts) for job $messageId to $destinationAddress")
                smsManager.sendMultipartTextMessage(
                    destinationAddress,
                    null,
                    parts,
                    sentIntents,
                    deliveryIntents
                )
            } else {
                Log.i(TAG, "Dispatching single-part SMS for job $messageId to $destinationAddress")
                smsManager.sendTextMessage(
                    destinationAddress,
                    null,
                    text,
                    sentIntents[0],
                    deliveryIntents[0]
                )
            }

            Result.success(partsCount)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to send SMS for job $messageId: ${e.message}", e)
            Result.failure(e)
        }
    }

    companion object {
        private const val TAG = "RealSmsManager"
    }
}
