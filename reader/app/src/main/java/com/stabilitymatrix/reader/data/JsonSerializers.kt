package com.stabilitymatrix.reader.data

import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonTransformingSerializer

/**
 * PowerShell ConvertTo-Json may emit a single object instead of a one-element array.
 * Accept both `[...]` and `{...}` so catalog parsing never crashes on startup.
 */
internal object CatalogSeriesListSerializer :
    JsonTransformingSerializer<List<CatalogSeries>>(ListSerializer(CatalogSeries.serializer())) {
    override fun transformDeserialize(element: JsonElement): JsonElement =
        if (element is JsonObject) JsonArray(listOf(element)) else element
}

internal object CatalogArticleListSerializer :
    JsonTransformingSerializer<List<CatalogArticle>>(ListSerializer(CatalogArticle.serializer())) {
    override fun transformDeserialize(element: JsonElement): JsonElement =
        if (element is JsonObject) JsonArray(listOf(element)) else element
}

internal object CatalogModuleListSerializer :
    JsonTransformingSerializer<List<CatalogModule>>(ListSerializer(CatalogModule.serializer())) {
    override fun transformDeserialize(element: JsonElement): JsonElement =
        if (element is JsonObject) JsonArray(listOf(element)) else element
}
