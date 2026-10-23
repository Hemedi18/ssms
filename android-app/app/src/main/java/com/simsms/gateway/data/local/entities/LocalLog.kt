package com.simsms.gateway.data.local.entities

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "app_logs",
    indices = [
        Index("category"),
        Index("timestamp")
    ]
)
data class LocalLog(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val category: String, // Sent, Received, System, Connection, Error
    val message: String,
    val details: String? = null,
    val timestamp: Long = System.currentTimeMillis()
)
