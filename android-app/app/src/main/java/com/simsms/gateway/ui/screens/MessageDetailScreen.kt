package com.simsms.gateway.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.simsms.gateway.data.local.entities.LocalMessage
import com.simsms.gateway.ui.components.GatewayTopAppBar
import com.simsms.gateway.ui.components.StatusBadge
import com.simsms.gateway.ui.navigation.Screen
import com.simsms.gateway.ui.theme.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel
import java.text.SimpleDateFormat
import java.util.*

@Composable
fun MessageDetailScreen(
    navController: NavController,
    viewModel: GatewayViewModel,
    messageId: String
) {
    val outgoingMessages by viewModel.messages.collectAsState()
    val incomingMessages by viewModel.incomingMessages.collectAsState()
    val isSending by viewModel.isSendingSms.collectAsState()

    // Find outgoing message or incoming message
    val outgoing = outgoingMessages.find { it.id == messageId }
    val incoming = incomingMessages.find { it.id.toString() == messageId }

    var showRetryDialog by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            GatewayTopAppBar(
                title = "Message Details",
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

        if (outgoing == null && incoming == null) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = "Message not found ($messageId)",
                    style = MaterialTheme.typography.bodyLarge,
                    color = TextSecondary
                )
            }
        } else {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .verticalScroll(scrollState)
                    .padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                if (outgoing != null) {
                    OutgoingMessageContent(
                        message = outgoing,
                        onRetryClick = { showRetryDialog = true },
                        onViewLogsClick = { navController.navigate(Screen.AppLogs.route) },
                        isRetrying = isSending
                    )
                } else if (incoming != null) {
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
                                Text(
                                    text = "DIRECTION: INCOMING",
                                    style = MaterialTheme.typography.labelSmall,
                                    fontWeight = FontWeight.Bold,
                                    color = PrimaryBlue
                                )
                                StatusBadge(status = if (incoming.isSynced) "synced" else "pending")
                            }

                            HorizontalDivider(color = BorderSubtle)

                            Text("Sender", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                            Text(incoming.fromNumber, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

                            Text("Message Content", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(BackgroundLight)
                                    .padding(12.dp)
                            ) {
                                Text(incoming.body, style = MaterialTheme.typography.bodyLarge)
                            }

                            DetailRow("Received At", formatDetailDate(incoming.receivedAt))
                            DetailRow("Synced to Server", if (incoming.isSynced) "Yes (Synced)" else "Pending Network Sync")
                            DetailRow("Message Hash", (incoming.rawPduHash ?: "N/A").take(16) + "...", isMono = true)
                            DetailRow("Local ID", incoming.id.toString(), isMono = true)

                            HorizontalDivider(color = BorderSubtle)

                            // AI Auto-Response Control per Chat
                            var isAiOn by remember(incoming.fromNumber) {
                                mutableStateOf(viewModel.prefs.isAiEnabledForContact(incoming.fromNumber))
                            }
                            var isBlocked by remember(incoming.fromNumber) {
                                mutableStateOf(viewModel.prefs.isContactBlocked(incoming.fromNumber))
                            }

                            Text("AI AUTO-RESPONSE CONTROLS", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold, color = TextSecondary)

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "Smart Switch for this Contact",
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    Text(
                                        text = if (isBlocked) "Contact is blocked. AI replies disabled."
                                               else if (isAiOn) "AI responds automatically to this contact."
                                               else "AI is paused for this contact.",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = TextSecondary
                                    )
                                }
                                Switch(
                                    checked = isAiOn && !isBlocked,
                                    onCheckedChange = { enabled ->
                                        isAiOn = enabled
                                        viewModel.prefs.setAiEnabledForContact(incoming.fromNumber, enabled)
                                    },
                                    enabled = !isBlocked,
                                    colors = SwitchDefaults.colors(checkedThumbColor = PrimaryBlue)
                                )
                            }

                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(
                                        text = "Block User",
                                        style = MaterialTheme.typography.bodyMedium,
                                        fontWeight = FontWeight.SemiBold
                                    )
                                    Text(
                                        text = "Blocked users never receive AI auto-replies.",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = TextSecondary
                                    )
                                }
                                Button(
                                    onClick = {
                                        val newState = !isBlocked
                                        isBlocked = newState
                                        if (newState) isAiOn = false
                                        viewModel.prefs.setContactBlocked(incoming.fromNumber, newState)
                                    },
                                    colors = ButtonDefaults.buttonColors(
                                        containerColor = if (isBlocked) AccentBlue else StatusRed
                                    ),
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Text(if (isBlocked) "Unblock" else "Block User")
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (showRetryDialog && outgoing != null) {
        AlertDialog(
            onDismissRequest = { showRetryDialog = false },
            title = { Text("Retry Sending SMS?") },
            text = {
                Text("This will re-submit this SMS job to your phone's SIM card to recipient ${outgoing.to}. Ensure this is not a duplicate message before proceeding.")
            },
            confirmButton = {
                Button(
                    onClick = {
                        showRetryDialog = false
                        viewModel.retryMessage(outgoing.id)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue)
                ) {
                    Text("Confirm Resend")
                }
            },
            dismissButton = {
                TextButton(onClick = { showRetryDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }
}

@Composable
private fun OutgoingMessageContent(
    message: LocalMessage,
    onRetryClick: () -> Unit,
    onViewLogsClick: () -> Unit,
    isRetrying: Boolean
) {
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
                Text(
                    text = "DIRECTION: OUTGOING",
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    color = PrimaryBlue
                )
                StatusBadge(status = message.status)
            }

            HorizontalDivider(color = BorderSubtle)

            Text("Recipient", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
            Text(message.to, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)

            Text("Message Content", style = MaterialTheme.typography.labelMedium, color = TextSecondary)
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(BackgroundLight)
                    .padding(12.dp)
            ) {
                Text(message.body, style = MaterialTheme.typography.bodyLarge)
            }

            DetailRow("Message ID", message.id, isMono = true)
            if (message.clientReference != null) {
                DetailRow("Client Reference", message.clientReference)
            }
            DetailRow("Created At", formatDetailDate(message.createdAt))
            if (message.sentAt != null) {
                DetailRow("Sent At", formatDetailDate(message.sentAt))
            }
            if (message.deliveredAt != null) {
                DetailRow("Delivered At", formatDetailDate(message.deliveredAt))
            }
            DetailRow("Multipart Parts", "${message.partsCount} part(s)")

            if (!message.errorMessage.isNullOrBlank()) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(StatusRed.copy(alpha = 0.1f))
                        .padding(12.dp)
                ) {
                    Column {
                        Text(
                            text = "Error Information",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = StatusRed
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = message.errorMessage,
                            style = MaterialTheme.typography.bodyMedium,
                            color = StatusRed
                        )
                    }
                }
            }

            // Actions
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (message.status == "failed") {
                    Button(
                        onClick = onRetryClick,
                        modifier = Modifier.weight(1f),
                        enabled = !isRetrying,
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue)
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Retry SMS")
                    }
                }
                OutlinedButton(
                    onClick = onViewLogsClick,
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(Icons.Default.List, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("View Logs")
                }
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String, isMono: Boolean = false) {
    Column {
        Text(text = label, style = MaterialTheme.typography.labelSmall, color = TextSecondary)
        Spacer(modifier = Modifier.height(2.dp))
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontFamily = if (isMono) FontFamily.Monospace else FontFamily.Default,
            fontSize = if (isMono) 12.sp else 14.sp,
            color = TextPrimary
        )
    }
}

private fun formatDetailDate(timestamp: Long): String {
    val sdf = SimpleDateFormat("yyyy-MM-dd HH:mm:ss (z)", Locale.getDefault())
    return sdf.format(Date(timestamp))
}
