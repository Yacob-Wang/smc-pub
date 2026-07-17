package com.stabilitymatrix.reader.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
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
import com.stabilitymatrix.reader.ui.components.ReadingStatsCard
import com.stabilitymatrix.reader.ui.components.AccentListTile
import com.stabilitymatrix.reader.ui.components.HeroBanner
import com.stabilitymatrix.reader.ui.components.ModuleIconBadge
import com.stabilitymatrix.reader.ui.components.ReaderSearchBar
import com.stabilitymatrix.reader.ui.components.SectionHeader
import com.stabilitymatrix.reader.ui.components.moduleVisual

@Composable
fun HomeScreen(
    catalog: CatalogRoot,
    readingProgress: ReadingProgress?,
    readingStats: ReadingStats,
    onOpenModule: (String) -> Unit,
    onOpenArticle: (String) -> Unit,
    onSearch: () -> Unit,
) {
    val contentModules = catalog.modules.filter { it.id != "_root" }
    val seriesCount = contentModules.sumOf { it.series.size }
    val summary = ReadingStatsHelper.summarize(catalog, readingStats)
    val featured = listOf(
        "Android_Framework" to "Framework 进程 / ANR / Watchdog",
        "Linux_Kernel" to "Kernel 内存 / Binder / IO",
        "Runtime" to "ART / GC / Native Crash",
    )

    Scaffold(containerColor = MaterialTheme.colorScheme.surface) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            item {
                HeroBanner(
                    articleCount = catalog.articleCount,
                    seriesCount = seriesCount,
                )
            }

            item {
                ReaderSearchBar(
                    placeholder = "搜索 LMKD、Binder、ANR、OOM…",
                    onClick = onSearch,
                )
            }

            item {
                ReadingStatsCard(summary = summary)
            }

            readingProgress?.let { progress ->
                item {
                    SectionHeader("继续阅读", "从上次停下的地方接着看")
                }
                item {
                    AccentListTile(
                        title = progress.articleId.substringAfterLast('/'),
                        subtitle = progress.articleId.substringBeforeLast('/', progress.articleId),
                        leading = {
                            ModuleIconBadge(
                                moduleId = progress.articleId.substringBefore('/').ifBlank { "_root" },
                            )
                        },
                        trailing = {
                            Icon(
                                Icons.Default.PlayArrow,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        },
                        onClick = { onOpenArticle(progress.articleId) },
                    )
                }
            }

            item {
                SectionHeader("学习路径", "建议从路线图进入，再按模块深入")
            }
            item {
                AccentListTile(
                    title = "成长路线图 v4",
                    subtitle = "AOSP 17 + android17-6.18 基线 · 7 模块改进优化",
                    leading = { ModuleIconBadge("_root") },
                    trailing = {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowForward,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    },
                    onClick = { onOpenArticle("Stability_Architect_Roadmap_v4") },
                )
            }

            item {
                SectionHeader("热门模块", "横向浏览，点进模块看系列")
            }
            item {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(featured) { (moduleId, hint) ->
                        val module = contentModules.firstOrNull { it.id == moduleId } ?: return@items
                        QuickModuleChip(
                            module = module,
                            hint = hint,
                            onClick = { onOpenModule(moduleId) },
                        )
                    }
                }
            }

            item {
                SectionHeader("最近更新模块", "完整目录请切到底部「目录」")
            }
            items(contentModules.take(4)) { module ->
                AccentListTile(
                    title = module.title,
                    subtitle = "${module.series.size} 系列 · ${module.series.sumOf { it.articles.size }} 篇",
                    leading = { ModuleIconBadge(module.id) },
                    trailing = {
                        Icon(
                            Icons.AutoMirrored.Filled.ArrowForward,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    },
                    onClick = { onOpenModule(module.id) },
                )
            }
        }
    }
}

@Composable
private fun QuickModuleChip(
    module: CatalogModule,
    hint: String,
    onClick: () -> Unit,
) {
    val visual = moduleVisual(module.id)
    Column(modifier = Modifier.width(260.dp)) {
        AccentListTile(
            title = visual.shortLabel,
            subtitle = hint,
            leading = { ModuleIconBadge(module.id) },
            onClick = onClick,
        )
    }
}
