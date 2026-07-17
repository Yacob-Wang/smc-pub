package com.stabilitymatrix.reader.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import com.stabilitymatrix.reader.data.ThemeMode

private val LightColors = lightColorScheme(
    primary = ReaderBlue,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFDDE7FF),
    onPrimaryContainer = Color(0xFF0B1F52),
    secondary = Color(0xFF475569),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFE2E8F0),
    onSecondaryContainer = Color(0xFF1E293B),
    surface = Color(0xFFF8FAFC),
    onSurface = Color(0xFF0F172A),
    onSurfaceVariant = Color(0xFF64748B),
    surfaceContainerLow = Color(0xFFF1F5F9),
    surfaceContainerHigh = Color(0xFFE2E8F0),
    outline = Color(0xFFCBD5E1),
    outlineVariant = Color(0xFFE2E8F0),
)

private val DarkColors = darkColorScheme(
    primary = ReaderBlueDark,
    onPrimary = Color(0xFF0B1F52),
    primaryContainer = Color(0xFF1E3A8A),
    onPrimaryContainer = Color(0xFFDDE7FF),
    secondary = Color(0xFF94A3B8),
    onSecondary = Color(0xFF0F172A),
    secondaryContainer = Color(0xFF334155),
    onSecondaryContainer = Color(0xFFE2E8F0),
    surface = Color(0xFF0B1220),
    onSurface = Color(0xFFE2E8F0),
    onSurfaceVariant = Color(0xFF94A3B8),
    surfaceContainerLow = Color(0xFF111827),
    surfaceContainerHigh = Color(0xFF1E293B),
    outline = Color(0xFF475569),
    outlineVariant = Color(0xFF334155),
)

@Composable
fun ReaderTheme(
    themeMode: ThemeMode,
    content: @Composable () -> Unit,
) {
    val darkTheme = when (themeMode) {
        ThemeMode.DARK -> true
        ThemeMode.LIGHT -> false
        ThemeMode.SYSTEM -> isSystemInDarkTheme()
    }

    // 固定品牌色，避免 dynamic color 让各模块 accent 发灰
    val colorScheme = if (darkTheme) DarkColors else LightColors

    MaterialTheme(
        colorScheme = colorScheme,
        typography = ReaderTypography,
        content = content,
    )
}
