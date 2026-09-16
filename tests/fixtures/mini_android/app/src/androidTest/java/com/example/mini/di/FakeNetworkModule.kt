package com.example.mini.di

import dagger.Module
import dagger.Provides
import dagger.hilt.components.SingletonComponent
import dagger.hilt.testing.TestInstallIn

@Module
@TestInstallIn(components = [SingletonComponent::class], replaces = [AppModule::class])
object FakeNetworkModule {
    @Provides
    fun provideBaseUrl(): String = "http://localhost:8080/"
}
