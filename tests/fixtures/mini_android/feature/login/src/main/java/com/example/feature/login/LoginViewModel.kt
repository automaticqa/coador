package com.example.feature.login

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.core.network.ApiService
import com.example.core.network.LoginRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class LoginUiState(val loading: Boolean = false, val error: String? = null)

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val api: ApiService,
    private val sessionStore: SessionStore,
) : ViewModel() {
    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state

    fun login(email: String, password: String) {
        viewModelScope.launch {
            _state.value = LoginUiState(loading = true)
            val token = api.login(LoginRequest(email, password))
            sessionStore.save(token.accessToken, token.refreshToken)
            _state.value = LoginUiState()
        }
    }
}
