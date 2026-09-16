package com.example.mini.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import com.example.core.ui.components.PrimaryButton

@Composable
fun HomeScreen(onLogin: () -> Unit, viewModel: MainViewModel = hiltViewModel()) {
    val state by viewModel.uiState.collectAsState()
    when (state) {
        MainUiState.Loading -> Unit
        is MainUiState.Content -> PrimaryButton(text = "Login", onClick = onLogin)
    }
}
