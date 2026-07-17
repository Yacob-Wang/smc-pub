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
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
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
import com.stabilitymatrix.reader.data.CatalogModule
import com.stabilitymatrix.reader.data.CatalogRoot
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ReadingStatsHelper
import com.stabilitymatrix.reader.ui.components.ModuleIconBadge
import com.stabilitymatrix.reader.ui.components.moduleVisual
import com.stabilitymatrix.reader.ui.tv.TvFocusableChip
import com.stabilitymatrix.reader.ui.tv.TvFocusableSurface

private enum class TvBrowseFilter(val label: String) {
    All("全部"),
    Kernel("Kernel"),
    Runtime("Runtime"),
    Framework("Framework"),
    Other("其他"),
}

@Composable
fun TvBrowseScreen(
    catalog: CatalogRoot,
    readingStats: ReadingStats,
    onOpenModule: (String) -> Unit,
) {
    var filter by remember { mutableStateOf(TvBrowseFilter.All) }
    val modules = remember(catalog, filter) {
        val all = catalog.modules.filter { it.id != "_root" }
        when (filter) {
            TvBrowseFilter.All -> all
            TvBrowseFilter.Kernel -> all.filter { it.id == "Linux_Kernel" }
            TvBrowseFilter.Runtime -> all.filter { it.id == "Runtime" }
            TvBrowseFilter.Framework -> all.filter { it.id == "Android_Framework" }
            TvBrowseFilter.Other -> all.filter {
                it.id !in setOf("Linux_Kernel", "Runtime", "Android_Framework")
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 48.dp),
    ) {
        Text("知识目录", style = MaterialTheme.typography.headlineSmall)
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            TvBrowseFilter.entries.forEach { item ->
                TvFocusableChip(
                    label = item.label,
                    selected = filter == item,
                    onClick = { filter = item },
                )
            }
        }
        Spacer(Modifier.height(16.dp))
        LazyVerticalGrid(
            columns = GridCells.Adaptive(minSize = 220.dp),
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 24.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            items(modules, key = { it.id }) { module ->
                TvBrowseModuleCard(module, readingStats, onClick = { onOpenModule(module.id) })
            }
        }
    }
}

@Composable
private fun TvBrowseModuleCard(
    module: CatalogModule,
    readingStats: ReadingStats,
    onClick: () -> Unit,
) {
    val visual = moduleVisual(module.id)
    val (read, _, total) = ReadingStatsHelper.moduleSummary(module, readingStats)
    TvFocusableSurface(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(18.dp)) {
            ModuleIconBadge(module.id)
            Text(
                module.title,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 12.dp),
            )
            Text(
                "${module.series.size} 系列 · 已读 $read/$total",
                style = MaterialTheme.typography.bodyLarge,
                color = visual.accent,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}
