package com.stabilitymatrix.reader.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.floatPreferencesKey
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "reader_prefs")

enum class ThemeMode { SYSTEM, LIGHT, DARK }

class PreferencesStore(private val context: Context) {
    private object Keys {
        val themeMode = stringPreferencesKey("theme_mode")
        val fontScale = floatPreferencesKey("font_scale")
        val lastArticleId = stringPreferencesKey("last_article_id")
        val lastSectionIndex = intPreferencesKey("last_section_index")
        val lastScrollOffset = intPreferencesKey("last_scroll_offset")
        val bookmarks = stringSetPreferencesKey("bookmarks")
    }

    val themeMode: Flow<ThemeMode> = context.dataStore.data.map { prefs ->
        runCatching { ThemeMode.valueOf(prefs[Keys.themeMode] ?: ThemeMode.SYSTEM.name) }
            .getOrDefault(ThemeMode.SYSTEM)
    }

    val fontScale: Flow<Float> = context.dataStore.data.map { prefs ->
        prefs[Keys.fontScale] ?: 1.0f
    }

    val bookmarks: Flow<Set<String>> = context.dataStore.data.map { prefs ->
        prefs[Keys.bookmarks] ?: emptySet()
    }

    val readingProgress: Flow<ReadingProgress?> = context.dataStore.data.map { prefs ->
        val articleId = prefs[Keys.lastArticleId] ?: return@map null
        ReadingProgress(
            articleId = articleId,
            sectionIndex = prefs[Keys.lastSectionIndex] ?: 0,
            scrollOffset = prefs[Keys.lastScrollOffset] ?: 0,
        )
    }

    suspend fun setThemeMode(mode: ThemeMode) {
        context.dataStore.edit { it[Keys.themeMode] = mode.name }
    }

    suspend fun setFontScale(scale: Float) {
        context.dataStore.edit { it[Keys.fontScale] = scale.coerceIn(0.85f, 1.45f) }
    }

    suspend fun saveReadingProgress(articleId: String, sectionIndex: Int, scrollOffset: Int) {
        context.dataStore.edit {
            it[Keys.lastArticleId] = articleId
            it[Keys.lastSectionIndex] = sectionIndex
            it[Keys.lastScrollOffset] = scrollOffset
        }
    }

    suspend fun toggleBookmark(articleId: String) {
        context.dataStore.edit { prefs ->
            val current = prefs[Keys.bookmarks]?.toMutableSet() ?: mutableSetOf()
            if (!current.add(articleId)) current.remove(articleId)
            prefs[Keys.bookmarks] = current.toSet()
        }
    }

    suspend fun isBookmarked(articleId: String): Boolean {
        val bookmarks = context.dataStore.data.first()[Keys.bookmarks] ?: emptySet()
        return articleId in bookmarks
    }
}
