package com.jay

import org.junit.Assert.assertEquals
import org.junit.Test

class ReconnectBackoffPolicyTest {

    @Test
    fun reconnectBackoffSequenceMatchesSpecBudget() {
        var backoff = Protocol.DISCOVERY_BACKOFF_MIN_MS
        val values = mutableListOf<Int>()
        repeat(5) {
            values += backoff
            backoff = (backoff * 2).coerceAtMost(Protocol.DISCOVERY_BACKOFF_MAX_MS)
        }
        assertEquals(listOf(1000, 2000, 4000, 8000, 12000), values)
    }
}
