package com.simsms.gateway.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Inbox
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.simsms.gateway.data.local.entities.LocalIncomingMessage
import com.simsms.gateway.ui.components.*
import com.simsms.gateway.ui.theme.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReceivedMessagesScreen(
    viewModel: GatewayViewModel,
    onBack: () -> Unit
) {
    var searchQuery by remember { mutableStateOf("") }
    val incomingMessages by viewModel.incomingMessages.collectAsState()
    val dateFormat = remember { SimpleDateFormat("HH:mm:ss dd MMM yyyy", Locale.getDefault()) }

    val filtered = incomingMessages.filter { msg ->
        searchQuery.isBlank() ||
                msg.fromNumber.contains(searchQuery, ignoreCase = true) ||
                msg.body.contains(searchQuery, ignoreCase = true)
    }

    Scaffold(
        topBar = {
            GatewayTopBar(
                title = "Received Messages",
                showBack = true,
                onBack = onBack
            )
        },
        containerColor = BackgroundLight
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            OutlinedTextField(
                value = searchQuery,
                onValueChange = { searchQuery = it },
                placeholder = { Text("Search sender or text...") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = AccentBlue) },
                trailingIcon = {
                    if (searchQuery.isNotBlank()) {
                        IconButton(onClick = { searchQuery = "" }) {
                            Icon(Icons.Default.Close, contentDescription = "Clear")
                        }
                    }
                },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = AccentBlue,
                    focusedContainerColor = SurfaceCard,
                    unfocusedContainerColor = SurfaceCard
                )
            )

            if (filtered.isEmpty()) {
                EmptyStateView(
                    icon = Icons.Default.Inbox,
                    title = "No received SMS",
                    message = "Incoming SMS messages received on this phone's SIM will appear here and sync to the backend."
                )
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(filtered) { msg ->
                        var isAiOn by remember(msg.fromNumber) {
                            mutableStateOf(viewModel.prefs.isAiEnabledForContact(msg.fromNumber))
                        }
                        var isBlocked by remember(msg.fromNumber) {
                            mutableStateOf(viewModel.prefs.isContactBlocked(msg.fromNumber))
                        }

                        IncomingMessageCard(
                            message = msg,
                            dateFormat = dateFormat,
                            isAiEnabled = isAiOn,
                            isBlocked = isBlocked,
                            onToggleAi = { enabled ->
                                isAiOn = enabled
                                viewModel.prefs.setAiEnabledForContact(msg.fromNumber, enabled)
                            },
                            onToggleBlock = { blocked ->
                                isBlocked = blocked
                                if (blocked) isAiOn = false
                                viewModel.prefs.setContactBlocked(msg.fromNumber, blocked)
                            }
                        )
                    }
                    item {
                        Spacer(modifier = Modifier.height(16.dp))
                    }
                }
            }
        }
    }
}

@Composable
fun IncomingMessageCard(
    message: LocalIncomingMessage,
    dateFormat: SimpleDateFormat,
    isAiEnabled: Boolean = true,
    isBlocked: Boolean = false,
    onToggleAi: (Boolean) -> Unit = {},
    onToggleBlock: (Boolean) -> Unit = {}
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
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
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = message.fromNumber,
                        fontWeight = FontWeight.Bold,
                        fontSize = 15.sp,
                        color = TextPrimary
                    )
                    if (isBlocked) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = StatusRed.copy(alpha = 0.15f)
                        ) {
                            Text(
                                text = "BLOCKED",
                                color = StatusRed,
                                fontSize = 10.sp,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                            )
                        }
                    }
                }
                StatusBadge(status = if (message.isSynced) "Synced" else "Pending Sync")
            }
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = message.body,
                fontSize = 13.sp,
                color = TextSecondary
            )
            Spacer(modifier = Modifier.height(8.dp))

            // Smart Switch & Contact Action Bar
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = if (isBlocked) "AI Blocked" else if (isAiEnabled) "AI Auto-Reply ON" else "AI Auto-Reply OFF",
                        fontSize = 11.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = if (isBlocked) TextMuted else if (isAiEnabled) StatusGreen else TextMuted
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Switch(
                        checked = isAiEnabled && !isBlocked,
                        onCheckedChange = { onToggleAi(it) },
                        enabled = !isBlocked,
                        modifier = Modifier.scale(0.75f)
                    )
                }

                TextButton(
                    onClick = { onToggleBlock(!isBlocked) },
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp)
                ) {
                    Text(
                        text = if (isBlocked) "Unblock" else "Block",
                        fontSize = 11.sp,
                        color = if (isBlocked) AccentBlue else StatusRed,
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Spacer(modifier = Modifier.height(4.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = if (message.isMultipart) "Multipart (${message.totalParts} parts)" else "Single part",
                    fontSize = 11.sp,
                    color = TextMuted
                )
                Text(
                    text = dateFormat.format(Date(message.receivedAt)),
                    fontSize = 11.sp,
                    color = TextMuted
                )
            }
        }
    }
}
