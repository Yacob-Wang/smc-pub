package com.stabilitymatrix.reader

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.lifecycle.lifecycleScope
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.stabilitymatrix.reader.data.ReadingStats
import com.stabilitymatrix.reader.data.ThemeMode
import com.stabilitymatrix.reader.ui.navigation.NavCodec
import com.stabilitymatrix.reader.ui.navigation.Routes
import com.stabilitymatrix.reader.ui.theme.ReaderTheme
import com.stabilitymatrix.reader.ui.tv.TvHintBar
import com.stabilitymatrix.reader.ui.tv.TvTab
import com.stabilitymatrix.reader.ui.tv.TvTopTabs
import com.stabilitymatrix.reader.ui.tv.screens.TvArticleScreen
import com.stabilitymatrix.reader.ui.tv.screens.TvBrowseScreen
import com.stabilitymatrix.reader.ui.tv.screens.TvHomeScreen
import com.stabilitymatrix.reader.ui.tv.screens.TvLibraryScreen
import com.stabilitymatrix.reader.ui.tv.screens.TvModuleScreen
import com.stabilitymatrix.reader.ui.tv.screens.TvSeriesScreen
import com.stabilitymatrix.reader.ui.tv.screens.TvSettingsScreen
import kotlinx.coroutines.launch

class TvMainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val app = application as ReaderApp

        setContent {
            val themeMode by app.preferencesStore.themeMode.collectAsState(initial = ThemeMode.DARK)
            val fontScale by app.preferencesStore.fontScale.collectAsState(initial = 1.25f)
            val readingProgress by app.preferencesStore.readingProgress.collectAsState(initial = null)
            val bookmarks by app.preferencesStore.bookmarks.collectAsState(initial = emptySet())
            val readingStats by app.readingStatsStore.stats.collectAsState(initial = ReadingStats())

            val catalog = remember { app.catalogRepository.catalog }
            val navController = rememberNavController()
            val scope = rememberCoroutineScope()
            val navBackStackEntry by navController.currentBackStackEntryAsState()
            val currentRoute = navBackStackEntry?.destination?.route?.substringBefore("/{")
            val showMainChrome = currentRoute in TvTab.mainRoutes

            BackHandler(enabled = !showMainChrome) {
                navController.popBackStack()
            }

            ReaderTheme(themeMode = ThemeMode.DARK) {
                Column(Modifier.fillMaxSize()) {
                    if (showMainChrome) {
                        val selectedTab = TvTab.entries.firstOrNull { it.route == currentRoute } ?: TvTab.Home
                        TvTopTabs(
                            selected = selectedTab,
                            onSelect = { tab ->
                                navController.navigate(tab.route) {
                                    popUpTo(TvTab.Home.route) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                        )
                    }
                    NavHost(
                        navController = navController,
                        startDestination = TvTab.Home.route,
                        modifier = Modifier.weight(1f),
                    ) {
                        composable(TvTab.Home.route) {
                            TvHomeScreen(
                                catalog = catalog,
                                readingProgress = readingProgress,
                                readingStats = readingStats,
                                onOpenModule = { navController.navigate(Routes.module(it)) },
                                onOpenArticle = { navController.navigate(Routes.article(it)) },
                            )
                        }
                        composable(TvTab.Browse.route) {
                            TvBrowseScreen(
                                catalog = catalog,
                                readingStats = readingStats,
                                onOpenModule = { navController.navigate(Routes.module(it)) },
                            )
                        }
                        composable(TvTab.Library.route) {
                            TvLibraryScreen(
                                catalog = catalog,
                                catalogRepository = app.catalogRepository,
                                readingProgress = readingProgress,
                                readingStats = readingStats,
                                onOpenArticle = { navController.navigate(Routes.article(it)) },
                            )
                        }
                        composable(TvTab.Settings.route) {
                            TvSettingsScreen(
                                fontScale = fontScale,
                                onFontScaleChange = { scale ->
                                    scope.launch { app.preferencesStore.setFontScale(scale) }
                                },
                            )
                        }
                        composable(
                            route = Routes.MODULE,
                            arguments = listOf(navArgument("moduleId") { type = NavType.StringType }),
                        ) { entry ->
                            val moduleId = NavCodec.decodeNavArg(entry.arguments?.getString("moduleId").orEmpty())
                            catalog.modules.firstOrNull { it.id == moduleId }?.let { module ->
                                TvModuleScreen(
                                    module = module,
                                    readingStats = readingStats,
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
                            val moduleId = NavCodec.decodeNavArg(entry.arguments?.getString("moduleId").orEmpty())
                            val seriesId = NavCodec.decodeNavArg(entry.arguments?.getString("seriesId").orEmpty())
                            val module = catalog.modules.firstOrNull { it.id == moduleId }
                            val series = module?.series?.firstOrNull { it.id == seriesId }
                            if (series != null && module != null) {
                                TvSeriesScreen(
                                    series = series,
                                    moduleTitle = module.title,
                                    moduleId = moduleId,
                                    readingStats = readingStats,
                                    onOpenArticle = { navController.navigate(Routes.article(it)) },
                                )
                            }
                        }
                        composable(
                            route = Routes.ARTICLE,
                            arguments = listOf(navArgument("articleId") { type = NavType.StringType }),
                        ) { entry ->
                            val articleId = NavCodec.decodeNavArg(entry.arguments?.getString("articleId").orEmpty())
                            val navInfo = app.catalogRepository.findArticle(articleId)
                            val markdown = remember(articleId) { app.articleRepository.loadMarkdown(articleId) }
                            val sections = remember(articleId) { app.articleRepository.loadSections(articleId) }

                            TvArticleScreen(
                                articleId = articleId,
                                markdown = markdown,
                                navInfo = navInfo,
                                sections = sections,
                                fontScale = fontScale,
                                isBookmarked = articleId in bookmarks,
                                onBack = { navController.popBackStack() },
                                onNavigateArticle = { target ->
                                    navController.navigate(Routes.article(target))
                                },
                                onToggleBookmark = {
                                    scope.launch { app.preferencesStore.toggleBookmark(articleId) }
                                },
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
                    }
                    if (showMainChrome) {
                        TvHintBar()
                    }
                }
            }
        }
    }
}
