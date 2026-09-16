package com.example.mini.suites

import com.example.mini.LoginTest
import org.junit.runner.RunWith
import org.junit.runners.Suite

@RunWith(Suite::class)
@Suite.SuiteClasses(LoginTest::class)
class SmokeSuite
