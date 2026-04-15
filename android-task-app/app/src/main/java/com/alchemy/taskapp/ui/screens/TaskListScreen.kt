package com.alchemy.taskapp.ui.screens

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.alchemy.taskapp.data.Task
import com.alchemy.taskapp.data.TaskPriority
import com.alchemy.taskapp.data.TaskStatus
import com.alchemy.taskapp.viewmodel.TaskViewModel
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskListScreen(
    onNavigateToCreate: () -> Unit,
    onNavigateToDetail: (String) -> Unit,
    viewModel: TaskViewModel = hiltViewModel()
) {
    val state by viewModel.listState.collectAsStateWithLifecycle()
    val snackbarHostState = remember { SnackbarHostState() }

    // Show snackbar messages
    LaunchedEffect(state.snackbarMessage) {
        state.snackbarMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearSnackbar()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Alchemy Tasks") },
                actions = {
                    // LLM status indicator
                    LlmStatusChip(
                        isReady = state.llmReady,
                        isInitialising = state.llmInitialising
                    )
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            )
        },
        floatingActionButton = {
            FloatingActionButton(onClick = onNavigateToCreate) {
                Icon(Icons.Default.Add, contentDescription = "Create task")
            }
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
        ) {
            // Search bar
            OutlinedTextField(
                value = state.searchQuery,
                onValueChange = viewModel::setSearchQuery,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp),
                placeholder = { Text("Search tasks, assignees, tags…") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                singleLine = true,
                shape = RoundedCornerShape(24.dp)
            )

            // Status filter chips
            StatusFilterRow(
                selected = state.filterStatus,
                onSelect = viewModel::setStatusFilter
            )

            if (state.isLoading) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (state.tasks.isEmpty()) {
                EmptyState(hasFilter = state.filterStatus != null || state.searchQuery.isNotBlank())
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(state.tasks, key = { it.id }) { task ->
                        TaskCard(
                            task = task,
                            onClick = { onNavigateToDetail(task.id) },
                            onToggleDone = { viewModel.toggleTaskDone(task) },
                            onDelete = { viewModel.deleteTask(task) }
                        )
                    }
                    item { Spacer(Modifier.height(72.dp)) } // FAB clearance
                }
            }
        }
    }
}

// ── Sub-composables ───────────────────────────────────────────────────────────

@Composable
private fun LlmStatusChip(isReady: Boolean, isInitialising: Boolean) {
    val bgColor by animateColorAsState(
        targetValue = when {
            isInitialising -> MaterialTheme.colorScheme.tertiary
            isReady -> Color(0xFF4CAF50)
            else -> MaterialTheme.colorScheme.error
        },
        animationSpec = tween(500),
        label = "llm_chip_color"
    )
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = bgColor.copy(alpha = 0.15f),
        modifier = Modifier.padding(end = 8.dp)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            if (isInitialising) {
                CircularProgressIndicator(
                    modifier = Modifier.size(10.dp),
                    strokeWidth = 1.5.dp,
                    color = bgColor
                )
            } else {
                Box(
                    modifier = Modifier
                        .size(8.dp)
                        .clip(CircleShape)
                        .background(bgColor)
                )
            }
            Text(
                text = when {
                    isInitialising -> "AI loading…"
                    isReady -> "AI ready"
                    else -> "AI offline"
                },
                style = MaterialTheme.typography.labelSmall,
                color = bgColor
            )
        }
    }
}

@Composable
private fun StatusFilterRow(
    selected: TaskStatus?,
    onSelect: (TaskStatus?) -> Unit
) {
    val statuses = listOf(null) + TaskStatus.values().toList()
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        statuses.forEach { status ->
            FilterChip(
                selected = selected == status,
                onClick = { onSelect(status) },
                label = { Text(status?.name?.lowercase()?.replaceFirstChar { it.uppercase() } ?: "All") }
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TaskCard(
    task: Task,
    onClick: () -> Unit,
    onToggleDone: () -> Unit,
    onDelete: () -> Unit
) {
    var showDeleteDialog by remember { mutableStateOf(false) }

    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text("Delete task?") },
            text = { Text("\"${task.title}\" will be permanently deleted.") },
            confirmButton = {
                TextButton(onClick = {
                    showDeleteDialog = false
                    onDelete()
                }) { Text("Delete", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) { Text("Cancel") }
            }
        )
    }

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.Top
        ) {
            // Done checkbox
            Checkbox(
                checked = task.status == TaskStatus.DONE,
                onCheckedChange = { onToggleDone() }
            )

            Spacer(Modifier.width(8.dp))

            Column(modifier = Modifier.weight(1f)) {
                // Title
                Text(
                    text = task.title,
                    style = MaterialTheme.typography.titleMedium.copy(
                        fontWeight = FontWeight.SemiBold,
                        textDecoration = if (task.status == TaskStatus.DONE)
                            TextDecoration.LineThrough else TextDecoration.None
                    ),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )

                // Description preview
                if (task.description.isNotBlank()) {
                    Text(
                        text = task.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.padding(top = 2.dp)
                    )
                }

                Spacer(Modifier.height(6.dp))

                // Meta row
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    PriorityBadge(task.priority)

                    if (task.assignedTo.isNotBlank()) {
                        AssigneeBadge(task.assignedTo)
                    }

                    task.dueDate?.let { due ->
                        DueDateBadge(dueEpochMillis = due, isDone = task.status == TaskStatus.DONE)
                    }

                    SourceIcon(task.source.name)
                }
            }

            // Delete button
            IconButton(
                onClick = { showDeleteDialog = true },
                modifier = Modifier.size(32.dp)
            ) {
                Icon(
                    Icons.Default.DeleteOutline,
                    contentDescription = "Delete",
                    tint = MaterialTheme.colorScheme.error.copy(alpha = 0.6f),
                    modifier = Modifier.size(18.dp)
                )
            }
        }
    }
}

@Composable
private fun PriorityBadge(priority: TaskPriority) {
    val (color, label) = when (priority) {
        TaskPriority.LOW -> Color(0xFF81C784) to "Low"
        TaskPriority.MEDIUM -> Color(0xFFFFB74D) to "Med"
        TaskPriority.HIGH -> Color(0xFFE57373) to "High"
        TaskPriority.URGENT -> Color(0xFFC62828) to "Urgent"
    }
    Surface(
        shape = RoundedCornerShape(4.dp),
        color = color.copy(alpha = 0.2f)
    ) {
        Text(
            text = label,
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            style = MaterialTheme.typography.labelSmall,
            color = color
        )
    }
}

@Composable
private fun AssigneeBadge(name: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            Icons.Default.Person,
            contentDescription = null,
            modifier = Modifier.size(12.dp),
            tint = MaterialTheme.colorScheme.primary
        )
        Spacer(Modifier.width(2.dp))
        Text(
            text = name,
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.primary,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            modifier = Modifier.widthIn(max = 80.dp)
        )
    }
}

@Composable
private fun DueDateBadge(dueEpochMillis: Long, isDone: Boolean) {
    val now = System.currentTimeMillis()
    val isOverdue = dueEpochMillis < now && !isDone
    val color = if (isOverdue) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
    val fmt = DateTimeFormatter.ofPattern("MMM d")
    val label = Instant.ofEpochMilli(dueEpochMillis)
        .atZone(ZoneId.systemDefault())
        .format(fmt)
    Row(verticalAlignment = Alignment.CenterVertically) {
        Icon(
            Icons.Default.Schedule,
            contentDescription = null,
            modifier = Modifier.size(12.dp),
            tint = color
        )
        Spacer(Modifier.width(2.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = color
        )
    }
}

@Composable
private fun SourceIcon(sourceName: String) {
    val (icon, desc) = when (sourceName) {
        "IMAGE" -> Icons.Default.Image to "From image"
        "VOICE" -> Icons.Default.Mic to "From voice"
        else -> Icons.Default.EditNote to "Manual"
    }
    Icon(icon, contentDescription = desc, modifier = Modifier.size(14.dp),
        tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f))
}

@Composable
private fun EmptyState(hasFilter: Boolean) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(
                if (hasFilter) Icons.Default.SearchOff else Icons.Default.TaskAlt,
                contentDescription = null,
                modifier = Modifier.size(64.dp),
                tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f)
            )
            Spacer(Modifier.height(16.dp))
            Text(
                text = if (hasFilter) "No tasks match your filter" else "No tasks yet",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            if (!hasFilter) {
                Text(
                    text = "Tap + to create one",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f)
                )
            }
        }
    }
}
