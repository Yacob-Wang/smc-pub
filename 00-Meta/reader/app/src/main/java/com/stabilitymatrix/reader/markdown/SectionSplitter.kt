package com.stabilitymatrix.reader.markdown

object SectionSplitter {

    private val headerRegex = Regex("^(#{1,3})\\s+(.+)$")

    fun split(markdown: String): List<MarkdownSection> {
        val lines = markdown.lines()
        val sections = mutableListOf<MarkdownSection>()
        var currentTitle = "前言"
        var currentLevel = 1
        var currentId = "intro"
        var currentLines = mutableListOf<String>()
        var index = 0

        fun flush() {
            val body = currentLines.joinToString("\n").trim()
            if (body.isNotEmpty() || sections.isEmpty()) {
                sections += MarkdownSection(
                    id = currentId,
                    title = currentTitle,
                    level = currentLevel,
                    content = if (sections.isEmpty() && body.isEmpty()) markdown.trim() else body,
                    index = index++,
                )
            }
            currentLines = mutableListOf()
        }

        for (line in lines) {
            val match = headerRegex.find(line)
            if (match != null) {
                flush()
                currentLevel = match.groupValues[1].length
                currentTitle = match.groupValues[2].trim()
                currentId = slugify(currentTitle)
                currentLines.add(line)
            } else {
                currentLines.add(line)
            }
        }
        flush()

        if (sections.size == 1 && sections[0].content == markdown.trim()) {
            return listOf(
                MarkdownSection(
                    id = "full",
                    title = "全文",
                    level = 1,
                    content = markdown,
                    index = 0,
                ),
            )
        }
        return sections
    }

    fun slugify(title: String): String = MarkdownHtmlRenderer.slugify(title)
}
