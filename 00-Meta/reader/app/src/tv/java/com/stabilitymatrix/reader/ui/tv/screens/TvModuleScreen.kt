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
import com.stabilitymatrix.reader.data.CatalogModule
import com.stabilitymatrix.reader.data.CatalogSeries
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ReadingStatsHelper
import com.stabilitymatrix.reader.ui.components.ReadingProgressBar
import com.stabilitymatrix.reader.ui.tv.TvFocusableSurface

@Composable
fun TvModuleScreen(
    module: CatalogModule,
    readingStats: ReadingStats,
    onOpenSeries: (String, String) -> Unit,
) {
    val grouped = module.series
        .groupBy { series -> seriesGroupLabel(module.id, series.id) }
        .toSortedMap()
    val (readCount, _, totalCount) = remember(module, readingStats) {
        ReadingStatsHelper.moduleSummary(module, readingStats)
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 48.dp),
        contentPadding = PaddingValues(bottom = 24.dp),
    ) {
        item {
            Text(module.title, style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            ReadingProgressBar(
                readCount = readCount,
                totalCount = totalCount,
                modifier = Modifier.padding(vertical = 12.dp),
            )
        }
        grouped.forEach { (group, seriesList) ->
            item(key = "header-$group") {
                Text(
                    group,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.padding(top = 12.dp, bottom = 8.dp),
                )
            }
            items(seriesList.sortedBy { it.id }, key = { it.id }) { series ->
                TvSeriesRow(
                    moduleId = module.id,
                    series = series,
                    readingStats = readingStats,
                    onClick = { onOpenSeries(module.id, series.id) },
                )
            }
        }
    }
}

@Composable
private fun TvSeriesRow(
    moduleId: String,
    series: CatalogSeries,
    readingStats: ReadingStats,
    onClick: () -> Unit,
) {
    val (read, _, total) = ReadingStatsHelper.seriesSummary(series, readingStats)
    TvFocusableSurface(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp),
    ) {
        Column(Modifier.padding(18.dp)) {
            Text(series.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Medium)
            Text(
                "已读 $read / $total 篇",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun seriesGroupLabel(moduleId: String, seriesId: String): String {
    if (seriesId == moduleId) return "模块总览"
    if (seriesId.endsWith("/_misc")) return "其他文章"
    val rel = seriesId.removePrefix("$moduleId/").removePrefix(moduleId).trim('/')
    if (rel.isEmpty()) return "模块总览"
    return rel.substringBefore('/').ifEmpty { rel }
}
