package com.example.feature.login

import androidx.compose.runtime.Composable
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun LoginRoute(viewModel: LoginViewModel = hiltViewModel()) {
    LoginScreen(onSubmit = viewModel::login)
}

@Composable
fun LoginScreen(onSubmit: (String, String) -> Unit) {
    // Fields are rendered by the design system; omitted in the fixture.
}
