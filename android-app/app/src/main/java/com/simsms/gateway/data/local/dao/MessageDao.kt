package com.simsms.gateway.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.simsms.gateway.data.local.entities.LocalMessage
import kotlinx.coroutines.flow.Flow

@Dao
interface MessageDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(message: LocalMessage)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(messages: List<LocalMessage>)

    @Update
    suspend fun update(message: LocalMessage)

    @Query("SELECT * FROM messages WHERE id = :id")
    suspend fun getById(id: String): LocalMessage?

    @Query("SELECT * FROM messages ORDER BY createdAt DESC")
    fun getAllFlow(): Flow<List<LocalMessage>>

    @Query("SELECT * FROM messages WHERE status = :status ORDER BY createdAt DESC")
    fun getByStatusFlow(status: String): Flow<List<LocalMessage>>

    @Query("SELECT COUNT(*) FROM messages WHERE status = 'sent'")
    fun getSentCountFlow(): Flow<Int>

    @Query("SELECT COUNT(*) FROM messages WHERE status = 'delivered'")
    fun getDeliveredCountFlow(): Flow<Int>

    @Query("SELECT COUNT(*) FROM messages WHERE status IN ('queued', 'dispatched', 'sending')")
    fun getPendingCountFlow(): Flow<Int>

    @Query("SELECT COUNT(*) FROM messages WHERE status = 'failed'")
    fun getFailedCountFlow(): Flow<Int>

    @Query("UPDATE messages SET status = :status, errorMessage = :error WHERE id = :id")
    suspend fun updateStatus(id: String, status: String, error: String? = null)

    @Query("UPDATE messages SET status = 'sent', sentAt = :sentAt WHERE id = :id")
    suspend fun markSent(id: String, sentAt: Long = System.currentTimeMillis())

    @Query("UPDATE messages SET status = 'delivered', deliveredAt = :deliveredAt WHERE id = :id")
    suspend fun markDelivered(id: String, deliveredAt: Long = System.currentTimeMillis())

    @Query("DELETE FROM messages")
    suspend fun deleteAll()
}
