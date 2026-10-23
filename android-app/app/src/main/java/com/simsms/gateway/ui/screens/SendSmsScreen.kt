package com.simsms.gateway.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.simsms.gateway.ui.components.ConfirmationDialog
import com.simsms.gateway.ui.components.GatewayTopBar
import com.simsms.gateway.ui.theme.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel
import kotlin.math.ceil

@Composable
fun SendSmsScreen(
    viewModel: GatewayViewModel,
    onBack: () -> Unit
) {
    var countryCode by remember { mutableStateOf("+255") }
    var phoneNumber by remember { mutableStateOf("") }
    var messageText by remember { mutableStateOf("") }
    var showConfirmDialog by remember { mutableStateOf(false) }

    val isSending by viewModel.isSendingSms.collectAsState()
    val sendResult by viewModel.sendResult.collectAsState()

    // GSM multipart character math
    val charCount = messageText.length
    val partsCount = if (charCount <= 160) {
        if (charCount == 0) 0 else 1
    } else {
        ceil(charCount.toDouble() / 153.0).toInt()
    }

    val maxSinglePart = 160
    val counterText = if (charCount <= 160) {
        "$charCount / $maxSinglePart chars (1 part)"
    } else {
        "$charCount chars ($partsCount parts)"
    }

    val fullDestination = if (phoneNumber.startsWith("+")) {
        phoneNumber
    } else if (phoneNumber.startsWith("0")) {
        countryCode + phoneNumber.drop(1)
    } else {
        countryCode + phoneNumber
    }

    val isFormValid = phoneNumber.trim().length >= 8 && messageText.isNotBlank()

    Scaffold(
        topBar = {
            GatewayTopBar(
                title = "Send New SMS",
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
                .verticalScroll(rememberScrollState())
                .padding(20.dp)
        ) {
            Text(
                text = "Compose Outgoing SMS",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = TextPrimary
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "This message will be dispatched through your phone's SIM card and logged into the gateway database.",
                style = MaterialTheme.typography.bodyMedium,
                color = TextSecondary
            )

            Spacer(modifier = Modifier.height(20.dp))

            // SIM Banner
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(10.dp),
                colors = CardDefaults.cardColors(
                    containerColor = if (viewModel.isSimReady) StatusGreenLight else StatusOrangeLight
                )
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.SimCard,
                        contentDescription = null,
                        tint = if (viewModel.isSimReady) StatusGreen else StatusOrange
                    )
                    Spacer(modifier = Modifier.width(10.dp))
                    Text(
                        text = if (viewModel.isSimReady)
                            "Sending via: ${viewModel.simCarrierName ?: "Active SIM"} (Slot 1)"
                        else
                            "Warning: Physical SIM not detected or not ready",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium,
                        color = if (viewModel.isSimReady) StatusGreen else StatusOrange
                    )
                }
            }

            Spacer(modifier = Modifier.height(18.dp))

            // Phone number with country code selector
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = countryCode,
                    onValueChange = { countryCode = it },
                    label = { Text("Code") },
                    singleLine = true,
                    modifier = Modifier.width(90.dp),
                    shape = RoundedCornerShape(10.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = AccentBlue,
                        focusedContainerColor = SurfaceCard,
                        unfocusedContainerColor = SurfaceCard
                    )
                )

                OutlinedTextField(
                    value = phoneNumber,
                    onValueChange = { phoneNumber = it },
                    label = { Text("Recipient Phone Number") },
                    placeholder = { Text("712345678") },
                    leadingIcon = { Icon(Icons.Default.Phone, contentDescription = null, tint = AccentBlue) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(10.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = AccentBlue,
                        focusedContainerColor = SurfaceCard,
                        unfocusedContainerColor = SurfaceCard
                    )
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Message text area
            OutlinedTextField(
                value = messageText,
                onValueChange = { messageText = it },
                label = { Text("Message Text") },
                placeholder = { Text("Type your SMS message here...") },
                minLines = 4,
                maxLines = 8,
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(10.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = AccentBlue,
                    focusedContainerColor = SurfaceCard,
                    unfocusedContainerColor = SurfaceCard
                )
            )

            Spacer(modifier = Modifier.height(6.dp))

            // Character counter & part indication
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Text(
                    text = if (partsCount > 1) "Multipart SMS concatenated" else "Standard single SMS",
                    fontSize = 12.sp,
                    color = if (partsCount > 1) StatusOrange else TextMuted
                )
                Text(
                    text = counterText,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = if (charCount > 160) StatusOrange else TextSecondary
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Feedback banner
            if (sendResult != null) {
                val (isOk, msg) = sendResult!!
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp),
                    colors = CardDefaults.cardColors(containerColor = if (isOk) StatusGreenLight else StatusRedLight)
                ) {
                    Row(
                        modifier = Modifier.padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = if (isOk) Icons.Default.CheckCircle else Icons.Default.Error,
                            contentDescription = null,
                            tint = if (isOk) StatusGreen else StatusRed
                        )
                        Spacer(modifier = Modifier.width(10.dp))
                        Text(text = msg, color = if (isOk) StatusGreen else StatusRed, fontSize = 13.sp)
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))
            }

            Button(
                onClick = { showConfirmDialog = true },
                enabled = isFormValid && !isSending,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = AccentBlue)
            ) {
                if (isSending) {
                    CircularProgressIndicator(color = Color.White, modifier = Modifier.size(24.dp), strokeWidth = 2.dp)
                } else {
                    Icon(imageVector = Icons.Default.Send, contentDescription = null)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(text = "Send SMS Now", fontWeight = FontWeight.Bold, fontSize = 16.sp)
                }
            }
        }
    }

    if (showConfirmDialog) {
        ConfirmationDialog(
            title = "Confirm Outgoing SMS",
            message = "Send $partsCount part(s) SMS to $fullDestination?\n\nStandard carrier SMS charges may apply.",
            confirmText = "Send Now",
            onConfirm = {
                showConfirmDialog = false
                viewModel.sendManualSms(fullDestination, messageText)
            },
            onDismiss = { showConfirmDialog = false }
        )
    }
}
