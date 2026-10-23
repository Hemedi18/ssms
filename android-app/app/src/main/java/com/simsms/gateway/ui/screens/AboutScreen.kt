package com.simsms.gateway.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.simsms.gateway.ui.components.GatewayTopAppBar
import com.simsms.gateway.ui.components.StatusBadge
import com.simsms.gateway.ui.theme.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel

@Composable
fun AboutScreen(
    navController: NavController,
    viewModel: GatewayViewModel
) {
    val isConnected by viewModel.isConnected.collectAsState()
    val isPaired by viewModel.isPaired.collectAsState()

    Scaffold(
        topBar = {
            GatewayTopAppBar(
                title = "About SMS Gateway",
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
            // Header Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Shield,
                        contentDescription = null,
                        tint = PrimaryBlue,
                        modifier = Modifier.size(48.dp)
                    )

                    Text(
                        text = "SIM SMS Gateway",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = NavyPrimary
                    )

                    Text(
                        text = "Version 1.0.0 (Build 2026.10)",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )

                    Spacer(modifier = Modifier.height(4.dp))

                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text("Backend Connection:", style = MaterialTheme.typography.bodySmall, color = TextSecondary)
                        StatusBadge(status = if (isConnected) "connected" else if (isPaired) "idle" else "offline")
                    }

                    Spacer(modifier = Modifier.height(4.dp))

                    Text(
                        text = "Turns an Android smartphone with a working SIM card into an automated cellular SMS gateway. Bridges external REST APIs, web applications, and webhooks directly to the cellular network.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextPrimary
                    )
                }
            }

            // Privacy Information
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Icons.Default.Lock, contentDescription = null, tint = PrimaryBlue, modifier = Modifier.size(20.dp))
                        Text("Privacy & Security Information", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    }

                    HorizontalDivider(color = BorderSubtle)

                    Text(
                        text = "• All device pairing tokens and server credentials are encrypted on-device using the Android Keystore system.\n" +
                                "• Outgoing and received messages are stored in an encrypted Room SQLite database.\n" +
                                "• Phone numbers and message contents are never displayed in plaintext routine diagnostic logs.\n" +
                                "• Network communication requires TLS / HTTPS for remote servers.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )
                }
            }

            // Terms of Use & Carrier Compliance
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Icons.Default.Info, contentDescription = null, tint = PrimaryBlue, modifier = Modifier.size(20.dp))
                        Text("Carrier Compliance & Terms", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    }

                    HorizontalDivider(color = BorderSubtle)

                    Text(
                        text = "This application is designed for legitimate transactional, notification, and alert messaging. The operator is strictly responsible for adhering to applicable telecommunications laws, carrier fair-use agreements, anti-spam policies, and recipient opt-in consent regulations. Bulk spam, phishing, OTP interception, and unauthorized messaging are strictly prohibited.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )
                }
            }

            // Support & Documentation
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Technical Support & Architecture", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    Text(
                        text = "Architecture: FastAPI backend with SQLAlchemy 2, Alembic, SQLite/PostgreSQL, HMAC-SHA256 webhooks, and Jetpack Compose Android client.\n" +
                                "Project: sim-sms-gateway",
                        style = MaterialTheme.typography.bodySmall,
                        color = TextSecondary
                    )
                }
            }
        }
    }
}
