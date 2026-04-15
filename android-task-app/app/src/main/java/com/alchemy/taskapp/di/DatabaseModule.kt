package com.alchemy.taskapp.di

import android.content.Context
import androidx.room.Room
import com.alchemy.taskapp.data.TaskDao
import com.alchemy.taskapp.data.TaskDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): TaskDatabase =
        Room.databaseBuilder(
            context,
            TaskDatabase::class.java,
            TaskDatabase.DATABASE_NAME
        )
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideTaskDao(database: TaskDatabase): TaskDao = database.taskDao()
}
