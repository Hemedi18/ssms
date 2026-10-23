package com.simsms.gateway

import org.junit.Assert.*
import org.junit.Test
import java.security.MessageDigest

class PduHashDeduplicationTest {

    private fun generateIncomingMessageHash(sender: String, body: String, timestamp: Long): String {
        // Quantize timestamp to 10-second window to handle duplicate broadcast deliveries of the same SMS
        val quantizedTimestamp = (timestamp / 10000) * 10000
        val raw = "$sender:$body:$quantizedTimestamp"
        val bytes = MessageDigest.getInstance("SHA-256").digest(raw.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }
    }

    @Test
    fun testSameMessageWithinWindowProducesIdenticalHash() {
        val t0 = 1700000000000L
        val tDuplicate = t0 + 2000L // 2 seconds later (duplicate broadcast)

        val hash1 = generateIncomingMessageHash("+255712345678", "Payment received: $50", t0)
        val hash2 = generateIncomingMessageHash("+255712345678", "Payment received: $50", tDuplicate)

        assertEquals(hash1, hash2)
    }

    @Test
    fun testDifferentSenderProducesDifferentHash() {
        val t0 = 1700000000000L
        val hash1 = generateIncomingMessageHash("+255712345678", "Hello", t0)
        val hash2 = generateIncomingMessageHash("+255799999999", "Hello", t0)

        assertNotEquals(hash1, hash2)
    }

    @Test
    fun testDifferentBodyProducesDifferentHash() {
        val t0 = 1700000000000L
        val hash1 = generateIncomingMessageHash("+255712345678", "Code: 1234", t0)
        val hash2 = generateIncomingMessageHash("+255712345678", "Code: 5678", t0)

        assertNotEquals(hash1, hash2)
    }
}
