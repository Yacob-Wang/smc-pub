package com.stabilitymatrix.reader.ui.screens

import android.widget.Toast
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.BookmarkBorder
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.ArticleNavInfo
import com.stabilitymatrix.reader.data.ThemeMode
import com.stabilitymatrix.reader.markdown.MarkdownSection
import com.stabilitymatrix.reader.ui.components.ArticleReadingTracker
import com.stabilitymatrix.reader.ui.components.MarkdownWebView

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ArticleScreen(
    articleId: String,
    markdown: String?,
    navInfo: ArticleNavInfo?,
    sections: List<MarkdownSection>,
    fontScale: Float,
    themeMode: ThemeMode,
    isBookmarked: Boolean,
    onBack: () -> Unit,
    onNavigateArticle: (String) -> Unit,
    onToggleBookmark: () -> Unit,
    onOpenSettings: () -> Unit,
    onSaveProgress: (Int, Int) -> Unit,
    onAddReadingSeconds: suspend (String, Int) -> Unit,
    linkResolver: (String) -> String?,
) {
    ArticleReadingTracker(
        articleId = articleId,
        onAddSeconds = onAddReadingSeconds,
    )

    val context = LocalContext.current
    var showToc by remember { mutableStateOf(false) }
    var scrollAnchorId by remember { mutableStateOf<String?>(null) }
    var scrollTick by remember { mutableIntStateOf(0) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val isWide = LocalConfiguration.current.screenWidthDp >= 840
    val darkTheme = when (themeMode) {
        ThemeMode.DARK -> true
        ThemeMode.LIGHT -> false
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
    }

    fun navigateInternalLink(target: String) {
        val resolved = linkResolver(target) ?: target
        if (resolved.isNotBlank()) {
            onNavigateArticle(resolved)
        } else {
            Toast.makeText(context, "文章未收录", Toast.LENGTH_SHORT).show()
        }
    }

    fun jumpToSection(section: MarkdownSection) {
        scrollAnchorId = section.id
        scrollTick++
        showToc = false
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            navInfo?.article?.title ?: articleId.substringAfterLast('/'),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        navInfo?.let {
                            Text(
                                "${it.moduleTitle} · ${it.seriesTitle}",
                                style = MaterialTheme.typography.labelSmall,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "返回")
                    }
                },
                actions = {
                    IconButton(onClick = onToggleBookmark) {
                        Icon(
                            if (isBookmarked) Icons.Default.Bookmark else Icons.Default.BookmarkBorder,
                            contentDescription = "书签",
                        )
                    }
                    IconButton(onClick = { showToc = true }) {
                        Icon(Icons.AutoMirrored.Filled.List, contentDescription = "目录")
                    }
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Default.Settings, contentDescription = "设置")
                    }
                },
            )
        },
        bottomBar = {
            navInfo?.article?.let { article ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 8.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                ) {
                    TextButton(
                        onClick = { article.prevId?.let(onNavigateArticle) },
                        enabled = article.prevId != null,
                    ) { Text("上一篇") }
                    TextButton(
                        onClick = { article.nextId?.let(onNavigateArticle) },
                        enabled = article.nextId != null,
                    ) { Text("下一篇") }
                }
            }
        },
    ) { padding ->
        when {
            markdown.isNullOrBlank() -> {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding)
                        .padding(24.dp),
                ) {
                    Text("无法加载文章内容", style = MaterialTheme.typography.titleMedium)
                    Text(
                        articleId,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
            }
            isWide -> {
                Row(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                ) {
                    LazyColumn(
                        modifier = Modifier
                            .fillMaxHeight()
                            .weight(0.3f)
                            .padding(8.dp),
                    ) {
                        items(sections) { section ->
                            Text(
                                text = section.title,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { jumpToSection(section) }
                                    .padding(
                                        start = ((section.level - 1).coerceAtLeast(0) * 12).dp,
                                        top = 6.dp,
                                        bottom = 6.dp,
                                        end = 8.dp,
                                    ),
                                style = when (section.level) {
                                    1 -> MaterialTheme.typography.titleSmall
                                    2 -> MaterialTheme.typography.bodyMedium
                                    else -> MaterialTheme.typography.bodySmall
                                },
                                fontWeight = if (section.level <= 2) FontWeight.Medium else FontWeight.Normal,
                            )
                        }
                    }
                    MarkdownWebView(
                        markdown = markdown,
                        darkTheme = darkTheme,
                        fontScale = fontScale,
                        scrollAnchorId = if (scrollTick > 0) scrollAnchorId else null,
                        modifier = Modifier
                            .weight(0.7f)
                            .fillMaxHeight(),
                        linkResolver = linkResolver,
                        onLinkClick = ::navigateInternalLink,
                        onScrollChanged = { scrollY -> onSaveProgress(0, scrollY) },
                    )
                }
            }
            else -> {
                MarkdownWebView(
                    markdown = markdown,
                    darkTheme = darkTheme,
                    fontScale = fontScale,
                    scrollAnchorId = if (scrollTick > 0) scrollAnchorId else null,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(padding),
                    linkResolver = linkResolver,
                    onLinkClick = ::navigateInternalLink,
                    onScrollChanged = { scrollY -> onSaveProgress(0, scrollY) },
                )
            }
        }
    }

    if (showToc) {
        ModalBottomSheet(
            onDismissRequest = { showToc = false },
            sheetState = sheetState,
        ) {
            LazyColumn(modifier = Modifier.padding(bottom = 32.dp)) {
                items(sections) { section ->
                    Text(
                        text = section.title,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { jumpToSection(section) }
                            .padding(
                                start = (16 + (section.level - 1).coerceAtLeast(0) * 12).dp,
                                end = 16.dp,
                                top = 8.dp,
                                bottom = 8.dp,
                            ),
                        style = when (section.level) {
                            1 -> MaterialTheme.typography.titleMedium
                            2 -> MaterialTheme.typography.bodyLarge
                            else -> MaterialTheme.typography.bodyMedium
                        },
                    )
                }
            }
        }
    }
}
