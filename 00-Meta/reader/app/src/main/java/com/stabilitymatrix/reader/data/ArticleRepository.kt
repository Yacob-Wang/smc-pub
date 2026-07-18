package com.stabilitymatrix.reader.data

import android.content.Context
import com.stabilitymatrix.reader.markdown.MarkdownSection
import com.stabilitymatrix.reader.markdown.SectionSplitter

class ArticleRepository(private val context: Context) {

    fun loadMarkdown(articleId: String): String? {
        val assetPath = "articles/$articleId.md"
        return runCatching {
            context.assets.open(assetPath).bufferedReader().use { it.readText() }
        }.getOrNull()
    }

    fun loadSections(articleId: String): List<MarkdownSection> {
        val markdown = loadMarkdown(articleId) ?: return emptyList()
        return SectionSplitter.split(markdown)
    }
}
