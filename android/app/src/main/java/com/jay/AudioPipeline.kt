package com.jay

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Dispatchers

/**
 * Capture mic -> "encode" (passthrough PCM) -> send; receive payload -> "decode" (passthrough) -> play.
 * For Opus interop with ESP32, replace passthrough with Opus encode/decode (16 kHz, mono, 20 ms, 16 kbps).
 */
class AudioPipeline(private val scope: CoroutineScope) {

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var captureJob: Job? = null
    private val bufSize = AudioRecord.getMinBufferSize(Protocol.SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        .coerceAtLeast(Protocol.FRAME_SAMPLES * 2 * 2)

    fun start(sendPayload: (ByteArray) -> Unit) {
        val minBuf = AudioRecord.getMinBufferSize(Protocol.SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT)
        val recBufSize = (Protocol.FRAME_SAMPLES * 2 * 4).coerceAtLeast(minBuf)
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.MIC,
            Protocol.SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            recBufSize
        )
        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            Log.e(TAG, "AudioRecord init failed")
            return
        }

        val playBufSize = AudioTrack.getMinBufferSize(Protocol.SAMPLE_RATE, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)
        audioTrack = AudioTrack.Builder()
            .setAudioFormat(
                android.media.AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(Protocol.SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes((Protocol.FRAME_SAMPLES * 2 * 4).coerceAtLeast(playBufSize))
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        if (audioTrack?.state != AudioTrack.STATE_INITIALIZED) {
            Log.e(TAG, "AudioTrack init failed")
            return
        }

        audioRecord?.startRecording()
        audioTrack?.play()

        captureJob = scope.launch(Dispatchers.IO) {
            val frame = ShortArray(Protocol.FRAME_SAMPLES)
            val byteBuf = ByteArray(Protocol.FRAME_SAMPLES * 2)
            while (scope.isActive) {
                val rec = audioRecord ?: break
                val read = rec.read(frame, 0, frame.size)
                if (read == Protocol.FRAME_SAMPLES) {
                    for (i in 0 until read) {
                        byteBuf[i * 2] = (frame[i].toInt() and 0xff).toByte()
                        byteBuf[i * 2 + 1] = (frame[i].toInt() shr 8).toByte()
                    }
                    sendPayload(byteBuf)
                }
                delay(15)
            }
        }
    }

    fun playPayload(payload: ByteArray) {
        if (payload.size < Protocol.FRAME_SAMPLES * 2) return
        val track = audioTrack ?: return
        val shorts = ShortArray(Protocol.FRAME_SAMPLES)
        for (i in 0 until Protocol.FRAME_SAMPLES) {
            shorts[i] = (payload[i * 2].toInt() and 0xff or (payload[i * 2 + 1].toInt() shl 8)).toShort()
        }
        track.write(shorts, 0, shorts.size)
    }

    fun stop() {
        captureJob?.cancel()
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        audioTrack?.stop()
        audioTrack?.release()
        audioTrack = null
    }

    companion object {
        private const val TAG = "AudioPipeline"
    }
}
