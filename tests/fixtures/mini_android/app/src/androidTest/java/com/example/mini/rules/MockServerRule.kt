package com.example.mini.rules

import androidx.test.platform.app.InstrumentationRegistry
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.rules.TestWatcher
import org.junit.runner.Description

class MockServerRule : TestWatcher() {
    val server = MockWebServer()

    override fun starting(description: Description) {
        server.start(8080)
        server.enqueue(MockResponse().setResponseCode(200).setBody(readAsset("login_ok.json")))
    }

    override fun finished(description: Description) {
        server.shutdown()
    }

    private fun readAsset(name: String): String =
        InstrumentationRegistry.getInstrumentation().context.assets.open(name).bufferedReader().readText()
}
