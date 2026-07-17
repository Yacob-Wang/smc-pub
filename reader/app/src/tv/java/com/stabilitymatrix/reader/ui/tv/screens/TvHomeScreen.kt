package com.stabilitymatrix.reader.ui.tv.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.CatalogModule
import com.stabilitymatrix.reader.data.CatalogRoot
import com.stabilitymatrix.reader.data.ReadingProgress
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ReadingStatsHelper
import com.stabilitymatrix.reader.ui.components.ModuleIconBadge
import com.stabilitymatrix.reader.ui.components.ReadingStatsCard
import com.stabilitymatrix.reader.ui.components.moduleVisual
import com.stabilitymatrix.reader.ui.tv.TvFocusableSurface

@Composable
fun TvHomeScreen(
    catalog: CatalogRoot,
    readingProgress: ReadingProgress?,
    readingStats: ReadingStats,
    onOpenModule: (String) -> Unit,
    onOpenArticle: (String) -> Unit,
) {
    val modules = catalog.modules.filter { it.id != "_root" }
    val summary = ReadingStatsHelper.summarize(catalog, readingStats)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 48.dp),
    ) {
        ReadingStatsCard(summary = summary, modifier = Modifier.padding(bottom = 16.dp))

        if (readingProgress != null) {
            TvFocusableSurface(
                onClick = { onOpenArticle(readingProgress.articleId) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp),
            ) {
                Column(Modifier.padding(20.dp)) {
                    Text("继续阅读", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(
                        readingProgress.articleId.substringAfterLast('/'),
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        TvFocusableSurface(
            onClick = { onOpenArticle("Stability_Architect_Roadmap_v4") },
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 20.dp),
        ) {
            Column(Modifier.padding(20.dp)) {
                Text("成长路线图 v4", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                Text("AOSP 17 + android17-6.18 基线", style = MaterialTheme.typography.bodyLarge)
            }
        }

        Text(
            "知识模块",
            style = MaterialTheme.typography.headlineSmall,
            modifier = Modifier.padding(bottom = 12.dp),
        )
        LazyVerticalGrid(
            columns = GridCells.Adaptive(minSize = 220.dp),
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 24.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            items(modules, key = { it.id }) { module ->
                TvModuleCard(module = module, readingStats = readingStats, onClick = { onOpenModule(module.id) })
            }
        }
    }
}

@Composable
private fun TvModuleCard(
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
                "已读 $read / $total 篇",
                style = MaterialTheme.typography.bodyLarge,
                color = visual.accent,
                modifier = Modifier.padding(top = 4.dp),
            )
        }
    }
}
