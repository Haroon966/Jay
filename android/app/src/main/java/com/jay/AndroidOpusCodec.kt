package com.jay

import org.concentus.OpusApplication
import org.concentus.OpusDecoder
import org.concentus.OpusEncoder

/**
 * Lightweight wrapper for 16 kHz mono Opus encode/decode.
 */
class AndroidOpusCodec(
    sampleRate: Int = Protocol.SAMPLE_RATE,
    channels: Int = 1,
    bitrate: Int = 16_000
) {
    private val encoder = OpusEncoder(sampleRate, channels, OpusApplication.OPUS_APPLICATION_VOIP).apply {
        this.bitrate = bitrate
    }
    private val decoder = OpusDecoder(sampleRate, channels)

    fun encode(pcm: ShortArray, frameSamples: Int, out: ByteArray): Int {
        return encoder.encode(pcm, 0, frameSamples, out, 0, out.size)
    }

    fun decode(packet: ByteArray, outPcm: ShortArray, frameSamples: Int): Int {
        return decoder.decode(packet, 0, packet.size, outPcm, 0, frameSamples, false)
    }
}
