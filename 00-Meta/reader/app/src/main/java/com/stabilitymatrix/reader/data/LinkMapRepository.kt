package com.stabilitymatrix.reader.data

import android.content.Context
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive

class LinkMapRepository(context: Context) {
    private val json = Json { ignoreUnknownKeys = true }

    private val linkMap: Map<String, String> by lazy {
        context.assets.open("link-map.json").bufferedReader().use { reader ->
            val obj = json.decodeFromString(JsonObject.serializer(), reader.readText())
            obj.mapValues { it.value.jsonPrimitive.content }
        }
    }

    fun resolve(href: String, fromArticleId: String): String? {
        if (href.startsWith("http://") || href.startsWith("https://")) return null
        if (href.startsWith("#")) return null

        val normalized = href.replace('\\', '/').substringBefore("#")
        linkMap[normalized]?.let { return it }

        val resolved = resolveRelative(fromArticleId, normalized)
        linkMap[resolved]?.let { return it }
        val withoutMd = resolved.removeSuffix(".md")
        return withoutMd.takeIf { linkMap.containsKey(it) || linkMap.containsKey("$it.md") }
    }

    private fun resolveRelative(fromArticleId: String, target: String): String {
        var path = target
        if (!path.endsWith(".md")) {
            if (path.endsWith("/")) path += "README.md" else path += ".md"
        }

        if (path.startsWith("/")) {
            return path.trimStart('/').removeSuffix(".md")
        }

        val fromDir = fromArticleId.substringBeforeLast('/', "")
        val parts = mutableListOf<String>()
        if (fromDir.isNotEmpty()) parts.addAll(fromDir.split('/'))
        for (seg in path.split('/')) {
            when (seg) {
                ".." -> if (parts.isNotEmpty()) parts.removeAt(parts.lastIndex)
                ".", "" -> Unit
                else -> parts.add(seg)
            }
        }
        return parts.joinToString("/").removeSuffix(".md")
    }
}
