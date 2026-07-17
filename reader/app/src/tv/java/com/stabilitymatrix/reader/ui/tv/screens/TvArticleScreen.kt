package com.stabilitymatrix.reader.ui.tv.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.ArticleNavInfo
import com.stabilitymatrix.reader.markdown.MarkdownSection
import com.stabilitymatrix.reader.ui.components.ArticleReadingTracker
import com.stabilitymatrix.reader.ui.tv.TvFocusableChip
import com.stabilitymatrix.reader.ui.tv.TvFocusableSurface
import com.stabilitymatrix.reader.ui.tv.TvHintBar
import com.stabilitymatrix.reader.ui.tv.components.TvMarkdownWebView

@Composable
fun TvArticleScreen(
    articleId: String,
    markdown: String?,
    navInfo: ArticleNavInfo?,
    sections: List<MarkdownSection>,
    fontScale: Float,
    isBookmarked: Boolean,
    onBack: () -> Unit,
    onNavigateArticle: (String) -> Unit,
    onToggleBookmark: () -> Unit,
    onSaveProgress: (Int, Int) -> Unit,
    onAddReadingSeconds: suspend (String, Int) -> Unit,
    linkResolver: (String) -> String?,
) {
    ArticleReadingTracker(articleId = articleId, onAddSeconds = onAddReadingSeconds)

    var scrollAnchorId by remember { mutableStateOf<String?>(null) }
    var scrollTick by remember { mutableIntStateOf(0) }

    Column(Modifier.fillMaxSize()) {
        Text(
            text = navInfo?.article?.title ?: articleId.substringAfterLast('/'),
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.Bold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.padding(horizontal = 48.dp, vertical = 12.dp),
        )
        if (markdown.isNullOrBlank()) {
            Text(
                "无法加载文章内容",
                modifier = Modifier.padding(48.dp),
                style = MaterialTheme.typography.titleMedium,
            )
        } else {
            Row(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .padding(horizontal = 48.dp),
            ) {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxHeight()
                        .weight(0.28f)
                        .padding(end = 12.dp),
                ) {
                    items(sections, key = { it.id }) { section ->
                        TvFocusableSurface(
                            onClick = {
                                scrollAnchorId = section.id
                                scrollTick++
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            selected = false,
                        ) {
                            Text(
                                text = section.title,
                                modifier = Modifier.padding(
                                    start = ((section.level - 1).coerceAtLeast(0) * 8 + 12).dp,
                                    top = 8.dp,
                                    bottom = 8.dp,
                                    end = 8.dp,
                                ),
                                style = MaterialTheme.typography.bodyLarge,
                            )
                        }
                    }
                }
                TvMarkdownWebView(
                    markdown = markdown,
                    darkTheme = true,
                    fontScale = fontScale.coerceAtLeast(1.15f),
                    scrollAnchorId = if (scrollTick > 0) scrollAnchorId else null,
                    modifier = Modifier
                        .weight(0.72f)
                        .fillMaxHeight(),
                    linkResolver = linkResolver,
                    onLinkClick = { href ->
                        linkResolver(href)?.let(onNavigateArticle)
                    },
                    onScrollChanged = { scrollY -> onSaveProgress(0, scrollY) },
                )
            }
        }
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 48.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            TvFocusableChip(
                label = "← 上一篇",
                selected = false,
                onClick = { navInfo?.article?.prevId?.let(onNavigateArticle) },
                modifier = Modifier,
            )
            TvFocusableChip(
                label = if (isBookmarked) "★ 已收藏" else "☆ 收藏",
                selected = isBookmarked,
                onClick = onToggleBookmark,
            )
            TvFocusableChip(
                label = "返回列表",
                selected = false,
                onClick = onBack,
            )
            TvFocusableChip(
                label = "下一篇 →",
                selected = false,
                onClick = { navInfo?.article?.nextId?.let(onNavigateArticle) },
            )
        }
        TvHintBar(text = "↑↓ 滚动正文   OK 选章节/按钮   返回 上一级")
    }
}
