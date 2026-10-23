package com.simsms.gateway.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Update
import com.simsms.gateway.data.local.entities.LocalIncomingMessage
import kotlinx.coroutines.flow.Flow

@Dao
interface IncomingDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(message: LocalIncomingMessage): Long

    @Update
    suspend fun update(message: LocalIncomingMessage)

    @Query("SELECT * FROM incoming_messages ORDER BY receivedAt DESC")
    fun getAllFlow(): Flow<List<LocalIncomingMessage>>

    @Query("SELECT * FROM incoming_messages WHERE isSynced = 0 ORDER BY receivedAt ASC")
    suspend fun getUnsynced(): List<LocalIncomingMessage>

    @Query("SELECT COUNT(*) FROM incoming_messages")
    fun getCountFlow(): Flow<Int>

    @Query("UPDATE incoming_messages SET isSynced = 1, serverMessageId = :serverId WHERE id = :localId")
    suspend fun markSynced(localId: Long, serverId: String)

    @Query("SELECT * FROM incoming_messages WHERE fromNumber = :fromNumber AND rawPduHash = :pduHash LIMIT 1")
    suspend fun findDuplicate(fromNumber: String, pduHash: String): LocalIncomingMessage?

    @Query("DELETE FROM incoming_messages")
    suspend fun deleteAll()
}
