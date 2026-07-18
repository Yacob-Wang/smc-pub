package com.stabilitymatrix.reader.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import java.io.FileOutputStream

class SearchRepository(context: Context) {
    private val db: SQLiteDatabase

    init {
        val dbName = "articles_search.db"
        val dbFile = context.getDatabasePath(dbName)
        if (!dbFile.exists()) {
            dbFile.parentFile?.mkdirs()
            context.assets.open("articles.db").use { input ->
                FileOutputStream(dbFile).use { output -> input.copyTo(output) }
            }
        }
        db = SQLiteDatabase.openDatabase(
            dbFile.path,
            null,
            SQLiteDatabase.OPEN_READONLY,
        )
    }

    fun search(rawQuery: String, limit: Int = 50): List<SearchResult> {
        val query = rawQuery.trim()
        if (query.length < 2) return emptyList()

        val ftsQuery = query.split(Regex("\\s+"))
            .filter { it.isNotBlank() }
            .joinToString(" ") { token ->
                val escaped = token.replace("\"", "\"\"")
                "\"$escaped\"*"
            }

        val results = mutableListOf<SearchResult>()
        db.rawQuery(
            """
            SELECT path, title, snippet(articles_fts, 2, '', '', '…', 40) AS snippet
            FROM articles_fts
            WHERE articles_fts MATCH ?
            LIMIT ?
            """.trimIndent(),
            arrayOf(ftsQuery, limit.toString()),
        ).use { cursor ->
            val pathIdx = cursor.getColumnIndex("path")
            val titleIdx = cursor.getColumnIndex("title")
            val snippetIdx = cursor.getColumnIndex("snippet")
            while (cursor.moveToNext()) {
                results += SearchResult(
                    path = cursor.getString(pathIdx),
                    title = cursor.getString(titleIdx),
                    snippet = cursor.getString(snippetIdx) ?: "",
                )
            }
        }
        return results
    }
}
