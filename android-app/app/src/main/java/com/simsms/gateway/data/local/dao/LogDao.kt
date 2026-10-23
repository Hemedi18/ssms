package com.simsms.gateway.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import com.simsms.gateway.data.local.entities.LocalLog
import kotlinx.coroutines.flow.Flow

@Dao
interface LogDao {
    @Insert
    suspend fun insert(log: LocalLog)

    @Query("SELECT * FROM app_logs ORDER BY timestamp DESC LIMIT 200")
    fun getAllFlow(): Flow<List<LocalLog>>

    @Query("SELECT * FROM app_logs WHERE category = :category ORDER BY timestamp DESC LIMIT 200")
    fun getByCategoryFlow(category: String): Flow<List<LocalLog>>

    @Query("DELETE FROM app_logs")
    suspend fun clearAll()
}
