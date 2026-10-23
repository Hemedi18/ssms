package com.simsms.gateway

import org.junit.Assert.*
import org.junit.Test

class ValidationTest {

    private fun isValidE164(phone: String): Boolean {
        val regex = Regex("^\\+[1-9]\\d{1,14}\$")
        return regex.matches(phone)
    }

    private fun calculateSmsParts(text: String): Int {
        val length = text.length
        return when {
            length == 0 -> 0
            length <= 160 -> 1
            else -> Math.ceil(length / 153.0).toInt()
        }
    }

    @Test
    fun testValidE164PhoneNumbers() {
        assertTrue(isValidE164("+255712345678"))
        assertTrue(isValidE164("+14155552671"))
        assertTrue(isValidE164("+447911123456"))
        assertTrue(isValidE164("+254700000000"))
    }

    @Test
    fun testInvalidE164PhoneNumbers() {
        assertFalse(isValidE164("0712345678"))
        assertFalse(isValidE164("712345678"))
        assertFalse(isValidE164("+0123456")) // Cannot start with 0 after +
        assertFalse(isValidE164("+"))
        assertFalse(isValidE164(""))
        assertFalse(isValidE164("+1234567890123456")) // > 15 digits
        assertFalse(isValidE164("invalid-phone"))
    }

    @Test
    fun testSinglePartSmsCalculation() {
        assertEquals(0, calculateSmsParts(""))
        assertEquals(1, calculateSmsParts("Hello World"))
        assertEquals(1, calculateSmsParts("A".repeat(160)))
    }

    @Test
    fun testMultipartSmsCalculation() {
        assertEquals(2, calculateSmsParts("A".repeat(161)))
        assertEquals(2, calculateSmsParts("A".repeat(306)))
        assertEquals(3, calculateSmsParts("A".repeat(307)))
    }
}
