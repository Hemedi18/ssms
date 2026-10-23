package com.simsms.gateway.ui.navigation

sealed class Screen(val route: String, val title: String) {
    // 15 Screens
    object Splash : Screen("splash", "Splash")
    object Onboarding : Screen("onboarding", "Welcome")
    object Connect : Screen("connect", "Connect to Server")
    object Home : Screen("home", "Dashboard")
    object SendSms : Screen("send_sms", "Send SMS")
    object SentMessages : Screen("sent_messages", "Sent Messages")
    object ReceivedMessages : Screen("received_messages", "Received Messages")
    object Inbox : Screen("inbox", "Inbox & Delivery")
    object MessageDetail : Screen("message_detail/{messageId}", "Message Details") {
        fun createRoute(messageId: String) = "message_detail/$messageId"
    }
    object Settings : Screen("settings", "Settings")
    object ServerConfig : Screen("server_config", "Server Configuration")
    object SimInfo : Screen("sim_info", "SIM & Phone Information")
    object AppLogs : Screen("app_logs", "App Logs")
    object SetupGuide : Screen("setup_guide", "Setup Guide")
    object About : Screen("about", "About SMS Gateway")

    companion object {
        val bottomNavScreens = listOf(Home, SentMessages, Inbox, Settings)
    }
}
