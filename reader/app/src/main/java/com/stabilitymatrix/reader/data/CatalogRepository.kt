package com.stabilitymatrix.reader.data

import android.content.Context
import kotlinx.serialization.json.Json

class CatalogRepository(context: Context) {
    private val json = Json { ignoreUnknownKeys = true }

    val catalog: CatalogRoot by lazy {
        context.assets.open("catalog.json").bufferedReader().use { reader ->
            json.decodeFromString(CatalogRoot.serializer(), reader.readText())
        }
    }

    private val articleIndex: Map<String, Pair<CatalogModule, CatalogSeries>> by lazy {
        buildMap {
            catalog.modules.forEach { module ->
                module.series.forEach { series ->
                    series.articles.forEach { article ->
                        put(article.id, module to series)
                    }
                }
            }
        }
    }

    fun findArticle(articleId: String): ArticleNavInfo? {
        val (module, series) = articleIndex[articleId] ?: return null
        val article = series.articles.firstOrNull { it.id == articleId } ?: return null
        return ArticleNavInfo(article, series.title, module.title)
    }

    fun getAllArticles(): List<CatalogArticle> =
        catalog.modules.flatMap { module ->
            module.series.flatMap { it.articles }
        }
}
