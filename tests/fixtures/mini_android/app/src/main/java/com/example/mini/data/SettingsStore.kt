package com.example.mini.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "settings")

class SettingsStore(private val context: Context) {
    private val legacyPrefs = context.getSharedPreferences("legacy", Context.MODE_PRIVATE)

    val newHomeEnabled: Flow<Boolean> =
        context.dataStore.data.map { prefs -> prefs[booleanPreferencesKey("feature_new_home")] ?: false }

    fun legacyOnboardingSeen(): Boolean = legacyPrefs.getBoolean("onboarding_seen", false)
}
