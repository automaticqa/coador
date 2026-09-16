package com.example.core.network

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

data class UserDto(val id: Long, val name: String)
data class LoginRequest(val email: String, val password: String)
data class TokenDto(val accessToken: String, val refreshToken: String)

interface ApiService {
    @GET("users/{id}")
    suspend fun user(@Path("id") id: Long): UserDto

    @POST("auth/login")
    suspend fun login(@Body body: LoginRequest): TokenDto
}
