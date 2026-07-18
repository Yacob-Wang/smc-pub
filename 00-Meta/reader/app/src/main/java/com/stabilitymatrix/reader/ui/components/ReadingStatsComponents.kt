package com.stabilitymatrix.reader.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.outlined.RadioButtonUnchecked
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.stabilitymatrix.reader.data.ArticleReadState
import com.stabilitymatrix.reader.data.CatalogReadingSummary
import com.stabilitymatrix.reader.data.formatReadingDuration

@Composable
fun ReadStatusIcon(
    state: ArticleReadState,
    modifier: Modifier = Modifier,
) {
    when (state) {
        ArticleReadState.READ -> Icon(
            Icons.Default.CheckCircle,
            contentDescription = "已读完",
            tint = MaterialTheme.colorScheme.primary,
            modifier = modifier.size(22.dp),
        )
        ArticleReadState.IN_PROGRESS -> Box(
            modifier = modifier
                .size(22.dp)
                .clip(CircleShape)
                .background(MaterialTheme.colorScheme.primary.copy(alpha = 0.18f)),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                modifier = Modifier
                    .size(10.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.primary),
            )
        }
        ArticleReadState.UNREAD -> Icon(
            Icons.Outlined.RadioButtonUnchecked,
            contentDescription = "未读",
            tint = MaterialTheme.colorScheme.outline,
            modifier = modifier.size(22.dp),
        )
    }
}

fun readStatusLabel(state: ArticleReadState): String = when (state) {
    ArticleReadState.READ -> "已读"
    ArticleReadState.IN_PROGRESS -> "在读"
    ArticleReadState.UNREAD -> "未读"
}

@Composable
fun ReadingProgressBar(
    readCount: Int,
    totalCount: Int,
    modifier: Modifier = Modifier,
    showLabel: Boolean = true,
) {
    if (totalCount <= 0) return
    val progress = readCount.toFloat() / totalCount
    Column(modifier = modifier.fillMaxWidth()) {
        if (showLabel) {
            Text(
                text = "已读 $readCount / $totalCount 篇（${(progress * 100).toInt()}%）",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            androidx.compose.foundation.layout.Spacer(Modifier.size(6.dp))
        }
        LinearProgressIndicator(
            progress = { progress.coerceIn(0f, 1f) },
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(999.dp)),
            strokeCap = StrokeCap.Round,
        )
    }
}

@Composable
fun ReadingStatsCard(
    summary: CatalogReadingSummary,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surfaceContainerLow,
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                text = "阅读统计",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            androidx.compose.foundation.layout.Spacer(Modifier.size(12.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                StatCell("累计时长", formatReadingDuration(summary.totalSeconds))
                StatCell("已读完", "${summary.readCount} 篇")
                StatCell("在读", "${summary.inProgressCount} 篇")
                StatCell("未读", "${summary.unreadCount} 篇")
            }
            androidx.compose.foundation.layout.Spacer(Modifier.size(14.dp))
            ReadingProgressBar(
                readCount = summary.readCount,
                totalCount = summary.totalArticles,
            )
        }
    }
}

@Composable
private fun StatCell(label: String, value: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = value,
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
