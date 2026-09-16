package com.example.mini

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navDeepLink
import com.example.core.ui.MiniTheme
import com.example.feature.login.LoginRoute
import com.example.mini.ui.HomeScreen
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MiniTheme {
                val navController = rememberNavController()
                NavHost(navController = navController, startDestination = "home") {
                    composable("home") { HomeScreen(onLogin = { navController.navigate("login") }) }
                    composable(
                        route = "login",
                        deepLinks = listOf(navDeepLink { uriPattern = "https://mini.example.com/login" }),
                    ) { LoginRoute() }
                }
            }
        }
    }
}
