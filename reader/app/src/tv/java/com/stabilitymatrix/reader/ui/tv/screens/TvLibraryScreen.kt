package com.stabilitymatrix.reader.ui.tv.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.ArticleReadState
import com.stabilitymatrix.reader.data.CatalogRepository
import com.stabilitymatrix.reader.data.CatalogRoot
import com.stabilitymatrix.reader.data.ReadingProgress
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ReadingStatsHelper
import com.stabilitymatrix.reader.data.formatReadingDuration
import com.stabilitymatrix.reader.ui.components.ReadingStatsCard
import com.stabilitymatrix.reader.ui.components.readStatusLabel
import com.stabilitymatrix.reader.ui.tv.TvFocusableSurface

@Composable
fun TvLibraryScreen(
    catalog: CatalogRoot,
    catalogRepository: CatalogRepository,
    readingProgress: ReadingProgress?,
    readingStats: ReadingStats,
    onOpenArticle: (String) -> Unit,
) {
    val summary = remember(catalog, readingStats) {
        ReadingStatsHelper.summarize(catalog, readingStats)
    }
    val inProgress = remember(catalog, readingStats) {
        ReadingStatsHelper.allArticleIds(catalog)
            .filter { readingStats.stateFor(it) == ArticleReadState.IN_PROGRESS }
            .sortedByDescending { readingStats.secondsFor(it) }
            .take(15)
            .mapNotNull { id ->
                catalogRepository.findArticle(id)?.let { info ->
                    Triple(id, info.article.title, readingStats.secondsFor(id))
                }
            }
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 48.dp),
        contentPadding = PaddingValues(bottom = 24.dp),
    ) {
        item {
            ReadingStatsCard(summary = summary, modifier = Modifier.padding(bottom = 16.dp))
        }
        if (readingProgress != null) {
            item {
                Text("继续阅读", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            }
            item {
                TvFocusableSurface(
                    onClick = { onOpenArticle(readingProgress.articleId) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 8.dp),
                ) {
                    Column(Modifier.padding(18.dp)) {
                        Text(readingProgress.articleId.substringAfterLast('/'), style = MaterialTheme.typography.titleMedium)
                    }
                }
            }
        }
        item {
            Text(
                "在读中",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(top = 12.dp, bottom = 8.dp),
            )
        }
        if (inProgress.isEmpty()) {
            item {
                Text("暂无进行中的文章", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        } else {
            items(inProgress, key = { it.first }) { (id, title, seconds) ->
                TvFocusableSurface(
                    onClick = { onOpenArticle(id) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 6.dp),
                ) {
                    Column(Modifier.padding(18.dp)) {
                        Text(title, style = MaterialTheme.typography.titleMedium)
                        Text(
                            "${readStatusLabel(ArticleReadState.IN_PROGRESS)} · ${formatReadingDuration(seconds)}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
    }
}

@Composable
fun TvSettingsScreen(
    fontScale: Float,
    onFontScaleChange: (Float) -> Unit,
) {
    val steps = listOf(1.0f, 1.15f, 1.25f, 1.4f)
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 48.dp),
    ) {
        item {
            Text("设置", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.padding(bottom = 16.dp))
            Text("正文字号（电视推荐 1.25 及以上）", style = MaterialTheme.typography.titleMedium)
        }
        items(steps) { scale ->
            TvFocusableSurface(
                onClick = { onFontScaleChange(scale) },
                selected = fontScale == scale,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 8.dp),
            ) {
                Column(Modifier.padding(18.dp)) {
                    Text("${(scale * 100).toInt()}%", style = MaterialTheme.typography.titleLarge)
                }
            }
        }
    }
}
