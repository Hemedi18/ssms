package com.simsms.gateway.data.local.entities

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "messages",
    indices = [
        Index("status"),
        Index("createdAt")
    ]
)
data class LocalMessage(
    @PrimaryKey
    val id: String,
    val to: String,
    val body: String,
    val status: String, // queued, dispatched, sending, sent, delivered, failed
    val partsCount: Int = 1,
    val errorMessage: String? = null,
    val clientReference: String? = null,
    val leaseToken: String? = null,
    val sentAt: Long? = null,
    val deliveredAt: Long? = null,
    val createdAt: Long = System.currentTimeMillis()
)
