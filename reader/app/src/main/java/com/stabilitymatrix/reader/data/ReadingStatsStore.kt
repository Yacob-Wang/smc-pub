package com.stabilitymatrix.reader.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private val Context.readingStatsDataStore: DataStore<Preferences> by preferencesDataStore(
    name = "reading_stats",
)

@Serializable
private data class ReadingStatsJson(
    val readIds: List<String> = emptyList(),
    val seconds: Map<String, Long> = emptyMap(),
)

class ReadingStatsStore(context: Context) {
    private val appContext = context.applicationContext
    private val json = Json { ignoreUnknownKeys = true }

    private object Keys {
        val payload = stringPreferencesKey("stats_v1")
    }

    val stats: Flow<ReadingStats> = appContext.readingStatsDataStore.data.map { prefs ->
        decode(prefs[Keys.payload])
    }

    suspend fun addReadingTime(articleId: String, seconds: Int) {
        if (articleId.isBlank() || seconds <= 0) return
        appContext.readingStatsDataStore.edit { prefs ->
            val current = decode(prefs[Keys.payload])
            val updatedSeconds = current.secondsByArticle.toMutableMap()
            val newTotal = (updatedSeconds[articleId] ?: 0L) + seconds
            updatedSeconds[articleId] = newTotal

            val updatedRead = current.readIds.toMutableSet()
            if (newTotal >= READ_THRESHOLD_SECONDS) {
                updatedRead.add(articleId)
            }

            prefs[Keys.payload] = encode(
                ReadingStats(
                    readIds = updatedRead,
                    secondsByArticle = updatedSeconds,
                ),
            )
        }
    }

    private fun decode(raw: String?): ReadingStats {
        if (raw.isNullOrBlank()) return ReadingStats()
        return runCatching {
            val parsed = json.decodeFromString(ReadingStatsJson.serializer(), raw)
            ReadingStats(
                readIds = parsed.readIds.toSet(),
                secondsByArticle = parsed.seconds,
            )
        }.getOrDefault(ReadingStats())
    }

    private fun encode(stats: ReadingStats): String =
        json.encodeToString(
            ReadingStatsJson.serializer(),
            ReadingStatsJson(
                readIds = stats.readIds.sorted(),
                seconds = stats.secondsByArticle,
            ),
        )
}
