package com.simsms.gateway.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.simsms.gateway.ui.screens.*
import com.simsms.gateway.ui.viewmodel.GatewayViewModel

@Composable
fun NavGraph(
    navController: NavHostController,
    viewModel: GatewayViewModel,
    modifier: Modifier = Modifier
) {
    NavHost(
        navController = navController,
        startDestination = Screen.Splash.route,
        modifier = modifier
    ) {
        // Screen 1: Splash
        composable(Screen.Splash.route) {
            SplashScreen(
                viewModel = viewModel,
                onNavigateNext = { isPaired ->
                    if (isPaired) {
                        navController.navigate(Screen.Home.route) {
                            popUpTo(Screen.Splash.route) { inclusive = true }
                        }
                    } else {
                        navController.navigate(Screen.Onboarding.route) {
                            popUpTo(Screen.Splash.route) { inclusive = true }
                        }
                    }
                }
            )
        }

        // Screen 2: Onboarding
        composable(Screen.Onboarding.route) {
            OnboardingScreen(
                onGetStarted = {
                    navController.navigate(Screen.Connect.route)
                },
                onViewGuide = {
                    navController.navigate(Screen.SetupGuide.route)
                }
            )
        }

        // Screen 3: Connect
        composable(Screen.Connect.route) {
            ConnectScreen(
                viewModel = viewModel,
                onConnectedSuccess = {
                    navController.navigate(Screen.Home.route) {
                        popUpTo(Screen.Onboarding.route) { inclusive = true }
                    }
                },
                onBack = { navController.popBackStack() },
                onOpenGuide = { navController.navigate(Screen.SetupGuide.route) }
            )
        }

        // Screen 4: Home / Dashboard
        composable(Screen.Home.route) {
            DashboardScreen(
                viewModel = viewModel,
                onNavigateToSendSms = { navController.navigate(Screen.SendSms.route) },
                onNavigateToMessageDetail = { messageId ->
                    navController.navigate(Screen.MessageDetail.createRoute(messageId))
                },
                onNavigateToLogs = { navController.navigate(Screen.AppLogs.route) },
                onNavigateToSettings = { navController.navigate(Screen.Settings.route) },
                onBottomNavigate = { route ->
                    navController.navigate(route) {
                        popUpTo(Screen.Home.route) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            )
        }

        // Screen 5: Send SMS
        composable(Screen.SendSms.route) {
            SendSmsScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }

        // Screen 6: Sent Messages
        composable(Screen.SentMessages.route) {
            SentMessagesScreen(
                viewModel = viewModel,
                onNavigateToDetail = { messageId ->
                    navController.navigate(Screen.MessageDetail.createRoute(messageId))
                },
                onBottomNavigate = { route ->
                    navController.navigate(route) {
                        popUpTo(Screen.Home.route) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            )
        }

        // Screen 7: Received Messages
        composable(Screen.ReceivedMessages.route) {
            ReceivedMessagesScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() }
            )
        }

        // Screen 8: Inbox & Delivery
        composable(Screen.Inbox.route) {
            InboxScreen(
                viewModel = viewModel,
                onNavigateToDetail = { messageId ->
                    navController.navigate(Screen.MessageDetail.createRoute(messageId))
                },
                onBottomNavigate = { route ->
                    navController.navigate(route) {
                        popUpTo(Screen.Home.route) { saveState = true }
                        launchSingleTop = true
                        restoreState = true
                    }
                }
            )
        }

        // Screen 9: Message Details
        composable(
            route = Screen.MessageDetail.route,
            arguments = listOf(navArgument("messageId") { type = NavType.StringType })
        ) { backStackEntry ->
            val messageId = backStackEntry.arguments?.getString("messageId") ?: ""
            MessageDetailScreen(
                navController = navController,
                viewModel = viewModel,
                messageId = messageId
            )
        }

        // Screen 10: Settings
        composable(Screen.Settings.route) {
            SettingsScreen(navController = navController, viewModel = viewModel)
        }

        // Screen 11: Server Configuration
        composable(Screen.ServerConfig.route) {
            ServerConfigScreen(navController = navController, viewModel = viewModel)
        }

        // Screen 12: SIM & Phone Information
        composable(Screen.SimInfo.route) {
            SimInfoScreen(navController = navController, viewModel = viewModel)
        }

        // Screen 13: App Logs
        composable(Screen.AppLogs.route) {
            AppLogsScreen(navController = navController, viewModel = viewModel)
        }

        // Screen 14: Setup Guide
        composable(Screen.SetupGuide.route) {
            SetupGuideScreen(navController = navController)
        }

        // Screen 15: About
        composable(Screen.About.route) {
            AboutScreen(navController = navController, viewModel = viewModel)
        }
    }
}
