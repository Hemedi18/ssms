package com.simsms.gateway.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.simsms.gateway.ui.components.GatewayTopAppBar
import com.simsms.gateway.ui.theme.*

@Composable
fun SetupGuideScreen(navController: NavController) {
    Scaffold(
        topBar = {
            GatewayTopAppBar(
                title = "Setup Guide & Tutorial",
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
            Text(
                "COMPLETE SETUP TUTORIAL",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.Bold,
                color = TextSecondary
            )

            // Step 1
            TutorialStepCard(
                step = 1,
                title = "Start the Python Backend",
                description = "Run the FastAPI backend on your server, Docker container, or local development workstation.",
                codeSnippet = "cd backend\npython -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
            )

            // Step 2
            TutorialStepCard(
                step = 2,
                title = "Generate a Pairing Code",
                description = "In the backend terminal, create an 8-character single-use pairing code for your Android phone:",
                codeSnippet = "python -m app.cli create-pairing-code --name \"OfficePhone\""
            )

            // Step 3
            TutorialStepCard(
                step = 3,
                title = "Connect Android App to Server",
                description = "In the Android app, go to 'Connect to Server', enter the Server URL (e.g. http://10.0.2.2:8000 for emulator or https://sms.yourdomain.com for production) and the 8-character pairing code.",
                codeSnippet = null
            )

            // Step 4
            TutorialStepCard(
                step = 4,
                title = "Grant SMS Permissions",
                description = "When prompted by Android, grant 'Send SMS' and 'Receive SMS' runtime permissions. These are strictly required for the phone to access the cellular modem.",
                codeSnippet = null
            )

            // Step 5
            TutorialStepCard(
                step = 5,
                title = "Confirm SIM Readiness",
                description = "Check the SIM status on the Dashboard or SIM Information screen. Ensure your SIM card is active, has carrier reception, and possesses airtime credit.",
                codeSnippet = null
            )

            // Step 6
            TutorialStepCard(
                step = 6,
                title = "Test Connectivity",
                description = "Ensure the Dashboard displays 'CONNECTED'. The app sends periodic authenticated heartbeats and polls for pending jobs.",
                codeSnippet = null
            )

            // Step 7
            TutorialStepCard(
                step = 7,
                title = "Send a Test SMS",
                description = "Use the 'Send New SMS' button on the Dashboard to transmit a test message to your personal mobile number and verify dispatch.",
                codeSnippet = null
            )

            // Step 8
            TutorialStepCard(
                step = 8,
                title = "Configure External API Clients",
                description = "Create an API key on the backend to allow your web application or CRM to queue SMS requests:",
                codeSnippet = "python -m app.cli create-api-key --name \"ProductionAPI\"\n# Send SMS via HTTP POST /api/v1/messages"
            )

            // Step 9
            TutorialStepCard(
                step = 9,
                title = "Configure Webhook Subscriptions",
                description = "Register webhooks to receive real-time notifications when an SMS is sent, delivered, failed, or received by your phone:",
                codeSnippet = "POST /api/v1/webhooks\n{\n  \"url\": \"https://yourapp.com/webhooks/sms\",\n  \"events\": [\"sms.sent\", \"sms.delivered\", \"sms.received\"]\n}"
            )

            // Step 10: Troubleshooting
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Icon(Icons.Default.Warning, contentDescription = null, tint = StatusOrange)
                        Text(
                            "Step 10: Troubleshooting Common Issues",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    HorizontalDivider(color = BorderSubtle)

                    TroubleshootingItem(
                        problem = "Offline Server / Connection Refused",
                        solution = "Check that your phone and server are on the same local network, or that the server has a valid public HTTPS URL. On Android emulators, use http://10.0.2.2:8000."
                    )
                    TroubleshootingItem(
                        problem = "Missing SMS Permissions",
                        solution = "Open Android Settings > Apps > SMS Gateway > Permissions, and enable SMS and Phone permissions manually."
                    )
                    TroubleshootingItem(
                        problem = "SIM Not Ready / Absent",
                        solution = "Ensure a physical SIM card is inserted. Emulators do not have physical cellular SIMs and will fail on real SMS dispatch."
                    )
                    TroubleshootingItem(
                        problem = "Background Disconnection",
                        solution = "Enable the 'Continuous Gateway Service' in Settings and exclude the SMS Gateway app from Android Battery Optimization."
                    )
                }
            }
        }
    }
}

@Composable
private fun TutorialStepCard(
    step: Int,
    title: String,
    description: String,
    codeSnippet: String?
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = SurfaceCard),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(28.dp)
                        .clip(CircleShape)
                        .background(PrimaryBlue),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = "$step",
                        color = Color.White,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
                }
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
            }

            Text(
                text = description,
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )

            if (codeSnippet != null) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(BackgroundDark)
                        .padding(12.dp)
                ) {
                    Text(
                        text = codeSnippet,
                        fontFamily = FontFamily.Monospace,
                        fontSize = 12.sp,
                        color = Color.White
                    )
                }
            }
        }
    }
}

@Composable
private fun TroubleshootingItem(problem: String, solution: String) {
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text("• $problem", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, color = StatusRed)
        Text(solution, style = MaterialTheme.typography.bodySmall, color = TextSecondary, modifier = Modifier.padding(start = 12.dp))
    }
}
