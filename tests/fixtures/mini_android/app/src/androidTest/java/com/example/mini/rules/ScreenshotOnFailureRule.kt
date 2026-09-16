package com.example.mini.rules

import androidx.test.runner.screenshot.Screenshot
import org.junit.rules.TestWatcher
import org.junit.runner.Description

class ScreenshotOnFailureRule : TestWatcher() {
    override fun failed(e: Throwable?, description: Description) {
        Screenshot.capture().setName(description.methodName).process()
    }
}
