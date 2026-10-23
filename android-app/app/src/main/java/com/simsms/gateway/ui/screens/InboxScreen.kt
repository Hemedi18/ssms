package com.simsms.gateway.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AllInbox
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.simsms.gateway.ui.components.*
import com.simsms.gateway.ui.navigation.Screen
import com.simsms.gateway.ui.theme.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel
import java.text.SimpleDateFormat
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InboxScreen(
    viewModel: GatewayViewModel,
    onNavigateToDetail: (String) -> Unit,
    onBottomNavigate: (String) -> Unit
) {
    var selectedTabIndex by remember { mutableIntStateOf(0) }
    val tabTitles = listOf("All", "Delivered", "Pending", "Failed")

    val allMessages by viewModel.messages.collectAsState()
    val dateFormat = remember { SimpleDateFormat("HH:mm:ss dd MMM", Locale.getDefault()) }

    val filteredMessages = when (selectedTabIndex) {
        1 -> allMessages.filter { it.status.equals("delivered", ignoreCase = true) }
        2 -> allMessages.filter { it.status.lowercase() in listOf("queued", "dispatched", "sending") }
        3 -> allMessages.filter { it.status.equals("failed", ignoreCase = true) }
        else -> allMessages
    }

    Scaffold(
        topBar = { GatewayTopBar(title = "Inbox & Delivery Status") },
        bottomBar = {
            GatewayBottomBar(
                currentRoute = Screen.Inbox.route,
                onNavigate = onBottomNavigate
            )
        },
        containerColor = BackgroundLight
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Filter Tabs
            TabRow(
                selectedTabIndex = selectedTabIndex,
                containerColor = NavyPrimary,
                contentColor = Color.White
            ) {
                tabTitles.forEachIndexed { index, title ->
                    Tab(
                        selected = selectedTabIndex == index,
                        onClick = { selectedTabIndex = index },
                        text = {
                            Text(
                                text = title,
                                fontSize = 13.sp,
                                fontWeight = if (selectedTabIndex == index) FontWeight.Bold else FontWeight.Normal,
                                color = if (selectedTabIndex == index) AccentBlueLight else Color.White.copy(alpha = 0.7f)
                            )
                        }
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            if (filteredMessages.isEmpty()) {
                EmptyStateView(
                    icon = Icons.Default.AllInbox,
                    title = "No ${tabTitles[selectedTabIndex].lowercase()} messages",
                    message = "Messages will appear under this tab once recorded with the corresponding status."
                )
            } else {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(filteredMessages) { msg ->
                        ActivityMessageCard(
                            message = msg,
                            dateFormat = dateFormat,
                            onClick = { onNavigateToDetail(msg.id) }
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
