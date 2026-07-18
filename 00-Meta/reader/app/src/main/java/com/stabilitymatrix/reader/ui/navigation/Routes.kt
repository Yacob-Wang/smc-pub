package com.stabilitymatrix.reader.ui.navigation

object Routes {
    const val HOME = "home"
    const val BROWSE = "browse"
    const val LIBRARY = "library"
    const val MODULE = "module/{moduleId}"
    const val SERIES = "series/{moduleId}/{seriesId}"
    const val ARTICLE = "article/{articleId}"
    const val SEARCH = "search"
    const val SETTINGS = "settings"

    val mainTabs = setOf(HOME, BROWSE, LIBRARY)

    fun module(moduleId: String): String = "module/${NavCodec.encode(moduleId)}"

    fun series(moduleId: String, seriesId: String): String {
        return "series/${NavCodec.encode(moduleId)}/${NavCodec.encode(seriesId)}"
    }

    fun article(articleId: String): String {
        return "article/${NavCodec.encode(articleId)}"
    }
}

enum class MainTab(val route: String, val label: String) {
    Home(Routes.HOME, "首页"),
    Browse(Routes.BROWSE, "目录"),
    Library(Routes.LIBRARY, "书架"),
    ;

    companion object {
        fun fromRoute(route: String?): MainTab? =
            entries.firstOrNull { it.route == route?.substringBefore("?") }
    }
}
