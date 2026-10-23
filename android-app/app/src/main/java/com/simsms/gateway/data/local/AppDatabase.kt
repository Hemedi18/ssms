package com.simsms.gateway.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import com.simsms.gateway.data.local.dao.IncomingDao
import com.simsms.gateway.data.local.dao.LogDao
import com.simsms.gateway.data.local.dao.MessageDao
import com.simsms.gateway.data.local.entities.LocalIncomingMessage
import com.simsms.gateway.data.local.entities.LocalLog
import com.simsms.gateway.data.local.entities.LocalMessage

@Database(
    entities = [
        LocalMessage::class,
        LocalIncomingMessage::class,
        LocalLog::class
    ],
    version = 1,
    exportSchema = false
)
abstract class AppDatabase : RoomDatabase() {
    abstract fun messageDao(): MessageDao
    abstract fun incomingDao(): IncomingDao
    abstract fun logDao(): LogDao

    companion object {
        @Volatile
        private var instance: AppDatabase? = null

        fun getDatabase(context: Context): AppDatabase {
            return instance ?: synchronized(this) {
                instance ?: Room.databaseBuilder(
                    context.applicationContext,
                    AppDatabase::class.java,
                    "sim_sms_gateway.db"
                ).fallbackToDestructiveMigration().build().also { instance = it }
            }
        }
    }
}
