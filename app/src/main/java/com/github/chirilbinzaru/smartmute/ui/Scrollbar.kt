package com.github.chirilbinzaru.smartmute.ui

import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * Always-visible scrollbar thumb along the right edge of a LazyColumn. Position and size are
 * estimated from item counts, since items have different heights. Leave some end content
 * padding on the list so the thumb doesn't sit on top of the items.
 */
fun Modifier.verticalScrollbar(
    state: LazyListState,
    color: Color,
    width: Dp = 4.dp,
    minThumbHeight: Dp = 32.dp,
): Modifier = drawWithContent {
    drawContent()
    // Read in the draw phase, so scrolling only redraws, never recomposes.
    val info = state.layoutInfo
    val total = info.totalItemsCount
    val visible = info.visibleItemsInfo
    if (total == 0 || visible.isEmpty()) return@drawWithContent
    if (!state.canScrollForward && !state.canScrollBackward) return@drawWithContent

    val first = visible.first()
    // How far the first visible item has scrolled out of view, as a fraction of its height.
    val firstHidden = if (first.size > 0) {
        (-first.offset).coerceIn(0, first.size).toFloat() / first.size
    } else {
        0f
    }
    val visibleCount = (visible.size - firstHidden).coerceAtLeast(1f)
    val progress = when {
        !state.canScrollForward -> 1f
        else -> ((first.index + firstHidden) / (total - visibleCount)).coerceIn(0f, 1f)
    }

    val thumbHeight = (size.height * visibleCount / total).coerceAtLeast(minThumbHeight.toPx())
        .coerceAtMost(size.height)
    val thumbWidth = width.toPx()
    drawRoundRect(
        color = color,
        topLeft = Offset(size.width - thumbWidth, (size.height - thumbHeight) * progress),
        size = Size(thumbWidth, thumbHeight),
        cornerRadius = CornerRadius(thumbWidth / 2),
    )
}
