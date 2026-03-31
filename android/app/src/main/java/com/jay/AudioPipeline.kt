package com.jay

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.Dispatchers
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit

/**
 * Capture mic -> DSP -> Opus encode -> send; receive payload -> Opus decode -> jitter-buffered playback.
 * Falls back to PCM passthrough only if Opus codec init fails.
 */
class AudioPipeline(private val scope: CoroutineScope) {

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var captureJob: Job? = null
    private var playbackJob: Job? = null
    private var codec: AndroidOpusCodec? = null
    private var useOpus = true
    private val playbackQueue = ArrayBlockingQueue<ShortArray>(6)
    private val framePool = ArrayBlockingQueue<ShortArray>(12)
    private var warnedPcmFallbackDrop = false

    // Optional pre-encode DSP toggles.
    private val noiseGateEnabled = true
    private val highPassEnabled = true
    private var dcEstimator = 0f

    fun start(sendPayload: (ByteArray, Int) -> Unit) {
        useOpus = true
        warnedPcmFallbackDrop = false
        playbackQueue.clear()
        framePool.clear()
        repeat(12) { framePool.offer(ShortArray(Protocol.FRAME_SAMPLES)) }
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
            shutdownAudio()
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
            shutdownAudio()
            return
        }

        audioRecord?.startRecording()
        audioTrack?.play()

        codec = try {
            AndroidOpusCodec()
        } catch (e: Throwable) {
            useOpus = false
            Log.w(TAG, "Opus codec unavailable, using PCM passthrough fallback", e)
            null
        }

        playbackJob = scope.launch(Dispatchers.IO) {
            while (scope.isActive) {
                val frame = playbackQueue.poll(100, TimeUnit.MILLISECONDS) ?: continue
                val track = audioTrack ?: break
                track.write(frame, 0, frame.size)
                recycleFrame(frame)
            }
        }

        captureJob = scope.launch(Dispatchers.IO) {
            val frame = ShortArray(Protocol.FRAME_SAMPLES)
            val opusOut = ByteArray(Protocol.MAX_PAYLOAD_LEN)
            while (scope.isActive) {
                val rec = audioRecord ?: break
                val read = rec.read(frame, 0, frame.size)
                if (read == Protocol.FRAME_SAMPLES) {
                    if (highPassEnabled || noiseGateEnabled) {
                        applyPreEncodeDsp(frame)
                    }
                    if (useOpus) {
                        val enc = codec?.encode(frame, Protocol.FRAME_SAMPLES, opusOut) ?: -1
                        if (enc > 0) {
                            sendPayload(opusOut, enc)
                        }
                    } else {
                        if (!warnedPcmFallbackDrop) {
                            warnedPcmFallbackDrop = true
                            Log.w(TAG, "PCM fallback disabled for SPP transport: frame exceeds MAX_PAYLOAD_LEN")
                        }
                    }
                }
            }
        }
    }

    fun playPayload(payload: ByteArray) {
        val frame = obtainFrame()
        val ok = if (useOpus) decodeOpusPayload(payload, frame) else decodePcmPayload(payload, frame)
        if (!ok) {
            recycleFrame(frame)
            return
        }
        if (!playbackQueue.offer(frame)) {
            playbackQueue.poll()?.let { recycleFrame(it) }
            if (!playbackQueue.offer(frame)) {
                recycleFrame(frame)
            }
        }
    }

    private fun decodeOpusPayload(payload: ByteArray, out: ShortArray): Boolean {
        val n = codec?.decode(payload, out, Protocol.FRAME_SAMPLES) ?: -1
        return n == Protocol.FRAME_SAMPLES
    }

    private fun decodePcmPayload(payload: ByteArray, out: ShortArray): Boolean {
        if (payload.size < Protocol.FRAME_SAMPLES * 2) return false
        for (i in 0 until Protocol.FRAME_SAMPLES) {
            out[i] = (payload[i * 2].toInt() and 0xff or (payload[i * 2 + 1].toInt() shl 8)).toShort()
        }
        return true
    }

    private fun obtainFrame(): ShortArray = framePool.poll() ?: ShortArray(Protocol.FRAME_SAMPLES)

    private fun recycleFrame(frame: ShortArray) {
        framePool.offer(frame)
    }

    private fun applyPreEncodeDsp(frame: ShortArray) {
        var sumAbs = 0f
        for (i in frame.indices) {
            var v = frame[i].toFloat()
            if (highPassEnabled) {
                // Lightweight DC/high-pass suppression.
                dcEstimator = 0.995f * dcEstimator + 0.005f * v
                v -= dcEstimator
            }
            sumAbs += kotlin.math.abs(v)
            frame[i] = v.toInt().coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt()).toShort()
        }
        if (noiseGateEnabled) {
            val avg = sumAbs / frame.size
            if (avg < 150f) {
                for (i in frame.indices) frame[i] = 0
            }
        }
    }

    fun stop() {
        captureJob?.cancel()
        playbackJob?.cancel()
        shutdownAudio()
        playbackQueue.clear()
        framePool.clear()
    }

    private fun shutdownAudio() {
        try {
            audioRecord?.stop()
        } catch (_: IllegalStateException) {
            // AudioRecord may not have started yet.
        }
        audioRecord?.release()
        audioRecord = null
        try {
            audioTrack?.stop()
        } catch (_: IllegalStateException) {
            // AudioTrack may not have started yet.
        }
        audioTrack?.release()
        audioTrack = null
    }

    companion object {
        private const val TAG = "AudioPipeline"
    }
}
