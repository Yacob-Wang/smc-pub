package com.stabilitymatrix.reader

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.Home
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.stabilitymatrix.reader.data.ThemeMode
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.ui.navigation.MainTab
import com.stabilitymatrix.reader.ui.navigation.NavCodec
import com.stabilitymatrix.reader.ui.navigation.Routes
import com.stabilitymatrix.reader.ui.screens.ArticleScreen
import com.stabilitymatrix.reader.ui.screens.BrowseScreen
import com.stabilitymatrix.reader.ui.screens.HomeScreen
import com.stabilitymatrix.reader.ui.screens.LibraryScreen
import com.stabilitymatrix.reader.ui.screens.ModuleScreen
import com.stabilitymatrix.reader.ui.screens.SearchScreen
import com.stabilitymatrix.reader.ui.screens.SeriesScreen
import com.stabilitymatrix.reader.ui.screens.SettingsSheet
import com.stabilitymatrix.reader.ui.theme.ReaderTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val app = application as ReaderApp

        setContent {
            val themeMode by app.preferencesStore.themeMode.collectAsState(initial = ThemeMode.SYSTEM)
            val fontScale by app.preferencesStore.fontScale.collectAsState(initial = 1f)
            val readingProgress by app.preferencesStore.readingProgress.collectAsState(initial = null)
            val bookmarks by app.preferencesStore.bookmarks.collectAsState(initial = emptySet())
            val readingStats by app.readingStatsStore.stats.collectAsState(initial = ReadingStats())

            val catalog = remember { app.catalogRepository.catalog }
            val navController = rememberNavController()
            val scope = rememberCoroutineScope()
            val navBackStackEntry by navController.currentBackStackEntryAsState()
            val currentRoute = navBackStackEntry?.destination?.route

            var searchResults by remember { mutableStateOf(emptyList<com.stabilitymatrix.reader.data.SearchResult>()) }
            var showSettings by remember { mutableStateOf(false) }

            val showBottomBar = currentRoute in Routes.mainTabs

            ReaderTheme(themeMode = themeMode) {
                SettingsSheet(
                    visible = showSettings,
                    themeMode = themeMode,
                    fontScale = fontScale,
                    onDismiss = { showSettings = false },
                    onThemeChange = { mode -> scope.launch { app.preferencesStore.setThemeMode(mode) } },
                    onFontScaleChange = { scale -> scope.launch { app.preferencesStore.setFontScale(scale) } },
                )

                Scaffold(
                    bottomBar = {
                        if (showBottomBar) {
                            NavigationBar {
                                MainTab.entries.forEach { tab ->
                                    NavigationBarItem(
                                        selected = currentRoute == tab.route,
                                        onClick = {
                                            navController.navigate(tab.route) {
                                                popUpTo(Routes.HOME) {
                                                    saveState = true
                                                }
                                                launchSingleTop = true
                                                restoreState = true
                                            }
                                        },
                                        icon = {
                                            Icon(
                                                when (tab) {
                                                    MainTab.Home -> Icons.Default.Home
                                                    MainTab.Browse -> Icons.AutoMirrored.Filled.MenuBook
                                                    MainTab.Library -> Icons.Default.Bookmark
                                                },
                                                contentDescription = tab.label,
                                            )
                                        },
                                        label = { Text(tab.label) },
                                    )
                                }
                            }
                        }
                    },
                ) { padding ->
                    NavHost(
                        navController = navController,
                        startDestination = Routes.HOME,
                        modifier = Modifier.padding(padding),
                    ) {
                        composable(Routes.HOME) {
                            HomeScreen(
                                catalog = catalog,
                                readingProgress = readingProgress,
                                readingStats = readingStats,
                                onOpenModule = { navController.navigate(Routes.module(it)) },
                                onOpenArticle = { navController.navigate(Routes.article(it)) },
                                onSearch = { navController.navigate(Routes.SEARCH) },
                            )
                        }

                        composable(Routes.BROWSE) {
                            BrowseScreen(
                                catalog = catalog,
                                readingStats = readingStats,
                                onOpenModule = { navController.navigate(Routes.module(it)) },
                                onSearch = { navController.navigate(Routes.SEARCH) },
                            )
                        }

                        composable(Routes.LIBRARY) {
                            LibraryScreen(
                                catalog = catalog,
                                catalogRepository = app.catalogRepository,
                                bookmarks = bookmarks,
                                readingProgress = readingProgress,
                                readingStats = readingStats,
                                onOpenArticle = { navController.navigate(Routes.article(it)) },
                                onOpenSettings = { showSettings = true },
                            )
                        }

                        composable(
                            route = Routes.MODULE,
                            arguments = listOf(navArgument("moduleId") { type = NavType.StringType }),
                        ) { entry ->
                            val moduleId = decodeNavArg(entry.arguments?.getString("moduleId").orEmpty())
                            val module = catalog.modules.firstOrNull { it.id == moduleId }
                            if (module != null) {
                                ModuleScreen(
                                    module = module,
                                    readingStats = readingStats,
                                    onBack = { navController.popBackStack() },
                                    onOpenSeries = { modId, seriesId ->
                                        navController.navigate(Routes.series(modId, seriesId))
                                    },
                                )
                            }
                        }

                        composable(
                            route = Routes.SERIES,
                            arguments = listOf(
                                navArgument("moduleId") { type = NavType.StringType },
                                navArgument("seriesId") { type = NavType.StringType },
                            ),
                        ) { entry ->
                            val moduleId = decodeNavArg(entry.arguments?.getString("moduleId").orEmpty())
                            val seriesId = decodeNavArg(entry.arguments?.getString("seriesId").orEmpty())
                            val module = catalog.modules.firstOrNull { it.id == moduleId }
                            val series = module?.series?.firstOrNull { it.id == seriesId }
                            if (series != null && module != null) {
                                SeriesScreen(
                                    series = series,
                                    moduleTitle = module.title,
                                    moduleId = moduleId,
                                    readingStats = readingStats,
                                    onBack = { navController.popBackStack() },
                                    onOpenArticle = { navController.navigate(Routes.article(it)) },
                                )
                            }
                        }

                        composable(
                            route = Routes.ARTICLE,
                            arguments = listOf(navArgument("articleId") { type = NavType.StringType }),
                        ) { entry ->
                            val articleId = decodeNavArg(entry.arguments?.getString("articleId").orEmpty())
                            val navInfo = app.catalogRepository.findArticle(articleId)
                            val markdown = remember(articleId) { app.articleRepository.loadMarkdown(articleId) }
                            val sections = remember(articleId) { app.articleRepository.loadSections(articleId) }

                            ArticleScreen(
                                articleId = articleId,
                                markdown = markdown,
                                navInfo = navInfo,
                                sections = sections,
                                fontScale = fontScale,
                                themeMode = themeMode,
                                isBookmarked = articleId in bookmarks,
                                onBack = { navController.popBackStack() },
                                onNavigateArticle = { target ->
                                    navController.navigate(Routes.article(target)) {
                                        popUpTo(Routes.HOME)
                                    }
                                },
                                onToggleBookmark = {
                                    scope.launch { app.preferencesStore.toggleBookmark(articleId) }
                                },
                                onOpenSettings = { showSettings = true },
                                onSaveProgress = { sectionIndex, offset ->
                                    lifecycleScope.launch {
                                        app.preferencesStore.saveReadingProgress(articleId, sectionIndex, offset)
                                    }
                                },
                                onAddReadingSeconds = { id, seconds ->
                                    app.readingStatsStore.addReadingTime(id, seconds)
                                },
                                linkResolver = { href ->
                                    app.linkMapRepository.resolve(href, articleId)
                                },
                            )
                        }

                        composable(Routes.SEARCH) {
                            SearchScreen(
                                results = searchResults,
                                onBack = { navController.popBackStack() },
                                onQueryChange = { query ->
                                    searchResults = if (query.length >= 2) {
                                        app.searchRepository.search(query)
                                    } else {
                                        emptyList()
                                    }
                                },
                                onOpenArticle = { path ->
                                    navController.navigate(Routes.article(path)) {
                                        popUpTo(Routes.HOME)
                                    }
                                },
                            )
                        }
                    }
                }
            }
        }
    }

    private fun decodeNavArg(value: String): String = NavCodec.decodeNavArg(value)
}
