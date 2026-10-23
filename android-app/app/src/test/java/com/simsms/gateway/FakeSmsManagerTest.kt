package com.simsms.gateway

import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/**
 * Fake SMS transport for testing queue dispatch, callback simulation, and error cases
 * without needing physical cellular modem hardware.
 */
class FakeSmsTransport {
    data class SentRecord(
        val destination: String,
        val text: String,
        val messageId: String,
        val partsCount: Int,
        var status: String = "queued"
    )

    val history = mutableListOf<SentRecord>()
    var simReady: Boolean = true
    var shouldFail: Boolean = false

    fun sendSms(destination: String, text: String, messageId: String): Result<Int> {
        if (!simReady) {
            return Result.failure(IllegalStateException("SIM card is absent or locked."))
        }
        if (shouldFail) {
            return Result.failure(RuntimeException("Cellular network transmission failed: NO_SERVICE"))
        }

        val parts = if (text.length <= 160) 1 else Math.ceil(text.length / 153.0).toInt()
        val record = SentRecord(destination, text, messageId, parts, "dispatched")
        history.add(record)
        return Result.success(parts)
    }

    fun simulateSentCallback(messageId: String, success: Boolean) {
        val record = history.find { it.messageId == messageId }
        if (record != null) {
            record.status = if (success) "sent" else "failed"
        }
    }

    fun simulateDeliveryCallback(messageId: String, success: Boolean) {
        val record = history.find { it.messageId == messageId }
        if (record != null) {
            record.status = if (success) "delivered" else "delivery_failed"
        }
    }
}

class FakeSmsManagerTest {

    private lateinit var transport: FakeSmsTransport

    @Before
    fun setup() {
        transport = FakeSmsTransport()
    }

    @Test
    fun testSuccessfulSinglePartDispatch() {
        val result = transport.sendSms("+255712345678", "Hello Gateway", "msg-1")
        assertTrue(result.isSuccess)
        assertEquals(1, result.getOrNull())
        assertEquals(1, transport.history.size)
        assertEquals("dispatched", transport.history[0].status)
    }

    @Test
    fun testSuccessfulMultipartDispatch() {
        val longText = "This is a long message intended to test multi-part concatenation. ".repeat(4)
        val result = transport.sendSms("+255712345678", longText, "msg-2")
        assertTrue(result.isSuccess)
        assertTrue(result.getOrNull()!! > 1)
        assertEquals(1, transport.history.size)
        assertEquals(result.getOrNull(), transport.history[0].partsCount)
    }

    @Test
    fun testSimAbsentFails() {
        transport.simReady = false
        val result = transport.sendSms("+255712345678", "Hello", "msg-3")
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()?.message?.contains("SIM") == true)
        assertEquals(0, transport.history.size)
    }

    @Test
    fun testNetworkTransmissionFailure() {
        transport.shouldFail = true
        val result = transport.sendSms("+255712345678", "Hello", "msg-4")
        assertTrue(result.isFailure)
        assertTrue(result.exceptionOrNull()?.message?.contains("NO_SERVICE") == true)
    }

    @Test
    fun testStatusTransitionsFromCallbacks() {
        transport.sendSms("+255712345678", "Test callbacks", "msg-5")
        assertEquals("dispatched", transport.history[0].status)

        // Sent callback
        transport.simulateSentCallback("msg-5", success = true)
        assertEquals("sent", transport.history[0].status)

        // Delivery callback
        transport.simulateDeliveryCallback("msg-5", success = true)
        assertEquals("delivered", transport.history[0].status)
    }
}
