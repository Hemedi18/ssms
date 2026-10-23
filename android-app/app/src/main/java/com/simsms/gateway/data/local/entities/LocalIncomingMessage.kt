package com.simsms.gateway.data.local.entities

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "incoming_messages",
    indices = [
        Index("fromNumber"),
        Index("receivedAt"),
        Index("isSynced")
    ]
)
data class LocalIncomingMessage(
    @PrimaryKey(autoGenerate = true)
    val id: Long = 0,
    val fromNumber: String,
    val body: String,
    val receivedAt: Long = System.currentTimeMillis(),
    val isSynced: Boolean = false,
    val serverMessageId: String? = null,
    val isMultipart: Boolean = false,
    val partIndex: Int = 1,
    val totalParts: Int = 1,
    val rawPduHash: String? = null
)
