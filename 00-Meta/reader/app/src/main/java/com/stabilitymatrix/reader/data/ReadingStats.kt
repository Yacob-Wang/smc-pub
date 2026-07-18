package com.stabilitymatrix.reader.data

enum class ArticleReadState {
    UNREAD,
    IN_PROGRESS,
    READ,
}

/** 单篇文章累计阅读 ≥ 45 秒视为「已读完」。 */
const val READ_THRESHOLD_SECONDS = 45L

data class ReadingStats(
    val readIds: Set<String> = emptySet(),
    val secondsByArticle: Map<String, Long> = emptyMap(),
) {
    val totalSeconds: Long get() = secondsByArticle.values.sum()

    val readCount: Int get() = readIds.size

    val inProgressCount: Int
        get() = secondsByArticle.keys.count { it !in readIds && (secondsByArticle[it] ?: 0) > 0 }

    fun stateFor(articleId: String): ArticleReadState = when {
        articleId in readIds -> ArticleReadState.READ
        (secondsByArticle[articleId] ?: 0) > 0 -> ArticleReadState.IN_PROGRESS
        else -> ArticleReadState.UNREAD
    }

    fun secondsFor(articleId: String): Long = secondsByArticle[articleId] ?: 0
}

data class CatalogReadingSummary(
    val totalArticles: Int,
    val readCount: Int,
    val inProgressCount: Int,
    val unreadCount: Int,
    val totalSeconds: Long,
) {
    val readPercent: Float
        get() = if (totalArticles == 0) 0f else readCount.toFloat() / totalArticles
}

fun formatReadingDuration(seconds: Long): String = when {
    seconds <= 0 -> "0 分钟"
    seconds < 60 -> "${seconds} 秒"
    seconds < 3600 -> {
        val m = seconds / 60
        val s = seconds % 60
        if (s == 0L) "${m} 分钟" else "${m} 分 ${s} 秒"
    }
    else -> {
        val h = seconds / 3600
        val m = (seconds % 3600) / 60
        if (m == 0L) "${h} 小时" else "${h} 小时 ${m} 分"
    }
}

object ReadingStatsHelper {
    fun allArticleIds(catalog: CatalogRoot): List<String> =
        catalog.modules.flatMap { module ->
            module.series.flatMap { series ->
                buildList {
                    series.readmeId?.let { add(it) }
                    addAll(series.articles.map { it.id })
                }
            }
        }.distinct()

    fun summarize(catalog: CatalogRoot, stats: ReadingStats): CatalogReadingSummary {
        val ids = allArticleIds(catalog)
        var read = 0
        var inProgress = 0
        var unread = 0
        for (id in ids) {
            when (stats.stateFor(id)) {
                ArticleReadState.READ -> read++
                ArticleReadState.IN_PROGRESS -> inProgress++
                ArticleReadState.UNREAD -> unread++
            }
        }
        return CatalogReadingSummary(
            totalArticles = ids.size,
            readCount = read,
            inProgressCount = inProgress,
            unreadCount = unread,
            totalSeconds = stats.totalSeconds,
        )
    }

    fun seriesArticleIds(series: CatalogSeries): List<String> = buildList {
        series.readmeId?.let { add(it) }
        addAll(series.articles.map { it.id })
    }

    fun seriesSummary(series: CatalogSeries, stats: ReadingStats): Triple<Int, Int, Int> {
        val ids = seriesArticleIds(series)
        var read = 0
        var inProgress = 0
        ids.forEach { id ->
            when (stats.stateFor(id)) {
                ArticleReadState.READ -> read++
                ArticleReadState.IN_PROGRESS -> inProgress++
                ArticleReadState.UNREAD -> Unit
            }
        }
        return Triple(read, inProgress, ids.size)
    }

    fun moduleSummary(module: CatalogModule, stats: ReadingStats): Triple<Int, Int, Int> {
        val ids = module.series.flatMap { seriesArticleIds(it) }.distinct()
        var read = 0
        var inProgress = 0
        ids.forEach { id ->
            when (stats.stateFor(id)) {
                ArticleReadState.READ -> read++
                ArticleReadState.IN_PROGRESS -> inProgress++
                ArticleReadState.UNREAD -> Unit
            }
        }
        return Triple(read, inProgress, ids.size)
    }
}
