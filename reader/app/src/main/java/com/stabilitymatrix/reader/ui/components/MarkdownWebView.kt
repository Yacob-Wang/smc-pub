package com.stabilitymatrix.reader.ui.components

import android.annotation.SuppressLint
import android.graphics.Color
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.runtime.Composable
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import com.stabilitymatrix.reader.markdown.MarkdownHtmlRenderer

@SuppressLint("SetJavaScriptEnabled")
@Composable
fun MarkdownWebView(
    markdown: String,
    darkTheme: Boolean,
    modifier: Modifier = Modifier,
    scrollAnchorId: String? = null,
    fontScale: Float = 1f,
    onLinkClick: (String) -> Unit = {},
    linkResolver: (String) -> String? = { null },
    onScrollChanged: (Int) -> Unit = {},
) {
    val html = remember(markdown, darkTheme, fontScale, linkResolver) {
        val processed = MarkdownHtmlRenderer.preprocessLinks(markdown, linkResolver)
        MarkdownHtmlRenderer.renderDocument(processed, darkTheme)
            .replace("font-size: 15px;", "font-size: ${(15 * fontScale).toInt()}px;")
    }

    key(html, scrollAnchorId) {
        AndroidView(
            modifier = modifier,
            factory = { context ->
                WebView(context).apply {
                    setBackgroundColor(Color.TRANSPARENT)
                    settings.apply {
                        javaScriptEnabled = true
                        domStorageEnabled = false
                        builtInZoomControls = true
                        displayZoomControls = false
                        textZoom = (100 * fontScale).toInt().coerceIn(85, 145)
                    }
                    isVerticalScrollBarEnabled = true
                    webViewClient = object : WebViewClient() {
                        override fun shouldOverrideUrlLoading(
                            view: WebView?,
                            request: WebResourceRequest?,
                        ): Boolean {
                            val url = request?.url?.toString() ?: return false
                            if (url.startsWith("smr://article/")) {
                                onLinkClick(url.removePrefix("smr://article/"))
                                return true
                            }
                            return false
                        }

                        @Deprecated("Deprecated in API 24")
                        override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                            if (url != null && url.startsWith("smr://article/")) {
                                onLinkClick(url.removePrefix("smr://article/"))
                                return true
                            }
                            return false
                        }
                    }
                    setOnScrollChangeListener { _, _, scrollY, _, _ ->
                        onScrollChanged(scrollY)
                    }
                }
            },
            update = { webView ->
                webView.settings.textZoom = (100 * fontScale).toInt().coerceIn(85, 145)
                webView.loadDataWithBaseURL(
                    "https://local.stabilitymatrix/",
                    html,
                    "text/html",
                    "UTF-8",
                    null,
                )
                scrollAnchorId?.let { anchorId ->
                    webView.post {
                        webView.evaluateJavascript(
                            """
                            (function(){
                              var el = document.getElementById('$anchorId');
                              if (el) el.scrollIntoView({behavior:'smooth', block:'start'});
                            })();
                            """.trimIndent(),
                            null,
                        )
                    }
                }
            },
        )
    }
}
