package com.simsms.gateway.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.automirrored.filled.Help
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.simsms.gateway.ui.components.GatewayBottomNavigation
import com.simsms.gateway.ui.components.GatewayTopAppBar
import com.simsms.gateway.ui.navigation.Screen
import com.simsms.gateway.ui.theme.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel

@Composable
fun SettingsScreen(
    navController: NavController,
    viewModel: GatewayViewModel
) {
    val prefs = viewModel.prefs
    var autoSync by remember { mutableStateOf(prefs.autoSyncEnabled) }
    var notifications by remember { mutableStateOf(prefs.notificationsEnabled) }
    var syncInterval by remember { mutableIntStateOf(prefs.syncIntervalSeconds) }
    val isServiceRunning by viewModel.isServiceRunning.collectAsState()
    val isPaired by viewModel.isPaired.collectAsState()

    var showApiDialog by remember { mutableStateOf(false) }
    var showWebhookDialog by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            GatewayTopAppBar(title = "Settings")
        },
        bottomBar = {
            GatewayBottomNavigation(
                currentRoute = Screen.Settings.route,
                onNavigate = { screen: Screen ->
                    if (screen.route != Screen.Settings.route) {
                        navController.navigate(screen.route) {
                            popUpTo(Screen.Home.route) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
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
            // Section 1: Gateway Operation
            Text("GATEWAY OPERATION", style = MaterialTheme.typography.labelMedium, color = TextSecondary, fontWeight = FontWeight.Bold)

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    // Service Switch
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Continuous Gateway Service", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            Text(
                                "Runs a persistent foreground service with a status notification to maintain connection and poll for outgoing SMS jobs.",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                        }
                        Switch(
                            checked = isServiceRunning,
                            onCheckedChange = { viewModel.toggleGatewayService(it) },
                            enabled = isPaired,
                            colors = SwitchDefaults.colors(checkedThumbColor = PrimaryBlue, checkedTrackColor = PrimaryBlue.copy(alpha = 0.5f))
                        )
                    }

                    HorizontalDivider(color = BorderSubtle)

                    // Auto-sync switch
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Auto-Sync Messages", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            Text(
                                "Automatically upload received SMS and delivery callbacks to the backend server.",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                        }
                        Switch(
                            checked = autoSync,
                            onCheckedChange = {
                                autoSync = it
                                viewModel.updateSettings(autoSync, syncInterval, notifications)
                            },
                            colors = SwitchDefaults.colors(checkedThumbColor = PrimaryBlue, checkedTrackColor = PrimaryBlue.copy(alpha = 0.5f))
                        )
                    }

                    HorizontalDivider(color = BorderSubtle)

                    // Polling interval selector
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Polling Interval", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text(
                            "Frequency at which the gateway polls the Python backend for newly queued SMS jobs.",
                            style = MaterialTheme.typography.bodySmall,
                            color = TextSecondary
                        )
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            listOf(5, 10, 30, 60).forEach { sec ->
                                FilterChip(
                                    selected = syncInterval == sec,
                                    onClick = {
                                        syncInterval = sec
                                        viewModel.updateSettings(autoSync, syncInterval, notifications)
                                    },
                                    label = { Text("${sec}s") },
                                    colors = FilterChipDefaults.filterChipColors(
                                        selectedContainerColor = PrimaryBlue,
                                        selectedLabelColor = androidx.compose.ui.graphics.Color.White
                                    )
                                )
                            }
                        }
                    }

                    HorizontalDivider(color = BorderSubtle)

                    // Notifications switch
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Notifications", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            Text(
                                "Show notifications for incoming SMS and failed transmission alerts.",
                                style = MaterialTheme.typography.bodySmall,
                                color = TextSecondary
                            )
                        }
                        Switch(
                            checked = notifications,
                            onCheckedChange = {
                                notifications = it
                                viewModel.updateSettings(autoSync, syncInterval, notifications)
                            },
                            colors = SwitchDefaults.colors(checkedThumbColor = PrimaryBlue, checkedTrackColor = PrimaryBlue.copy(alpha = 0.5f))
                        )
                    }
                }
            }

            // Section 2: Configuration & Diagnostics
            Text("CONFIGURATION & DIAGNOSTICS", style = MaterialTheme.typography.labelMedium, color = TextSecondary, fontWeight = FontWeight.Bold)

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column {
                    SettingsNavigationItem(
                        icon = Icons.Default.Cloud,
                        title = "Server Configuration",
                        subtitle = "Server URL, connection test, device pairing",
                        onClick = { navController.navigate(Screen.ServerConfig.route) }
                    )
                    HorizontalDivider(color = BorderSubtle, modifier = Modifier.padding(horizontal = 16.dp))
                    SettingsNavigationItem(
                        icon = Icons.Default.SimCard,
                        title = "SIM & Phone Information",
                        subtitle = "Hardware readiness, carrier, network, battery",
                        onClick = { navController.navigate(Screen.SimInfo.route) }
                    )
                    HorizontalDivider(color = BorderSubtle, modifier = Modifier.padding(horizontal = 16.dp))
                    SettingsNavigationItem(
                        icon = Icons.Default.Code,
                        title = "API Information",
                        subtitle = "REST API documentation and client integration",
                        onClick = { showApiDialog = true }
                    )
                    HorizontalDivider(color = BorderSubtle, modifier = Modifier.padding(horizontal = 16.dp))
                    SettingsNavigationItem(
                        icon = Icons.Default.Send,
                        title = "Webhook Information",
                        subtitle = "HMAC-SHA256 signatures, events, and retry policies",
                        onClick = { showWebhookDialog = true }
                    )
                    HorizontalDivider(color = BorderSubtle, modifier = Modifier.padding(horizontal = 16.dp))
                    SettingsNavigationItem(
                        icon = Icons.Default.List,
                        title = "App Logs",
                        subtitle = "Diagnostic events, sync records, error audits",
                        onClick = { navController.navigate(Screen.AppLogs.route) }
                    )
                }
            }

            // Section 3: Information & Support
            Text("INFORMATION & SUPPORT", style = MaterialTheme.typography.labelMedium, color = TextSecondary, fontWeight = FontWeight.Bold)

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column {
                    SettingsNavigationItem(
                        icon = Icons.AutoMirrored.Filled.Help,
                        title = "Setup Guide & Tutorial",
                        subtitle = "Step-by-step instructions to configure the gateway",
                        onClick = { navController.navigate(Screen.SetupGuide.route) }
                    )
                    HorizontalDivider(color = BorderSubtle, modifier = Modifier.padding(horizontal = 16.dp))
                    SettingsNavigationItem(
                        icon = Icons.Default.Info,
                        title = "About SMS Gateway",
                        subtitle = "Version, legal terms, privacy and security policy",
                        onClick = { navController.navigate(Screen.About.route) }
                    )
                }
            }
        }
    }

    if (showApiDialog) {
        AlertDialog(
            onDismissRequest = { showApiDialog = false },
            title = { Text("REST API Information") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("External systems and web applications send SMS requests using standard HTTP POST requests:")
                    Text("POST /api/v1/messages", fontWeight = FontWeight.Bold, color = PrimaryBlue)
                    Text("Headers:\n• Authorization: Bearer <API_KEY>\n• Content-Type: application/json")
                    Text("Body:\n{\n  \"to\": \"+255712345678\",\n  \"message\": \"Hello from API!\"\n}")
                    Text("Generate API keys on the server using:\npython -m app.cli create-api-key --name \"MyApp\"", style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                }
            },
            confirmButton = {
                TextButton(onClick = { showApiDialog = false }) { Text("Close") }
            }
        )
    }

    if (showWebhookDialog) {
        AlertDialog(
            onDismissRequest = { showWebhookDialog = false },
            title = { Text("Webhooks Documentation") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("The backend notifies external services on key events:")
                    Text("• sms.queued\n• sms.sent\n• sms.delivered\n• sms.failed\n• sms.received\n• device.online / offline")
                    Text("Security: Each webhook payload is signed with HMAC-SHA256 in header X-Gateway-Signature using your secret.")
                    Text("Worker: Persistent PostgreSQL/SQLite queue with exponential backoff and jitter.", style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                }
            },
            confirmButton = {
                TextButton(onClick = { showWebhookDialog = false }) { Text("Close") }
            }
        )
    }
}

@Composable
private fun SettingsNavigationItem(
    icon: ImageVector,
    title: String,
    subtitle: String,
    onClick: () -> Unit
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(16.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Icon(imageVector = icon, contentDescription = null, tint = PrimaryBlue, modifier = Modifier.size(24.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(text = title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Text(text = subtitle, style = MaterialTheme.typography.bodySmall, color = TextSecondary)
        }
        Icon(imageVector = Icons.AutoMirrored.Filled.ArrowForward, contentDescription = null, tint = TextSecondary, modifier = Modifier.size(16.dp))
    }
}
