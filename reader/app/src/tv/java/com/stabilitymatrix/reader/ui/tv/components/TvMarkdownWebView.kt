package com.stabilitymatrix.reader.ui.tv.components

import android.annotation.SuppressLint
import android.graphics.Color
import android.view.KeyEvent
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.viewinterop.AndroidView
import com.stabilitymatrix.reader.markdown.MarkdownHtmlRenderer

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun TvMarkdownWebView(
    markdown: String,
    darkTheme: Boolean,
    modifier: Modifier = Modifier,
    fontScale: Float = 1.25f,
    scrollAnchorId: String? = null,
    onLinkClick: (String) -> Unit = {},
    linkResolver: (String) -> String? = { null },
    onScrollChanged: (Int) -> Unit = {},
    onWebViewReady: (WebView) -> Unit = {},
) {
    val html = remember(markdown, darkTheme, fontScale, linkResolver) {
        val processed = MarkdownHtmlRenderer.preprocessLinks(markdown, linkResolver)
        MarkdownHtmlRenderer.renderDocument(processed, darkTheme)
            .replace("font-size: 15px;", "font-size: ${(18 * fontScale).toInt()}px;")
    }
    var webViewRef by remember { mutableStateOf<WebView?>(null) }
    val focusRequester = remember { FocusRequester() }

    key(html, scrollAnchorId) {
        AndroidView(
            modifier = modifier
                .focusRequester(focusRequester)
                .onFocusChanged { state ->
                    if (state.isFocused) webViewRef?.requestFocus()
                }
                .onKeyEvent { event ->
                    if (event.type != KeyEventType.KeyDown) return@onKeyEvent false
                    val webView = webViewRef ?: return@onKeyEvent false
                    when (event.key) {
                        Key.DirectionDown -> {
                            webView.scrollBy(0, 140)
                            onScrollChanged(webView.scrollY)
                            true
                        }
                        Key.DirectionUp -> {
                            webView.scrollBy(0, -140)
                            onScrollChanged(webView.scrollY)
                            true
                        }
                        Key.PageDown -> {
                            webView.pageDown(true)
                            onScrollChanged(webView.scrollY)
                            true
                        }
                        Key.PageUp -> {
                            webView.pageUp(true)
                            onScrollChanged(webView.scrollY)
                            true
                        }
                        else -> false
                    }
                },
            factory = { context ->
                WebView(context).apply {
                    isFocusable = true
                    isFocusableInTouchMode = true
                    setBackgroundColor(Color.TRANSPARENT)
                    settings.apply {
                        javaScriptEnabled = true
                        domStorageEnabled = false
                        builtInZoomControls = false
                    }
                    isVerticalScrollBarEnabled = true
                    webViewClient = object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(
                            view: WebView?,
                            request: WebResourceRequest?,
                        ): Boolean {
                            val url = request?.url?.toString() ?: return false
                            onLinkClick(url)
                            return true
                        }
                    }
                    setOnKeyListener { v, keyCode, event ->
                        if (event.action != KeyEvent.ACTION_DOWN) return@setOnKeyListener false
                        when (keyCode) {
                            KeyEvent.KEYCODE_DPAD_DOWN -> {
                                v.scrollBy(0, 140)
                                onScrollChanged((v as WebView).scrollY)
                                true
                            }
                            KeyEvent.KEYCODE_DPAD_UP -> {
                                v.scrollBy(0, -140)
                                onScrollChanged((v as WebView).scrollY)
                                true
                            }
                            KeyEvent.KEYCODE_PAGE_DOWN, KeyEvent.KEYCODE_CHANNEL_DOWN -> {
                                (v as WebView).pageDown(true)
                                onScrollChanged(v.scrollY)
                                true
                            }
                            KeyEvent.KEYCODE_PAGE_UP, KeyEvent.KEYCODE_CHANNEL_UP -> {
                                (v as WebView).pageUp(true)
                                onScrollChanged(v.scrollY)
                                true
                            }
                            else -> false
                        }
                    }
                    loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
                    scrollAnchorId?.let { anchor ->
                        post { loadUrl("javascript:document.getElementById('$anchor')?.scrollIntoView();") }
                    }
                    webViewRef = this
                    onWebViewReady(this)
                }
            },
            update = { webView ->
                webViewRef = webView
                onWebViewReady(webView)
            },
        )
    }
}
