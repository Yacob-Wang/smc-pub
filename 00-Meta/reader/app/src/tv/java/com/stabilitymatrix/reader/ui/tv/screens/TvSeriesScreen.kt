package com.stabilitymatrix.reader.ui.tv.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.ArticleReadState
import com.stabilitymatrix.reader.data.CatalogSeries
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ReadingStatsHelper
import com.stabilitymatrix.reader.data.formatReadingDuration
import com.stabilitymatrix.reader.ui.components.ReadStatusIcon
import com.stabilitymatrix.reader.ui.components.ReadingProgressBar
import com.stabilitymatrix.reader.ui.components.moduleVisual
import com.stabilitymatrix.reader.ui.components.readStatusLabel
import com.stabilitymatrix.reader.ui.tv.TvFocusableChip
import com.stabilitymatrix.reader.ui.tv.TvFocusableSurface

private enum class TvSeriesFilter(val label: String) {
    All("全部"),
    Unread("未读"),
    InProgress("在读"),
    Read("已读"),
}

@Composable
fun TvSeriesScreen(
    series: CatalogSeries,
    moduleTitle: String,
    moduleId: String,
    readingStats: ReadingStats,
    onOpenArticle: (String) -> Unit,
) {
    var filter by remember { mutableStateOf(TvSeriesFilter.All) }
    val visual = moduleVisual(moduleId)
    val (readCount, _, totalCount) = remember(series, readingStats) {
        ReadingStatsHelper.seriesSummary(series, readingStats)
    }
    val entries = remember(series, filter, readingStats) {
        buildList {
            series.readmeId?.let { add(Triple(it, "系列导读", "README")) }
            series.articles.sortedBy { it.order }.forEach { article ->
                add(Triple(article.id, article.title, article.id.substringAfterLast('/')))
            }
        }.filter { (id, _, _) ->
            when (filter) {
                TvSeriesFilter.All -> true
                TvSeriesFilter.Unread -> readingStats.stateFor(id) == ArticleReadState.UNREAD
                TvSeriesFilter.InProgress -> readingStats.stateFor(id) == ArticleReadState.IN_PROGRESS
                TvSeriesFilter.Read -> readingStats.stateFor(id) == ArticleReadState.READ
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
            Text(moduleTitle, style = MaterialTheme.typography.labelLarge, color = visual.accent)
            Text(series.title, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            ReadingProgressBar(
                readCount = readCount,
                totalCount = totalCount,
                modifier = Modifier.padding(vertical = 12.dp),
            )
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                TvSeriesFilter.entries.forEach { item ->
                    TvFocusableChip(
                        label = item.label,
                        selected = filter == item,
                        onClick = { filter = item },
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
        }
        items(entries, key = { it.first }) { (id, title, subtitle) ->
            val state = readingStats.stateFor(id)
            val seconds = readingStats.secondsFor(id)
            TvFocusableSurface(
                onClick = { onOpenArticle(id) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 6.dp),
            ) {
                Row(
                    modifier = Modifier.padding(18.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(title, style = MaterialTheme.typography.titleLarge)
                        Text(
                            buildString {
                                append(readStatusLabel(state))
                                if (seconds > 0) append(" · ${formatReadingDuration(seconds)}")
                                append(" · ")
                                append(subtitle)
                            },
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    ReadStatusIcon(state = state)
                }
            }
        }
    }
}
