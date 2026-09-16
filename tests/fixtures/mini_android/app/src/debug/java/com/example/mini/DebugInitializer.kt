package com.example.mini

import android.content.Context
import com.chuckerteam.chucker.api.ChuckerInterceptor
import leakcanary.LeakCanary

object DebugInitializer {
    fun install(context: Context) {
        LeakCanary.config = LeakCanary.config.copy(dumpHeap = true)
        ChuckerInterceptor.Builder(context).build()
    }
}
