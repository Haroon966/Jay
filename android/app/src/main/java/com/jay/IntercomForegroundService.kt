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

    override fun onCreate() {
        super.onCreate()
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

        audioPipeline = AudioPipeline(serviceScope)
        sppManager = BluetoothSppManager(
            scope = serviceScope,
            onConnected = { name ->
                @Suppress("UNUSED_PARAMETER")
                val n = name
                // Could broadcast to Activity for UI update
            },
            onDisconnected = { },
            onPayloadReceived = { payload -> audioPipeline?.playPayload(payload) }
        )
        sppManager?.start()
        audioPipeline?.start { payload -> sppManager?.send(payload) }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        sppManager?.stop()
        audioPipeline?.stop()
        serviceScope.cancel()
        stopForeground(STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}
