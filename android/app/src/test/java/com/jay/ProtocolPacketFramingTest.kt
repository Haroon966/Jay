package com.jay

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ProtocolPacketFramingTest {

    @Test
    fun packetRoundTripUsesLeHeader() {
        val payload = byteArrayOf(1, 2, 3, 4, 5)
        val frame = frame(payload)
        assertEquals(payload.size, frame[0].toInt() and 0xff)
        assertEquals(0, frame[1].toInt() and 0xff)

        val decoded = parse(frame)
        assertArrayEquals(payload, decoded)
    }

    @Test
    fun parserRejectsZeroAndOversizedFrames() {
        val zero = byteArrayOf(0, 0)
        val oversized = byteArrayOf((Protocol.MAX_PAYLOAD_LEN + 1).toByte(), 0x02)
        assertNull(parse(zero))
        assertNull(parse(oversized))
    }

    private fun frame(payload: ByteArray): ByteArray {
        require(payload.isNotEmpty() && payload.size <= Protocol.MAX_PAYLOAD_LEN)
        val out = ByteArray(Protocol.PACKET_HEADER_SIZE + payload.size)
        out[0] = (payload.size and 0xff).toByte()
        out[1] = ((payload.size shr 8) and 0xff).toByte()
        payload.copyInto(out, destinationOffset = Protocol.PACKET_HEADER_SIZE)
        return out
    }

    private fun parse(packet: ByteArray): ByteArray? {
        if (packet.size < Protocol.PACKET_HEADER_SIZE) return null
        val len = (packet[0].toInt() and 0xff) or ((packet[1].toInt() and 0xff) shl 8)
        if (len <= 0 || len > Protocol.MAX_PAYLOAD_LEN) return null
        if (packet.size < Protocol.PACKET_HEADER_SIZE + len) return null
        return packet.copyOfRange(Protocol.PACKET_HEADER_SIZE, Protocol.PACKET_HEADER_SIZE + len)
    }
}
