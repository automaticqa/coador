package com.example.mini

import app.cash.turbine.test
import com.example.mini.data.User
import com.example.mini.data.UserRepository
import com.example.mini.ui.MainUiState
import com.example.mini.ui.MainViewModel
import io.mockk.coEvery
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class MainViewModelTest {

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    private val repository: UserRepository = mockk()

    @Test
    fun `load emits content state`() = runTest {
        coEvery { repository.currentUser() } returns User(1, "Ada")
        val viewModel = MainViewModel(repository)

        viewModel.uiState.test {
            assertEquals(MainUiState.Loading, awaitItem())
            viewModel.load()
            assertEquals(MainUiState.Content("Ada"), awaitItem())
        }
    }
}
