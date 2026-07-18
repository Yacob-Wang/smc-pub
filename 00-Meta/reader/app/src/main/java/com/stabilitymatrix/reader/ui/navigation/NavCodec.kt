package com.stabilitymatrix.reader.ui.navigation

import android.util.Base64

object NavCodec {
    fun encode(value: String): String =
        Base64.encodeToString(
            value.toByteArray(Charsets.UTF_8),
            Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING,
        )

    fun decode(value: String): String =
        String(Base64.decode(value, Base64.URL_SAFE), Charsets.UTF_8)

    fun decodeNavArg(value: String): String = runCatching {
        decode(value)
    }.getOrElse { value }
}
