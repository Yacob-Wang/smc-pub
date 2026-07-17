package com.stabilitymatrix.reader.ui.components

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material.icons.filled.Android
import androidx.compose.material.icons.filled.Apps
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Extension
import androidx.compose.material.icons.filled.Memory
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material.icons.filled.Route
import androidx.compose.material.icons.filled.Storage
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import com.stabilitymatrix.reader.ui.theme.ModuleAi
import com.stabilitymatrix.reader.ui.theme.ModuleApp
import com.stabilitymatrix.reader.ui.theme.ModuleFramework
import com.stabilitymatrix.reader.ui.theme.ModuleHook
import com.stabilitymatrix.reader.ui.theme.ModuleLinux
import com.stabilitymatrix.reader.ui.theme.ModuleRoot
import com.stabilitymatrix.reader.ui.theme.ModuleRuntime
import com.stabilitymatrix.reader.ui.theme.ModuleTools

data class ModuleVisual(
    val icon: ImageVector,
    val accent: Color,
    val shortLabel: String,
)

fun moduleVisual(moduleId: String): ModuleVisual = when (moduleId) {
    "Linux_Kernel" -> ModuleVisual(Icons.Default.Storage, ModuleLinux, "Kernel")
    "Runtime" -> ModuleVisual(Icons.Default.Memory, ModuleRuntime, "ART")
    "Android_Framework" -> ModuleVisual(Icons.Default.Android, ModuleFramework, "FWK")
    "App" -> ModuleVisual(Icons.Default.Apps, ModuleApp, "App")
    "Tools" -> ModuleVisual(Icons.Default.Build, ModuleTools, "Tools")
    "Hook" -> ModuleVisual(Icons.Default.Extension, ModuleHook, "Hook")
    "AI_Native_X" -> ModuleVisual(Icons.Default.Psychology, ModuleAi, "AI")
    "_root" -> ModuleVisual(Icons.Default.Route, ModuleRoot, "Roadmap")
    else -> ModuleVisual(Icons.AutoMirrored.Filled.MenuBook, ModuleFramework, moduleId)
}
