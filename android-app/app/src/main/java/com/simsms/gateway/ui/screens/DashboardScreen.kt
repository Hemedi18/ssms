package com.simsms.gateway.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.simsms.gateway.data.local.entities.LocalMessage
import com.simsms.gateway.ui.components.*
import com.simsms.gateway.ui.theme.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    viewModel: GatewayViewModel,
    onNavigateToSendSms: () -> Unit,
    onNavigateToMessageDetail: (String) -> Unit,
    onNavigateToLogs: () -> Unit,
    onNavigateToSettings: () -> Unit,
    onBottomNavigate: (String) -> Unit
) {
    val isConnected by viewModel.isConnected.collectAsState()
    val isServiceRunning by viewModel.isServiceRunning.collectAsState()
    val isPaired by viewModel.isPaired.collectAsState()
    val messages by viewModel.messages.collectAsState()
    val incomingMessages by viewModel.incomingMessages.collectAsState()

    val sentCount by viewModel.repository.sentCountFlow.collectAsState(initial = 0)
    val deliveredCount by viewModel.repository.deliveredCountFlow.collectAsState(initial = 0)
    val pendingCount by viewModel.repository.pendingCountFlow.collectAsState(initial = 0)
    val failedCount by viewModel.repository.failedCountFlow.collectAsState(initial = 0)
    val receivedCount by viewModel.repository.receivedCountFlow.collectAsState(initial = 0)

    val dateFormat = remember { SimpleDateFormat("HH:mm:ss dd MMM", Locale.getDefault()) }

    Scaffold(
        topBar = {
            GatewayTopBar(
                title = "SMS Gateway Dashboard",
                actions = {
                    IconButton(onClick = onNavigateToLogs) {
                        Icon(Icons.Default.ListAlt, contentDescription = "Logs", tint = Color.White)
                    }
                }
            )
        },
        bottomBar = {
            GatewayBottomBar(
                currentRoute = com.simsms.gateway.ui.navigation.Screen.Home.route,
                onNavigate = onBottomNavigate
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = onNavigateToSendSms,
                containerColor = AccentBlue,
                contentColor = Color.White,
                shape = RoundedCornerShape(16.dp),
                icon = { Icon(Icons.Default.Send, contentDescription = null) },
                text = { Text("Send SMS", fontWeight = FontWeight.Bold) }
            )
        },
        containerColor = BackgroundLight
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            item {
                Spacer(modifier = Modifier.height(6.dp))

                // Status Banner Card
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .size(12.dp)
                                        .clip(CircleShape)
                                        .background(if (isConnected) StatusGreen else StatusRed)
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    text = if (isConnected) "Server Connected" else "Server Disconnected",
                                    fontWeight = FontWeight.Bold,
                                    fontSize = 15.sp,
                                    color = TextPrimary
                                )
                            }
                            StatusBadge(status = if (isServiceRunning) "Running" else "Stopped")
                        }

                        Spacer(modifier = Modifier.height(12.dp))
                        Divider(color = SurfaceCardBorder)
                        Spacer(modifier = Modifier.height(12.dp))

                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Column {
                                Text(text = "SIM State", fontSize = 11.sp, color = TextSecondary)
                                Text(
                                    text = if (viewModel.isSimReady) "SIM Ready (${viewModel.simCarrierName ?: "Carrier"})" else "No SIM detected",
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = if (viewModel.isSimReady) StatusGreen else StatusRed
                                )
                            }
                            Column(horizontalAlignment = Alignment.End) {
                                Text(text = "Gateway Mode", fontSize = 11.sp, color = TextSecondary)
                                Text(
                                    text = if (isServiceRunning) "Foreground Active" else "Idle (Paused)",
                                    fontSize = 13.sp,
                                    fontWeight = FontWeight.SemiBold,
                                    color = if (isServiceRunning) AccentBlue else TextSecondary
                                )
                            }
                        }

                        Spacer(modifier = Modifier.height(14.dp))

                        // Toggle Foreground Service Button
                        Button(
                            onClick = { viewModel.toggleGatewayService(!isServiceRunning) },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (isServiceRunning) StatusRed else AccentBlue
                            )
                        ) {
                            Icon(
                                imageVector = if (isServiceRunning) Icons.Default.Pause else Icons.Default.PlayArrow,
                                contentDescription = null
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = if (isServiceRunning) "Stop Gateway Service" else "Start Gateway Service",
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }
            }

            item {
                Text(
                    text = "Operational Metrics",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = TextPrimary
                )
            }

            item {
                // Metric Cards Grid
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    MetricCard(
                        title = "SMS Sent",
                        count = sentCount,
                        icon = Icons.Default.CheckCircle,
                        iconColor = StatusGreen,
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        title = "Delivered",
                        count = deliveredCount,
                        icon = Icons.Default.DoneAll,
                        iconColor = AccentBlue,
                        modifier = Modifier.weight(1f)
                    )
                }
            }

            item {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    MetricCard(
                        title = "Pending Queue",
                        count = pendingCount,
                        icon = Icons.Default.HourglassTop,
                        iconColor = StatusOrange,
                        modifier = Modifier.weight(1f)
                    )
                    MetricCard(
                        title = "Failed",
                        count = failedCount,
                        icon = Icons.Default.ErrorOutline,
                        iconColor = StatusRed,
                        modifier = Modifier.weight(1f)
                    )
                }
            }

            item {
                MetricCard(
                    title = "SMS Received on SIM",
                    count = receivedCount,
                    icon = Icons.Default.Inbox,
                    iconColor = Color(0xFF8B5CF6)
                )
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Recent Activity",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary
                    )
                    Text(
                        text = "View All",
                        color = AccentBlue,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.clickable { onBottomNavigate(com.simsms.gateway.ui.navigation.Screen.SentMessages.route) }
                    )
                }
            }

            if (messages.isEmpty()) {
                item {
                    EmptyStateView(
                        icon = Icons.Default.Message,
                        title = "No SMS activity yet",
                        message = "Queued messages from the REST API or manual sends will appear here."
                    )
                }
            } else {
                items(messages.take(6)) { msg ->
                    ActivityMessageCard(
                        message = msg,
                        dateFormat = dateFormat,
                        onClick = { onNavigateToMessageDetail(msg.id) }
                    )
                }
            }

            item {
                Spacer(modifier = Modifier.height(72.dp)) // padding for FAB
            }
        }
    }
}

@Composable
fun ActivityMessageCard(
    message: LocalMessage,
    dateFormat: SimpleDateFormat,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = SurfaceCard),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = message.to,
                    fontWeight = FontWeight.Bold,
                    fontSize = 14.sp,
                    color = TextPrimary
                )
                StatusBadge(status = message.status)
            }
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = message.body,
                maxLines = 2,
                fontSize = 13.sp,
                color = TextSecondary
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = "${message.partsCount} part(s)",
                    fontSize = 11.sp,
                    color = TextMuted
                )
                Text(
                    text = dateFormat.format(Date(message.createdAt)),
                    fontSize = 11.sp,
                    color = TextMuted
                )
            }
        }
    }
}
