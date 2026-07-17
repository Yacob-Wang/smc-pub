package com.stabilitymatrix.reader.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
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

private enum class SeriesReadFilter(val label: String) {
    All("全部"),
    Unread("未读"),
    InProgress("在读"),
    Read("已读"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SeriesScreen(
    series: CatalogSeries,
    moduleTitle: String,
    moduleId: String,
    readingStats: ReadingStats,
    onBack: () -> Unit,
    onOpenArticle: (String) -> Unit,
) {
    var filter by remember { mutableStateOf(SeriesReadFilter.All) }
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val visual = moduleVisual(moduleId)
    val (readCount, _, totalCount) = remember(series, readingStats) {
        ReadingStatsHelper.seriesSummary(series, readingStats)
    }

    val entries = remember(series, filter, readingStats) {
        buildList {
            series.readmeId?.let { readmeId ->
                add(SeriesEntry(0, readmeId, "系列导读", "README · 建议先读"))
            }
            series.articles.sortedBy { it.order }.forEach { article ->
                add(
                    SeriesEntry(
                        order = article.order,
                        id = article.id,
                        title = article.title,
                        subtitle = article.id.substringAfterLast('/'),
                    ),
                )
            }
        }.filter { entry ->
            when (filter) {
                SeriesReadFilter.All -> true
                SeriesReadFilter.Unread -> readingStats.stateFor(entry.id) == ArticleReadState.UNREAD
                SeriesReadFilter.InProgress -> readingStats.stateFor(entry.id) == ArticleReadState.IN_PROGRESS
                SeriesReadFilter.Read -> readingStats.stateFor(entry.id) == ArticleReadState.READ
            }
        }
    }

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            LargeTopAppBar(
                title = {
                    Text(series.title, maxLines = 2, overflow = TextOverflow.Ellipsis)
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "返回")
                    }
                },
                scrollBehavior = scrollBehavior,
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            item {
                Text(
                    moduleTitle,
                    style = MaterialTheme.typography.labelLarge,
                    color = visual.accent,
                )
            }
            item {
                ReadingProgressBar(readCount = readCount, totalCount = totalCount)
            }
            item {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(SeriesReadFilter.entries) { item ->
                        FilterChip(
                            selected = filter == item,
                            onClick = { filter = item },
                            label = { Text(item.label) },
                        )
                    }
                }
            }
            if (entries.isEmpty()) {
                item {
                    Text(
                        text = "当前筛选下没有文章",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(vertical = 24.dp),
                    )
                }
            } else {
                items(entries, key = { it.id }) { entry ->
                    val state = readingStats.stateFor(entry.id)
                    val seconds = readingStats.secondsFor(entry.id)
                    ArticleListItem(
                        order = entry.order,
                        title = entry.title,
                        subtitle = buildString {
                            append(readStatusLabel(state))
                            if (seconds > 0) append(" · ${formatReadingDuration(seconds)}")
                            append(" · ")
                            append(entry.subtitle)
                        },
                        accent = visual.accent,
                        readState = state,
                        onClick = { onOpenArticle(entry.id) },
                    )
                }
            }
        }
    }
}

private data class SeriesEntry(
    val order: Int,
    val id: String,
    val title: String,
    val subtitle: String,
)

@Composable
private fun ArticleListItem(
    order: Int,
    title: String,
    subtitle: String,
    accent: androidx.compose.ui.graphics.Color,
    readState: ArticleReadState,
    onClick: () -> Unit,
) {
    val containerColor = when (readState) {
        ArticleReadState.READ -> MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.35f)
        ArticleReadState.IN_PROGRESS -> MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.45f)
        ArticleReadState.UNREAD -> MaterialTheme.colorScheme.surfaceContainerLow
    }
    Surface(
        onClick = onClick,
        shape = MaterialTheme.shapes.large,
        color = containerColor,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (order > 0) {
                Surface(
                    shape = CircleShape,
                    color = accent.copy(alpha = 0.14f),
                    modifier = Modifier.size(36.dp),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            text = order.toString().padStart(2, '0'),
                            style = MaterialTheme.typography.labelMedium,
                            color = accent,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
                Spacer(Modifier.width(12.dp))
            }
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Medium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            Spacer(Modifier.width(8.dp))
            ReadStatusIcon(state = readState)
        }
    }
}
