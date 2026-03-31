package com.jay

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.activity.result.contract.ActivityResultContracts

class MainActivity : AppCompatActivity() {

    private var serviceRunning = false
    private var receiverRegistered = false
    private var manualStopRequested = false
    private lateinit var statusText: TextView
    private lateinit var toggleButton: Button
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { _ ->
        serviceRunning = isIntercomServiceRunning()
        maybeAutoStartService()
        updateUi()
        if (!hasRequiredPermissions()) {
            statusText.text = getString(R.string.status_error_with_reason, "Permissions required")
        }
    }
    private val statusReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != IntercomForegroundService.ACTION_INTERCOM_STATUS) return
            val status = intent.getStringExtra(IntercomForegroundService.EXTRA_STATUS)
            val detail = intent.getStringExtra(IntercomForegroundService.EXTRA_DETAIL)
            when (status) {
                BluetoothSppManager.Status.CONNECTING.name -> {
                    statusText.text = getString(R.string.status_connecting, detail ?: getString(R.string.peer_label))
                }
                BluetoothSppManager.Status.CONNECTED.name -> {
                    statusText.text = getString(R.string.status_connected, detail ?: getString(R.string.peer_label))
                }
                BluetoothSppManager.Status.RECOVERING.name -> {
                    statusText.text = getString(R.string.status_recovering)
                }
                BluetoothSppManager.Status.DISCONNECTED.name -> {
                    statusText.text = getString(R.string.status_disconnected)
                }
                BluetoothSppManager.Status.ERROR.name -> {
                    statusText.text = detail?.let { getString(R.string.status_error_with_reason, it) }
                        ?: getString(R.string.status_error)
                }
                else -> {
                    statusText.text = getString(R.string.status_waiting)
                }
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        statusText = findViewById(R.id.statusText)
        toggleButton = findViewById(R.id.toggleButton)

        requestPermissionsIfNeeded()
        serviceRunning = isIntercomServiceRunning()
        maybeAutoStartService()
        updateUi()

        toggleButton.setOnClickListener {
            if (serviceRunning) {
                stopService(Intent(this, IntercomForegroundService::class.java))
                serviceRunning = false
                manualStopRequested = true
                statusText.text = getString(R.string.status_stopped)
            } else {
                if (!hasRequiredPermissions()) {
                    requestPermissionsIfNeeded()
                    statusText.text = getString(R.string.status_error_with_reason, "Grant permissions to start")
                    updateUi()
                    return@setOnClickListener
                }
                startForegroundService(Intent(this, IntercomForegroundService::class.java))
                serviceRunning = true
                manualStopRequested = false
                statusText.text = getString(R.string.status_waiting)
            }
            updateUi()
        }
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter(IntercomForegroundService.ACTION_INTERCOM_STATUS)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(statusReceiver, filter, RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(statusReceiver, filter)
        }
        receiverRegistered = true
    }

    override fun onStop() {
        if (receiverRegistered) {
            unregisterReceiver(statusReceiver)
            receiverRegistered = false
        }
        super.onStop()
    }

    override fun onResume() {
        super.onResume()
        serviceRunning = isIntercomServiceRunning()
        maybeAutoStartService()
        updateUi()
    }

    private fun requestPermissionsIfNeeded() {
        val missing = requiredPermissions().filterNot(::hasPermission)
        if (missing.isNotEmpty()) {
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun maybeAutoStartService() {
        if (serviceRunning || manualStopRequested || !hasRequiredPermissions()) return
        startForegroundService(Intent(this, IntercomForegroundService::class.java))
        serviceRunning = true
        statusText.text = getString(R.string.status_waiting)
    }

    private fun updateUi() {
        if (!serviceRunning) {
            statusText.text = getString(R.string.status_stopped)
        }
        toggleButton.isEnabled = serviceRunning || hasRequiredPermissions()
        toggleButton.text = if (serviceRunning) getString(R.string.stop_intercom) else getString(R.string.start_intercom)
    }

    private fun hasRequiredPermissions(): Boolean = requiredPermissions().all(::hasPermission)

    private fun hasPermission(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun requiredPermissions(): List<String> {
        val perms = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            perms += listOf(
                Manifest.permission.BLUETOOTH_SCAN,
                Manifest.permission.BLUETOOTH_CONNECT,
                Manifest.permission.BLUETOOTH_ADVERTISE,
            )
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            perms += Manifest.permission.POST_NOTIFICATIONS
        }
        return perms
    }

    @Suppress("DEPRECATION")
    private fun isIntercomServiceRunning(): Boolean {
        val manager = getSystemService(ACTIVITY_SERVICE) as? android.app.ActivityManager ?: return false
        return manager.getRunningServices(Int.MAX_VALUE)
            .any { it.service.className == IntercomForegroundService::class.java.name }
    }
}
