package com.stabilitymatrix.reader.markdown

import org.commonmark.Extension
import org.commonmark.ext.autolink.AutolinkExtension
import org.commonmark.ext.gfm.tables.TablesExtension
import org.commonmark.node.Node
import org.commonmark.parser.Parser
import org.commonmark.renderer.html.HtmlRenderer

object MarkdownHtmlRenderer {

    private val extensions: List<Extension> = listOf(
        TablesExtension.create(),
        AutolinkExtension.create(),
    )

    private val parser: Parser = Parser.builder()
        .extensions(extensions)
        .build()

    private val renderer: HtmlRenderer = HtmlRenderer.builder()
        .extensions(extensions)
        .escapeHtml(true)
        .softbreak("<br />\n")
        .build()

    fun renderDocument(markdown: String, darkTheme: Boolean): String {
        val document: Node = parser.parse(markdown)
        val body = injectHeadingIds(renderer.render(document))
        return wrapHtml(body, darkTheme)
    }

    fun preprocessLinks(
        markdown: String,
        linkResolver: (String) -> String? = { null },
    ): String {
        return markdown.replace(Regex("\\]\\(([^)]+\\.md[^)]*)\\)")) { match ->
            val href = match.groupValues[1]
            val resolved = linkResolver(href)
            if (resolved != null) "](smr://article/$resolved)" else match.value
        }
    }

    private fun injectHeadingIds(html: String): String {
        return Regex("<h([1-4])>([^<]+)</h\\1>").replace(html) { match ->
            val level = match.groupValues[1]
            val text = match.groupValues[2]
            val id = slugify(text)
            """<h$level id="$id">$text</h$level>"""
        }
    }

    fun slugify(title: String): String {
        return title.lowercase()
            .replace(Regex("<[^>]+>"), "")
            .replace(Regex("[^a-z0-9\\u4e00-\\u9fff]+"), "-")
            .trim('-')
            .ifEmpty { "section" }
    }

    private fun wrapHtml(body: String, darkTheme: Boolean): String {
        val bg = if (darkTheme) "#121212" else "#ffffff"
        val fg = if (darkTheme) "#e8e8e8" else "#1a1a1a"
        val muted = if (darkTheme) "#9e9e9e" else "#666666"
        val codeBg = if (darkTheme) "#1e1e1e" else "#f6f8fa"
        val border = if (darkTheme) "#333333" else "#e0e0e0"
        val quoteBg = if (darkTheme) "#1a2332" else "#f0f4f8"
        val link = if (darkTheme) "#90caf9" else "#1565c0"
        val thBg = if (darkTheme) "#2a2a2a" else "#f0f0f0"

        return """
            <!DOCTYPE html>
            <html>
            <head>
              <meta charset="utf-8" />
              <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=4.0" />
              <style>
                * { box-sizing: border-box; }
                body {
                  margin: 0;
                  padding: 12px 16px 48px;
                  font-size: 15px;
                  line-height: 1.7;
                  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                    "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
                  color: $fg;
                  background: $bg;
                  -webkit-text-size-adjust: 100%;
                }
                h1 { font-size: 1.45em; font-weight: 700; margin: 0.2em 0 0.7em; line-height: 1.35; }
                h2 {
                  font-size: 1.25em; font-weight: 700; margin: 1.4em 0 0.55em;
                  padding-bottom: 0.35em; border-bottom: 1px solid $border;
                }
                h3 { font-size: 1.12em; font-weight: 600; margin: 1.1em 0 0.45em; }
                h4, h5, h6 { font-size: 1.02em; font-weight: 600; margin: 0.9em 0 0.35em; }
                p { margin: 0.55em 0; }
                strong { font-weight: 700; }
                em { font-style: italic; }
                hr { border: none; border-top: 1px solid $border; margin: 1.5em 0; }
                blockquote {
                  margin: 0.8em 0; padding: 0.55em 1em;
                  border-left: 4px solid $link;
                  background: $quoteBg;
                  color: $muted;
                }
                blockquote p { margin: 0.35em 0; }
                code {
                  font-family: "Roboto Mono", "Droid Sans Mono", "Courier New", monospace;
                  font-size: 0.86em;
                  background: $codeBg;
                  padding: 2px 6px;
                  border-radius: 4px;
                  word-break: break-word;
                }
                pre {
                  background: $codeBg;
                  border: 1px solid $border;
                  border-radius: 8px;
                  padding: 12px 14px;
                  margin: 0.85em 0;
                  overflow-x: auto;
                  -webkit-overflow-scrolling: touch;
                }
                pre code {
                  background: transparent;
                  padding: 0;
                  font-size: 12px;
                  line-height: 1.5;
                  white-space: pre;
                  word-break: normal;
                  display: block;
                }
                table {
                  border-collapse: collapse;
                  width: 100%;
                  margin: 1em 0;
                  font-size: 0.92em;
                  display: block;
                  overflow-x: auto;
                  -webkit-overflow-scrolling: touch;
                }
                th, td {
                  border: 1px solid $border;
                  padding: 8px 10px;
                  text-align: left;
                  vertical-align: top;
                  min-width: 80px;
                }
                th { background: $thBg; font-weight: 600; white-space: nowrap; }
                ul, ol { padding-left: 1.4em; margin: 0.45em 0; }
                li { margin: 0.3em 0; }
                li > p { margin: 0.2em 0; }
                a { color: $link; text-decoration: none; word-break: break-all; }
                a:active { opacity: 0.7; }
              </style>
            </head>
            <body>$body</body>
            </html>
        """.trimIndent()
    }
}
