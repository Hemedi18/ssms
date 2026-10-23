package com.simsms.gateway.ui.screens

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.navigation.NavController
import com.simsms.gateway.ui.components.GatewayTopAppBar
import com.simsms.gateway.ui.components.StatusBadge
import com.simsms.gateway.ui.theme.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel

@Composable
fun SimInfoScreen(
    navController: NavController,
    viewModel: GatewayViewModel
) {
    val context = LocalContext.current
    val isServiceRunning by viewModel.isServiceRunning.collectAsState()
    val isConnected by viewModel.isConnected.collectAsState()

    val isSimReady = viewModel.isSimReady
    val carrierName = viewModel.simCarrierName ?: "Unknown / Absent"
    val phoneNumber = viewModel.simPhoneNumber

    // Read battery level
    val batteryPct = remember {
        val batteryStatus: Intent? = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        if (level >= 0 && scale > 0) (level * 100 / scale) else null
    }

    // Read network connectivity
    val connectivityInfo = remember {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
        val activeNetwork = cm?.activeNetwork
        val caps = cm?.getNetworkCapabilities(activeNetwork)
        when {
            caps == null -> "Disconnected"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Wi-Fi (Active)"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Cellular Mobile Data"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "Ethernet"
            else -> "Connected"
        }
    }

    // Check runtime permissions
    val hasSendSms = ContextCompat.checkSelfPermission(context, Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED
    val hasReceiveSms = ContextCompat.checkSelfPermission(context, Manifest.permission.RECEIVE_SMS) == PackageManager.PERMISSION_GRANTED
    val hasReadPhoneState = ContextCompat.checkSelfPermission(context, Manifest.permission.READ_PHONE_STATE) == PackageManager.PERMISSION_GRANTED

    Scaffold(
        topBar = {
            GatewayTopAppBar(
                title = "SIM & Phone Information",
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                            contentDescription = "Back",
                            tint = Color.White
                        )
                    }
                }
            )
        }
    ) { padding ->
        val scrollState = rememberScrollState()

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(scrollState)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // SIM Card Readiness
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text("SIM CARD HARDWARE", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = TextSecondary)
                        StatusBadge(status = if (isSimReady) "ready" else "absent")
                    }

                    HorizontalDivider(color = BorderSubtle)

                    InfoRow("SIM Readiness", if (isSimReady) "Ready to Send & Receive SMS" else "SIM card not ready, absent, or locked")
                    InfoRow("Carrier Name", carrierName)
                    InfoRow(
                        "Phone Number",
                        if (!phoneNumber.isNullOrBlank()) phoneNumber else "Not accessible from SIM (requires carrier provisioning or READ_PHONE_NUMBERS permission)"
                    )
                    InfoRow("Subscription Slot", if (isSimReady) "Slot 0 / Default SIM" else "None")
                }
            }

            // Phone & Operating Environment
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("DEVICE ENVIRONMENT", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

                    InfoRow("Internet Connection", connectivityInfo)
                    InfoRow("Server Connectivity", if (isConnected) "Connected & Polling" else "Disconnected")
                    InfoRow("Battery Level", if (batteryPct != null) "$batteryPct%" else "Unknown")
                    InfoRow("Foreground Service", if (isServiceRunning) "Running (Persistent Notification)" else "Stopped")
                }
            }

            // Permissions Status
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("PERMISSIONS STATUS", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

                    PermissionRow("SEND_SMS", hasSendSms, "Required to send real SMS via SmsManager")
                    PermissionRow("RECEIVE_SMS", hasReceiveSms, "Required to listen for incoming SMS broadcasts")
                    PermissionRow("READ_PHONE_STATE", hasReadPhoneState, "Used to query SIM state and carrier name")
                }
            }

            // Android Hardware Note
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(BackgroundLight)
                    .padding(12.dp)
            ) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(Icons.Default.Info, contentDescription = null, tint = PrimaryBlue, modifier = Modifier.size(20.dp))
                    Text(
                        "Note: On Android emulators without cellular radio, SMS sending will fail or simulate in Android Studio. A physical Android device with a functioning SIM card and mobile credit is required for real SMS delivery to cellular towers.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )
                }
            }
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = TextSecondary)
        Spacer(modifier = Modifier.height(2.dp))
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun PermissionRow(permissionName: String, granted: Boolean, description: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(permissionName, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
            Text(description, style = MaterialTheme.typography.bodySmall, color = TextSecondary)
        }
        Text(
            text = if (granted) "GRANTED" else "DENIED",
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.Bold,
            color = if (granted) StatusGreen else StatusRed
        )
    }
}
