package com.stabilitymatrix.reader.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LargeTopAppBar
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.CatalogModule
import com.stabilitymatrix.reader.data.CatalogSeries
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ReadingStatsHelper
import com.stabilitymatrix.reader.ui.components.AccentListTile
import com.stabilitymatrix.reader.ui.components.ModuleIconBadge
import com.stabilitymatrix.reader.ui.components.ReadingProgressBar
import com.stabilitymatrix.reader.ui.components.SectionHeader

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ModuleScreen(
    module: CatalogModule,
    readingStats: ReadingStats,
    onBack: () -> Unit,
    onOpenSeries: (String, String) -> Unit,
) {
    val grouped = module.series
        .groupBy { series -> seriesGroupLabel(module.id, series.id) }
        .toSortedMap()
    val scrollBehavior = TopAppBarDefaults.exitUntilCollapsedScrollBehavior()
    val (readCount, _, totalCount) = remember(module, readingStats) {
        ReadingStatsHelper.moduleSummary(module, readingStats)
    }

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            LargeTopAppBar(
                title = {
                    Column {
                        Text(module.title)
                        Text(
                            "${module.series.size} 个系列 · $totalCount 篇",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
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
                ReadingProgressBar(readCount = readCount, totalCount = totalCount)
            }
            item {
                SectionHeader("系列列表", "已读系列会显示进度")
            }
            grouped.forEach { (group, seriesList) ->
                item(key = "header-$group") {
                    Text(
                        text = group,
                        style = MaterialTheme.typography.labelLarge,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(top = 12.dp, bottom = 4.dp),
                    )
                }
                items(seriesList.sortedBy { it.id }, key = { it.id }) { series ->
                    SeriesListItem(
                        moduleId = module.id,
                        series = series,
                        readingStats = readingStats,
                        onClick = { onOpenSeries(module.id, series.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun SeriesListItem(
    moduleId: String,
    series: CatalogSeries,
    readingStats: ReadingStats,
    onClick: () -> Unit,
) {
    val (read, _, total) = ReadingStatsHelper.seriesSummary(series, readingStats)
    AccentListTile(
        title = series.title,
        subtitle = "已读 $read / $total 篇 · ${series.id.removePrefix("$moduleId/")}",
        leading = { ModuleIconBadge(moduleId) },
        trailing = {
            Icon(
                Icons.AutoMirrored.Filled.ArrowForward,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        },
        onClick = onClick,
    )
}

private fun seriesGroupLabel(moduleId: String, seriesId: String): String {
    if (seriesId == moduleId) return "模块总览"
    if (seriesId.endsWith("/_misc")) return "其他文章"
    val rel = seriesId.removePrefix("$moduleId/").removePrefix(moduleId).trim('/')
    if (rel.isEmpty()) return "模块总览"
    return rel.substringBefore('/').ifEmpty { rel }
}
