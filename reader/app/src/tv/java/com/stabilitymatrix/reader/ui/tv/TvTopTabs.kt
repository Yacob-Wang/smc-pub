package com.stabilitymatrix.reader.ui.tv

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

enum class TvTab(val route: String, val label: String) {
    Home("home", "继续阅读"),
    Browse("browse", "知识目录"),
    Library("library", "我的书架"),
    Settings("settings", "设置"),
    ;

    companion object {
        val mainRoutes = setOf(Home.route, Browse.route, Library.route, Settings.route)
    }
}

@Composable
fun TvTopTabs(
    selected: TvTab,
    onSelect: (TvTab) -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 48.dp, vertical = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        TvTab.entries.forEach { tab ->
            TvFocusableChip(
                label = tab.label,
                selected = tab == selected,
                onClick = { onSelect(tab) },
            )
        }
    }
}
