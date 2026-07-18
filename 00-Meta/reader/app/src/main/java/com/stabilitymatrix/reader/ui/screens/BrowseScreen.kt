package com.stabilitymatrix.reader.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.CatalogModule
import com.stabilitymatrix.reader.data.CatalogRoot
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ReadingStatsHelper
import com.stabilitymatrix.reader.ui.components.ModuleIconBadge
import com.stabilitymatrix.reader.ui.components.ReadingProgressBar
import com.stabilitymatrix.reader.ui.components.ReaderSearchBar
import com.stabilitymatrix.reader.ui.components.SectionHeader
import com.stabilitymatrix.reader.ui.components.moduleVisual

private enum class BrowseFilter(val label: String) {
    All("全部"),
    Kernel("Kernel"),
    Runtime("Runtime"),
    Framework("Framework"),
    Other("其他"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BrowseScreen(
    catalog: CatalogRoot,
    readingStats: ReadingStats,
    onOpenModule: (String) -> Unit,
    onSearch: () -> Unit,
) {
    var filter by remember { mutableStateOf(BrowseFilter.All) }
    val modules = remember(catalog, filter) {
        val all = catalog.modules.filter { it.id != "_root" }
        when (filter) {
            BrowseFilter.All -> all
            BrowseFilter.Kernel -> all.filter { it.id == "Linux_Kernel" }
            BrowseFilter.Runtime -> all.filter { it.id == "Runtime" }
            BrowseFilter.Framework -> all.filter { it.id == "Android_Framework" }
            BrowseFilter.Other -> all.filter {
                it.id !in setOf("Linux_Kernel", "Runtime", "Android_Framework")
            }
        }
    }

    Scaffold(containerColor = MaterialTheme.colorScheme.surface) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp),
        ) {
            Spacer(Modifier.height(8.dp))
            SectionHeader("知识目录", "按模块 → 系列 → 文章三级浏览")
            Spacer(Modifier.height(12.dp))
            ReaderSearchBar(
                placeholder = "全文搜索 532+ 篇技术文章",
                onClick = onSearch,
            )
            Spacer(Modifier.height(16.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(BrowseFilter.entries.size) { index ->
                    val item = BrowseFilter.entries[index]
                    FilterChip(
                        selected = filter == item,
                        onClick = { filter = item },
                        label = { Text(item.label) },
                    )
                }
            }
            Spacer(Modifier.height(12.dp))
            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(bottom = 24.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(modules, key = { it.id }) { module ->
                    ModuleGridCard(
                        module = module,
                        readingStats = readingStats,
                        onClick = { onOpenModule(module.id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun ModuleGridCard(
    module: CatalogModule,
    readingStats: ReadingStats,
    onClick: () -> Unit,
) {
    val visual = moduleVisual(module.id)
    val articleCount = module.series.sumOf { it.articles.size }
    val (readCount, _, totalCount) = ReadingStatsHelper.moduleSummary(module, readingStats)
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            ModuleIconBadge(module.id)
            Spacer(Modifier.height(12.dp))
            Text(
                text = module.title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = "${module.series.size} 系列",
                style = MaterialTheme.typography.labelMedium,
                color = visual.accent,
            )
            Text(
                text = "$articleCount 篇",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            ReadingProgressBar(
                readCount = readCount,
                totalCount = totalCount,
                showLabel = false,
            )
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = "进入",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
                Icon(
                    Icons.AutoMirrored.Filled.ArrowForward,
                    contentDescription = null,
                    modifier = Modifier.height(16.dp),
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}
