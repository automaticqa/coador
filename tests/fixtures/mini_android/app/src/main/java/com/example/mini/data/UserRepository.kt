package com.example.mini.data

import com.example.core.network.ApiService
import javax.inject.Inject

data class User(val id: Long, val name: String)

class UserRepository @Inject constructor(
    private val api: ApiService,
    private val dao: UserDao,
) {
    suspend fun currentUser(): User {
        val dto = api.user(1)
        return User(dto.id, dto.name)
    }
}
