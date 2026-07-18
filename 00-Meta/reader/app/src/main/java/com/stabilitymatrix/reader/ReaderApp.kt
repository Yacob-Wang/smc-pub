package com.stabilitymatrix.reader

import android.app.Application
import com.stabilitymatrix.reader.data.ArticleRepository
import com.stabilitymatrix.reader.data.CatalogRepository
import com.stabilitymatrix.reader.data.LinkMapRepository
import com.stabilitymatrix.reader.data.PreferencesStore
import com.stabilitymatrix.reader.data.ReadingStatsStore
import com.stabilitymatrix.reader.data.SearchRepository

class ReaderApp : Application() {
    lateinit var catalogRepository: CatalogRepository
        private set
    lateinit var articleRepository: ArticleRepository
        private set
    lateinit var linkMapRepository: LinkMapRepository
        private set
    lateinit var searchRepository: SearchRepository
        private set
    lateinit var preferencesStore: PreferencesStore
        private set
    lateinit var readingStatsStore: ReadingStatsStore
        private set

    override fun onCreate() {
        super.onCreate()
        catalogRepository = CatalogRepository(this)
        articleRepository = ArticleRepository(this)
        linkMapRepository = LinkMapRepository(this)
        searchRepository = SearchRepository(this)
        preferencesStore = PreferencesStore(this)
        readingStatsStore = ReadingStatsStore(this)
    }
}
