package com.example.mini

import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import com.example.mini.rules.MockServerRule
import com.example.mini.screens.LoginScreen
import com.kaspersky.components.composesupport.config.withComposeSupport
import com.kaspersky.kaspresso.kaspresso.Kaspresso
import com.kaspersky.kaspresso.testcases.api.testcase.TestCase
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import io.github.kakaocup.compose.node.element.ComposeScreen.Companion.onComposeScreen
import org.junit.Rule
import org.junit.Test

@HiltAndroidTest
class LoginTest : TestCase(kaspressoBuilder = Kaspresso.Builder.withComposeSupport()) {

    @get:Rule(order = 0)
    val hiltRule = HiltAndroidRule(this)

    @get:Rule(order = 1)
    val mockServerRule = MockServerRule()

    @get:Rule(order = 2)
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test
    fun login_happy_path() = run {
        step("Open login and type e-mail") {
            onComposeScreen<LoginScreen>(composeRule) {
                emailField.performTextInput("user@example.com")
            }
        }
        step("Submit") {
            flakySafely(timeoutMs = 10_000) {
                onComposeScreen<LoginScreen>(composeRule) {
                    submitButton.performClick()
                }
            }
        }
    }
}
