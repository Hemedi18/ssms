package com.simsms.gateway

import com.simsms.gateway.ui.navigation.Screen
import org.junit.Assert.*
import org.junit.Test

class NavigationRoutesTest {

    @Test
    fun testAllFifteenScreensExist() {
        val allScreens = listOf(
            Screen.Splash,
            Screen.Onboarding,
            Screen.Connect,
            Screen.Home,
            Screen.SendSms,
            Screen.SentMessages,
            Screen.ReceivedMessages,
            Screen.Inbox,
            Screen.MessageDetail,
            Screen.Settings,
            Screen.ServerConfig,
            Screen.SimInfo,
            Screen.AppLogs,
            Screen.SetupGuide,
            Screen.About
        )

        assertEquals(15, allScreens.size)

        // Ensure each screen has a unique route
        val routes = allScreens.map { it.route }
        assertEquals(routes.distinct().size, routes.size)
    }

    @Test
    fun testBottomNavScreens() {
        val bottomScreens = Screen.bottomNavScreens
        assertEquals(4, bottomScreens.size)
        assertTrue(bottomScreens.contains(Screen.Home))
        assertTrue(bottomScreens.contains(Screen.SentMessages))
        assertTrue(bottomScreens.contains(Screen.Inbox))
        assertTrue(bottomScreens.contains(Screen.Settings))
    }

    @Test
    fun testParameterizedMessageDetailRoute() {
        val testId = "msg-uuid-12345"
        val generatedRoute = Screen.MessageDetail.createRoute(testId)
        assertEquals("message_detail/msg-uuid-12345", generatedRoute)
    }
}
