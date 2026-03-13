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
    private val onConnected: (String) -> Unit,
    private val onDisconnected: () -> Unit,
    private val onPayloadReceived: (ByteArray) -> Unit
) {
    private val adapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private var serverSocket: BluetoothServerSocket? = null
    private var clientSocket: BluetoothSocket? = null
    private var outputStream: OutputStream? = null
    private var readJob: Job? = null
    private val running = AtomicBoolean(false)

    private val sppUuid = UUID.fromString(Protocol.SPP_SERVICE_UUID)

    @SuppressLint("MissingPermission")
    fun start() {
        if (adapter == null || !adapter.isEnabled) return
        if (!running.compareAndSet(false, true)) return

        scope.launch(Dispatchers.IO) { startServer() }
        scope.launch(Dispatchers.IO) { startDiscoveryLoop() }
    }

    @SuppressLint("MissingPermission")
    private suspend fun startServer() {
        try {
            serverSocket = adapter?.listenUsingRfcommWithServiceRecord("Intercom", sppUuid)
            while (running.get() && scope.isActive) {
                val socket = serverSocket?.accept()
                if (socket != null) {
                    withContext(Dispatchers.Main) { onConnected(socket.remoteDevice?.name ?: "Peer") }
                    setSocket(socket)
                    serverSocket?.close()
                    serverSocket = null
                    return
                }
                delay(100)
            }
        } catch (e: IOException) {
            Log.e(TAG, "Server accept", e)
        }
    }

    @SuppressLint("MissingPermission")
    private suspend fun startDiscoveryLoop() {
        while (running.get() && clientSocket == null && scope.isActive) {
            adapter?.bondedDevices?.firstOrNull { it.name?.startsWith(Protocol.DEVICE_NAME_PREFIX) == true }
                ?.let { connectTo(it) }
            if (clientSocket == null)
                adapter?.startDiscovery()
            delay(5000)
        }
    }

    @SuppressLint("MissingPermission")
    private suspend fun connectTo(device: BluetoothDevice) {
        try {
            val socket = device.createRfcommSocketToServiceRecord(sppUuid)
            socket.connect()
            withContext(Dispatchers.Main) { onConnected(device.name ?: device.address) }
            setSocket(socket)
        } catch (e: IOException) {
            Log.w(TAG, "Connect to ${device.name} failed", e)
        }
    }

    private fun setSocket(socket: BluetoothSocket) {
        clientSocket?.close()
        clientSocket = socket
        outputStream = socket.outputStream
        readJob?.cancel()
        readJob = scope.launch(Dispatchers.IO) { readLoop(socket.inputStream) }
    }

    private suspend fun readLoop(input: InputStream) {
        val header = ByteArray(Protocol.PACKET_HEADER_SIZE)
        val buf = ByteArray(Protocol.MAX_PAYLOAD_LEN)
        try {
            while (running.get() && scope.isActive) {
                if (input.read(header) != header.size) break
                val len = (header[0].toInt() and 0xff) or (header[1].toInt() shl 8)
                if (len <= 0 || len > Protocol.MAX_PAYLOAD_LEN) continue
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
            withContext(Dispatchers.Main) { onDisconnected() }
            clientSocket = null
            outputStream = null
        }
    }

    fun send(payload: ByteArray) {
        if (payload.size > Protocol.MAX_PAYLOAD_LEN) return
        scope.launch(Dispatchers.IO) {
            try {
                val out = outputStream ?: return@launch
                out.write(payload.size and 0xff)
                out.write(payload.size shr 8)
                out.write(payload)
                out.flush()
            } catch (e: IOException) {
                Log.w(TAG, "Send", e)
            }
        }
    }

    fun stop() {
        running.set(false)
        readJob?.cancel()
        serverSocket?.close()
        clientSocket?.close()
        serverSocket = null
        clientSocket = null
        outputStream = null
    }

    fun isConnected(): Boolean = clientSocket != null

    companion object {
        private const val TAG = "BluetoothSpp"
    }
}
