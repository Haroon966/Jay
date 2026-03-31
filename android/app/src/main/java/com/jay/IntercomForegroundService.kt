package com.jay

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel

class IntercomForegroundService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var sppManager: BluetoothSppManager? = null
    private var audioPipeline: AudioPipeline? = null
    private var started = false

    override fun onCreate() {
        super.onCreate()
        running = true
        val channelId = "intercom_channel"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW
            )
            (getSystemService(NOTIFICATION_SERVICE) as NotificationManager).createNotificationChannel(channel)
        }
        val pending = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle(getString(R.string.notification_title))
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(pending)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, notification, android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
        } else {
            startForeground(1, notification)
        }

        startIntercomRuntime()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (!started) {
            startIntercomRuntime()
        }
        return START_STICKY
    }

    override fun onDestroy() {
        started = false
        sppManager?.stop()
        audioPipeline?.stop()
        serviceScope.cancel()
        stopForeground(STOP_FOREGROUND_REMOVE)
        running = false
        broadcastStatus(BluetoothSppManager.Status.DISCONNECTED, null)
        super.onDestroy()
    }

    private fun broadcastStatus(status: BluetoothSppManager.Status, detail: String?) {
        val intent = Intent(ACTION_INTERCOM_STATUS).apply {
            setPackage(packageName)
            putExtra(EXTRA_STATUS, status.name)
            if (!detail.isNullOrBlank()) putExtra(EXTRA_DETAIL, detail)
        }
        sendBroadcast(intent)
    }

    private fun startIntercomRuntime() {
        if (started) return
        started = true
        audioPipeline = AudioPipeline(serviceScope)
        sppManager = BluetoothSppManager(
            scope = serviceScope,
            onStatusChanged = { status, detail -> broadcastStatus(status, detail) },
            onConnected = { name ->
                broadcastStatus(BluetoothSppManager.Status.CONNECTED, name)
            },
            onDisconnected = { broadcastStatus(BluetoothSppManager.Status.DISCONNECTED, null) },
            onPayloadReceived = { payload -> audioPipeline?.playPayload(payload) }
        )
        broadcastStatus(BluetoothSppManager.Status.WAITING, null)
        sppManager?.start()
        audioPipeline?.start { payload, len -> sppManager?.send(payload, len) }
    }

    companion object {
        const val ACTION_INTERCOM_STATUS = "com.jay.ACTION_INTERCOM_STATUS"
        const val EXTRA_STATUS = "status"
        const val EXTRA_DETAIL = "detail"
        @Volatile var running: Boolean = false
    }
}
