package com.stabilitymatrix.reader.markdown

data class MarkdownSection(
    val id: String,
    val title: String,
    val level: Int,
    val content: String,
    val index: Int,
)
