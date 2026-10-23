package com.simsms.gateway.data.api

import com.simsms.gateway.data.api.models.DeviceHeartbeatRequest
import com.simsms.gateway.data.api.models.DeviceJobResponse
import com.simsms.gateway.data.api.models.DevicePairRequest
import com.simsms.gateway.data.api.models.DevicePairResponse
import com.simsms.gateway.data.api.models.DeviceSendResultRequest
import com.simsms.gateway.data.api.models.GatewayDeviceResponse
import com.simsms.gateway.data.api.models.HealthResponse
import com.simsms.gateway.data.api.models.IncomingMessageResponse
import com.simsms.gateway.data.api.models.IncomingSmsReportRequest
import com.simsms.gateway.data.api.models.MessageResponse
import com.simsms.gateway.data.api.models.OutgoingMessageCreateRequest
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

interface GatewayApiService {

    @GET("/health")
    suspend fun healthCheck(): Response<HealthResponse>

    @POST("/api/v1/devices/pair")
    suspend fun pairDevice(
        @Body request: DevicePairRequest
    ): Response<DevicePairResponse>

    @POST("/api/v1/devices/heartbeat")
    suspend fun sendHeartbeat(
        @Header("Authorization") bearerToken: String,
        @Body request: DeviceHeartbeatRequest
    ): Response<GatewayDeviceResponse>

    @GET("/api/v1/devices/jobs/next")
    suspend fun fetchNextJob(
        @Header("Authorization") bearerToken: String
    ): Response<DeviceJobResponse?>

    @POST("/api/v1/devices/jobs/{jobId}/result")
    suspend fun submitJobResult(
        @Header("Authorization") bearerToken: String,
        @Path("jobId") jobId: String,
        @Body request: DeviceSendResultRequest
    ): Response<Map<String, Any>>

    @POST("/api/v1/devices/incoming")
    suspend fun reportIncomingSms(
        @Header("Authorization") bearerToken: String,
        @Body request: IncomingSmsReportRequest
    ): Response<IncomingMessageResponse>

    @POST("/api/v1/messages")
    suspend fun submitOutgoingMessage(
        @Header("Authorization") bearerToken: String,
        @Body request: OutgoingMessageCreateRequest
    ): Response<MessageResponse>
}
