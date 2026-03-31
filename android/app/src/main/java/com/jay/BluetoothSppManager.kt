package com.jay

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothServerSocket
import android.bluetooth.BluetoothSocket
import android.util.Log
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.util.UUID
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * SPP server (accept) + client (connect), packet format: 2-byte length (LE) + payload.
 */
class BluetoothSppManager(
    private val scope: CoroutineScope,
    private val onStatusChanged: (Status, String?) -> Unit,
    private val onConnected: (String) -> Unit,
    private val onDisconnected: () -> Unit,
    private val onPayloadReceived: (ByteArray) -> Unit
) {
    private val adapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private var serverSocket: BluetoothServerSocket? = null
    private var clientSocket: BluetoothSocket? = null
    private var outputStream: OutputStream? = null
    private var readJob: Job? = null
    private var writerJob: Job? = null
    private val running = AtomicBoolean(false)
    private val connecting = AtomicBoolean(false)
    private val socketLock = Any()
    private val sendQueue = ArrayBlockingQueue<ByteArray>(48)
    private var droppedSendPackets = 0L

    private val sppUuid = UUID.fromString(Protocol.SPP_SERVICE_UUID)

    @SuppressLint("MissingPermission")
    fun start() {
        if (adapter == null || !adapter.isEnabled) return
        if (!running.compareAndSet(false, true)) return

        onStatusChanged(Status.WAITING, null)
        scope.launch(Dispatchers.IO) { startServer() }
        scope.launch(Dispatchers.IO) { startDiscoveryLoop() }
    }

    @SuppressLint("MissingPermission")
    private suspend fun startServer() {
        try {
            serverSocket = adapter?.listenUsingRfcommWithServiceRecord("Intercom", sppUuid)
            while (running.get() && scope.isActive) {
                val socket = serverSocket?.accept() ?: continue
                val accepted = setSocketIfFree(socket)
                if (accepted) {
                    withContext(Dispatchers.Main) {
                        onConnected(socket.remoteDevice?.name ?: "Peer")
                        onStatusChanged(Status.CONNECTED, socket.remoteDevice?.name)
                    }
                } else {
                    socket.close()
                }
            }
        } catch (e: IOException) {
            Log.e(TAG, "Server accept", e)
            withContext(Dispatchers.Main) { onStatusChanged(Status.ERROR, e.message) }
        }
    }

    @SuppressLint("MissingPermission")
    private suspend fun startDiscoveryLoop() {
        var backoffMs = Protocol.DISCOVERY_BACKOFF_MIN_MS.toLong()
        while (running.get() && scope.isActive) {
            if (!isConnected() && !connecting.get()) {
                val bondedPeers = adapter?.bondedDevices
                    ?.filter { it.name?.startsWith(Protocol.DEVICE_NAME_PREFIX) == true }
                    ?.sortedBy { it.name ?: it.address }
                    .orEmpty()
                for (peer in bondedPeers) {
                    connectTo(peer)
                    if (isConnected()) break
                }
                if (!isConnected() && !connecting.get()) {
                    if (adapter?.isDiscovering != true) {
                        adapter?.startDiscovery()
                    }
                    withContext(Dispatchers.Main) { onStatusChanged(Status.RECOVERING, null) }
                    delay(backoffMs)
                    backoffMs = (backoffMs * 2).coerceAtMost(Protocol.DISCOVERY_BACKOFF_MAX_MS.toLong())
                    continue
                }
                backoffMs = Protocol.DISCOVERY_BACKOFF_MIN_MS.toLong()
            }
            delay(1000)
        }
    }

    @SuppressLint("MissingPermission")
    private suspend fun connectTo(device: BluetoothDevice) {
        if (isConnected() || !connecting.compareAndSet(false, true)) return
        try {
            withContext(Dispatchers.Main) { onStatusChanged(Status.CONNECTING, device.name ?: device.address) }
            adapter?.cancelDiscovery()
            val socket = device.createRfcommSocketToServiceRecord(sppUuid)
            socket.connect()
            val accepted = setSocketIfFree(socket)
            if (accepted) {
                withContext(Dispatchers.Main) {
                    onConnected(device.name ?: device.address)
                    onStatusChanged(Status.CONNECTED, device.name ?: device.address)
                }
            } else {
                socket.close()
            }
        } catch (e: IOException) {
            Log.w(TAG, "Connect to ${device.name} failed", e)
            withContext(Dispatchers.Main) { onStatusChanged(Status.RECOVERING, null) }
        } finally {
            connecting.set(false)
        }
    }

    private fun setSocketIfFree(socket: BluetoothSocket): Boolean {
        synchronized(socketLock) {
            if (clientSocket != null) {
                return false
            }
            clientSocket = socket
            outputStream = socket.outputStream
            readJob?.cancel()
            writerJob?.cancel()
            readJob = scope.launch(Dispatchers.IO) { readLoop(socket.inputStream) }
            writerJob = scope.launch(Dispatchers.IO) { writeLoop() }
            return true
        }
    }

    private suspend fun writeLoop() {
        val frame = ByteArray(Protocol.PACKET_HEADER_SIZE + Protocol.MAX_PAYLOAD_LEN)
        try {
            while (running.get() && scope.isActive) {
                val payload = sendQueue.poll(100, TimeUnit.MILLISECONDS) ?: continue
                val len = payload.size
                if (len <= 0 || len > Protocol.MAX_PAYLOAD_LEN) continue
                val out = synchronized(socketLock) { outputStream } ?: continue
                frame[0] = (len and 0xff).toByte()
                frame[1] = ((len shr 8) and 0xff).toByte()
                payload.copyInto(frame, destinationOffset = Protocol.PACKET_HEADER_SIZE, endIndex = len)
                out.write(frame, 0, Protocol.PACKET_HEADER_SIZE + len)
            }
        } catch (_: InterruptedException) {
            // Coroutine canceled while blocked on queue.
        } catch (e: IOException) {
            Log.w(TAG, "Write loop", e)
            closeActiveSocket()
        }
    }

    private suspend fun readLoop(input: InputStream) {
        val header = ByteArray(Protocol.PACKET_HEADER_SIZE)
        val buf = ByteArray(Protocol.MAX_PAYLOAD_LEN)
        val discardBuf = ByteArray(256)
        try {
            while (running.get() && scope.isActive) {
                if (!readFully(input, header, header.size)) break
                val len = (header[0].toInt() and 0xff) or (header[1].toInt() shl 8)
                if (len <= 0) continue
                if (len > Protocol.MAX_PAYLOAD_LEN) {
                    skipFully(input, len, discardBuf)
                    continue
                }
                var n = 0
                while (n < len) {
                    val r = input.read(buf, n, len - n)
                    if (r <= 0) return
                    n += r
                }
                onPayloadReceived(buf.copyOf(len))
            }
        } catch (e: IOException) {
            Log.w(TAG, "Read loop", e)
        } finally {
            closeActiveSocket()
            withContext(Dispatchers.Main) {
                onDisconnected()
                onStatusChanged(Status.DISCONNECTED, null)
            }
        }
    }

    private fun closeActiveSocket() {
        synchronized(socketLock) {
            try {
                clientSocket?.close()
            } catch (_: IOException) {
                // Ignore close errors.
            }
            clientSocket = null
            outputStream = null
        }
    }

    private fun readFully(input: InputStream, dst: ByteArray, len: Int): Boolean {
        var n = 0
        while (n < len) {
            val r = input.read(dst, n, len - n)
            if (r <= 0) return false
            n += r
        }
        return true
    }

    private fun skipFully(input: InputStream, bytes: Int, scratch: ByteArray) {
        var left = bytes
        while (left > 0) {
            val chunk = minOf(left, scratch.size)
            val r = input.read(scratch, 0, chunk)
            if (r <= 0) return
            left -= r
        }
    }

    fun send(payload: ByteArray, length: Int = payload.size) {
        if (length <= 0 || length > Protocol.MAX_PAYLOAD_LEN || length > payload.size) return
        val queued = payload.copyOf(length)
        if (!sendQueue.offer(queued)) {
            sendQueue.poll()
            if (!sendQueue.offer(queued)) {
                droppedSendPackets++
                if ((droppedSendPackets % 50L) == 1L) {
                    Log.w(TAG, "Dropping outbound packet due to full queue; dropped=$droppedSendPackets")
                }
            }
        }
    }

    fun stop() {
        running.set(false)
        connecting.set(false)
        readJob?.cancel()
        writerJob?.cancel()
        adapter?.cancelDiscovery()
        serverSocket?.close()
        synchronized(socketLock) {
            clientSocket?.close()
            serverSocket = null
            clientSocket = null
            outputStream = null
        }
        sendQueue.clear()
    }

    fun isConnected(): Boolean = synchronized(socketLock) { clientSocket != null }

    enum class Status {
        WAITING,
        CONNECTING,
        CONNECTED,
        RECOVERING,
        DISCONNECTED,
        ERROR
    }

    companion object {
        private const val TAG = "BluetoothSpp"
    }
}
