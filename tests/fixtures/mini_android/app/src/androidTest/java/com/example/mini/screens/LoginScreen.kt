package com.example.mini.screens

import androidx.compose.ui.test.SemanticsNodeInteractionsProvider
import io.github.kakaocup.compose.node.element.ComposeScreen
import io.github.kakaocup.compose.node.element.KNode

class LoginScreen(provider: SemanticsNodeInteractionsProvider) :
    ComposeScreen<LoginScreen>(provider, viewBuilderAction = { hasTestTag("login_screen") }) {

    val emailField: KNode = child { hasTestTag("login_email") }
    val submitButton: KNode = child { hasTestTag("primary_button") }
}
