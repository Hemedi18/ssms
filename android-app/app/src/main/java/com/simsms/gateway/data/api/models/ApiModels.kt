package com.simsms.gateway.data.api.models

import com.google.gson.annotations.SerializedName

data class DevicePairRequest(
    @SerializedName("pairing_code") val pairingCode: String,
    @SerializedName("device_name") val deviceName: String,
    @SerializedName("model") val model: String?,
    @SerializedName("os_version") val osVersion: String?,
    @SerializedName("app_version") val appVersion: String?
)

data class DevicePairResponse(
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("device_token") val deviceToken: String,
    @SerializedName("name") val name: String,
    @SerializedName("message") val message: String
)

data class SimSlotTelemetry(
    @SerializedName("slot") val slot: Int,
    @SerializedName("carrier") val carrier: String? = null,
    @SerializedName("number") val number: String? = null,
    @SerializedName("daily_sent") val dailySent: Int = 0,
    @SerializedName("limit") val limit: Int = 500,
    @SerializedName("signal_dbm") val signalDbm: Int? = null,
    @SerializedName("is_active") val isActive: Boolean = true
)

data class DeviceHeartbeatRequest(
    @SerializedName("sim_ready") val simReady: Boolean,
    @SerializedName("phone_number") val phoneNumber: String?,
    @SerializedName("carrier_name") val carrierName: String?,
    @SerializedName("network_type") val networkType: String?,
    @SerializedName("signal_level") val signalLevel: Int?,
    @SerializedName("battery_level") val batteryLevel: Int?,
    @SerializedName("battery_temperature") val batteryTemperature: Float? = null,
    @SerializedName("sim_slots") val simSlots: List<SimSlotTelemetry>? = null
)

data class GatewayDeviceResponse(
    @SerializedName("id") val id: String,
    @SerializedName("name") val name: String,
    @SerializedName("model") val model: String?,
    @SerializedName("sim_ready") val simReady: Boolean,
    @SerializedName("is_online") val isOnline: Boolean,
    @SerializedName("is_revoked") val isRevoked: Boolean
)

data class DeviceJobResponse(
    @SerializedName("job_id") val jobId: String,
    @SerializedName("message_id") val messageId: String,
    @SerializedName("to") val to: String,
    @SerializedName("body") val body: String,
    @SerializedName("lease_token") val leaseToken: String,
    @SerializedName("parts_count") val partsCount: Int,
    @SerializedName("sim_slot") val simSlot: Int? = null,
    @SerializedName("created_at") val createdAt: String
)

data class DeviceSendResultRequest(
    @SerializedName("status") val status: String, // sent, delivered, failed
    @SerializedName("error_message") val errorMessage: String? = null,
    @SerializedName("parts_sent") val partsSent: Int? = 1,
    @SerializedName("timestamp") val timestamp: String? = null
)

data class IncomingSmsReportRequest(
    @SerializedName("from_number") val fromNumber: String,
    @SerializedName("body") val body: String,
    @SerializedName("received_at") val receivedAt: String,
    @SerializedName("device_message_id") val deviceMessageId: String?,
    @SerializedName("is_multipart") val isMultipart: Boolean = false,
    @SerializedName("part_index") val partIndex: Int = 1,
    @SerializedName("total_parts") val totalParts: Int = 1,
    @SerializedName("pdu_hash") val pduHash: String? = null
)

data class IncomingMessageResponse(
    @SerializedName("id") val id: String,
    @SerializedName("from_number") val fromNumber: String,
    @SerializedName("body") val body: String,
    @SerializedName("received_at_device") val receivedAtDevice: String,
    @SerializedName("device_id") val deviceId: String?,
    @SerializedName("synced_at") val syncedAt: String
)

data class OutgoingMessageCreateRequest(
    @SerializedName("to") val to: String,
    @SerializedName("message") val message: String,
    @SerializedName("client_reference") val clientReference: String? = null
)

data class MessageResponse(
    @SerializedName("id") val id: String,
    @SerializedName("to") val to: String,
    @SerializedName("body") val body: String,
    @SerializedName("status") val status: String,
    @SerializedName("client_reference") val clientReference: String?,
    @SerializedName("parts_count") val partsCount: Int,
    @SerializedName("error_message") val errorMessage: String?,
    @SerializedName("created_at") val createdAt: String
)

data class HealthResponse(
    @SerializedName("status") val status: String,
    @SerializedName("service") val service: String,
    @SerializedName("version") val version: String,
    @SerializedName("database") val database: String
)
