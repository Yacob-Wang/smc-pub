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
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.BookmarkBorder
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.ArticleReadState
import com.stabilitymatrix.reader.data.CatalogRepository
import com.stabilitymatrix.reader.data.CatalogRoot
import com.stabilitymatrix.reader.data.ReadingProgress
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ReadingStatsHelper
import com.stabilitymatrix.reader.data.formatReadingDuration
import com.stabilitymatrix.reader.ui.components.AccentListTile
import com.stabilitymatrix.reader.ui.components.ModuleIconBadge
import com.stabilitymatrix.reader.ui.components.ReadStatusIcon
import com.stabilitymatrix.reader.ui.components.ReadingStatsCard
import com.stabilitymatrix.reader.ui.components.SectionHeader
import com.stabilitymatrix.reader.ui.components.readStatusLabel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LibraryScreen(
    catalog: CatalogRoot,
    catalogRepository: CatalogRepository,
    bookmarks: Set<String>,
    readingProgress: ReadingProgress?,
    readingStats: ReadingStats,
    onOpenArticle: (String) -> Unit,
    onOpenSettings: () -> Unit,
) {
    val summary = remember(catalog, readingStats) {
        ReadingStatsHelper.summarize(catalog, readingStats)
    }
    val bookmarkItems = bookmarks
        .mapNotNull { id -> catalogRepository.findArticle(id)?.let { info -> id to info.article.title } }
        .sortedBy { it.second }
    val inProgressItems = remember(catalog, readingStats) {
        ReadingStatsHelper.allArticleIds(catalog)
            .filter { readingStats.stateFor(it) == ArticleReadState.IN_PROGRESS }
            .sortedByDescending { readingStats.secondsFor(it) }
            .take(20)
            .mapNotNull { id ->
                catalogRepository.findArticle(id)?.let { info ->
                    Triple(id, info.article.title, readingStats.secondsFor(id))
                }
            }
    }

    Scaffold(
        containerColor = MaterialTheme.colorScheme.surface,
        topBar = {
            TopAppBar(
                title = { Text("我的书架") },
                actions = {
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "设置")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
            contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                ReadingStatsCard(summary = summary)
            }

            item {
                SectionHeader("继续阅读", "上次打开的文章")
            }
            if (readingProgress != null) {
                item(key = "continue_${readingProgress.articleId}") {
                    AccentListTile(
                        title = readingProgress.articleId.substringAfterLast('/'),
                        subtitle = "滚动位置已保存",
                        leading = {
                            ModuleIconBadge(
                                moduleId = readingProgress.articleId.substringBefore('/').ifBlank { "_root" },
                            )
                        },
                        trailing = {
                            ReadStatusIcon(readingStats.stateFor(readingProgress.articleId))
                        },
                        onClick = { onOpenArticle(readingProgress.articleId) },
                    )
                }
            } else {
                item { EmptyHint(text = "还没有阅读记录，去首页或目录选一篇开始吧") }
            }

            item {
                Spacer(Modifier.height(4.dp))
                SectionHeader("在读中", "累计不足 45 秒，尚未标记为已读")
            }
            if (inProgressItems.isEmpty()) {
                item { EmptyHint(text = "暂无进行中的文章") }
            } else {
                items(inProgressItems, key = { "in_progress_${it.first}" }) { (id, title, seconds) ->
                    AccentListTile(
                        title = title,
                        subtitle = "${readStatusLabel(ArticleReadState.IN_PROGRESS)} · 已读 ${formatReadingDuration(seconds)}",
                        leading = {
                            ModuleIconBadge(moduleId = id.substringBefore('/').ifBlank { "_root" })
                        },
                        trailing = { ReadStatusIcon(ArticleReadState.IN_PROGRESS) },
                        onClick = { onOpenArticle(id) },
                    )
                }
            }

            item {
                Spacer(Modifier.height(4.dp))
                SectionHeader("书签", "${bookmarkItems.size} 篇已收藏")
            }
            if (bookmarkItems.isEmpty()) {
                item { EmptyHint(text = "阅读文章时点击书签图标即可收藏") }
            } else {
                items(bookmarkItems, key = { "bookmark_${it.first}" }) { (id, title) ->
                    AccentListTile(
                        title = title,
                        subtitle = readStatusLabel(readingStats.stateFor(id)),
                        leading = {
                            ModuleIconBadge(moduleId = id.substringBefore('/').ifBlank { "_root" })
                        },
                        trailing = {
                            Icon(
                                Icons.Default.Bookmark,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        },
                        onClick = { onOpenArticle(id) },
                    )
                }
            }
        }
    }
}

@Composable
private fun EmptyHint(text: String) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
    ) {
        Icon(
            Icons.Default.BookmarkBorder,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
