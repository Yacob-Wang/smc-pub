package com.stabilitymatrix.reader.data

import kotlinx.serialization.Serializable

@Serializable
data class CatalogRoot(
    val version: Int = 1,
    val articleCount: Int = 0,
    val generatedAt: String = "",
    @Serializable(with = CatalogModuleListSerializer::class)
    val modules: List<CatalogModule> = emptyList(),
)

@Serializable
data class CatalogModule(
    val id: String,
    val title: String,
    @Serializable(with = CatalogSeriesListSerializer::class)
    val series: List<CatalogSeries> = emptyList(),
)

@Serializable
data class CatalogSeries(
    val id: String,
    val title: String,
    val readmePath: String? = null,
    val readmeId: String? = null,
    @Serializable(with = CatalogArticleListSerializer::class)
    val articles: List<CatalogArticle> = emptyList(),
)

@Serializable
data class CatalogArticle(
    val id: String,
    val title: String,
    val order: Int = 0,
    val prevId: String? = null,
    val nextId: String? = null,
)

data class SearchResult(
    val path: String,
    val title: String,
    val snippet: String = "",
)

data class ReadingProgress(
    val articleId: String,
    val sectionIndex: Int,
    val scrollOffset: Int,
)

data class ArticleNavInfo(
    val article: CatalogArticle,
    val seriesTitle: String,
    val moduleTitle: String,
)
