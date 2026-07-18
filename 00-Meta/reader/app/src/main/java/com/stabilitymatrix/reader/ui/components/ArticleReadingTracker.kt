package com.stabilitymatrix.reader.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import kotlinx.coroutines.launch

/**
 * 在文章页可见时累计阅读时长；离开页面时 flush 剩余秒数。
 */
@Composable
fun ArticleReadingTracker(
    articleId: String,
    onAddSeconds: suspend (String, Int) -> Unit,
) {
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()

    DisposableEffect(articleId, lifecycleOwner) {
        var sessionStartMs = 0L
        var isActive = false

        fun flush() {
            if (!isActive || sessionStartMs <= 0L) return
            val elapsed = ((System.currentTimeMillis() - sessionStartMs) / 1000L).toInt()
            sessionStartMs = System.currentTimeMillis()
            if (elapsed > 0) {
                scope.launch { onAddSeconds(articleId, elapsed) }
            }
        }

        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> {
                    isActive = true
                    sessionStartMs = System.currentTimeMillis()
                }
                Lifecycle.Event.ON_PAUSE -> {
                    flush()
                    isActive = false
                }
                else -> Unit
            }
        }

        lifecycleOwner.lifecycle.addObserver(observer)
        if (lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) {
            isActive = true
            sessionStartMs = System.currentTimeMillis()
        }

        onDispose {
            flush()
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }
}
