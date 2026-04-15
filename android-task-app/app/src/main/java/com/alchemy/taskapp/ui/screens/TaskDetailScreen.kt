package com.alchemy.taskapp.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.alchemy.taskapp.data.TaskPriority
import com.alchemy.taskapp.data.TaskSource
import com.alchemy.taskapp.data.TaskStatus
import com.alchemy.taskapp.viewmodel.TaskViewModel
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TaskDetailScreen(
    taskId: String,
    onNavigateBack: () -> Unit,
    onNavigateToEdit: (String) -> Unit,
    viewModel: TaskViewModel = hiltViewModel()
) {
    LaunchedEffect(taskId) { viewModel.loadTaskForEdit(taskId) }
    val state by viewModel.formState.collectAsStateWithLifecycle()
    val task = state.task

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Task Details") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { onNavigateToEdit(taskId) }) {
                        Icon(Icons.Default.Edit, contentDescription = "Edit")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Title & status
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = task.title,
                    style = MaterialTheme.typography.headlineSmall.copy(
                        fontWeight = FontWeight.Bold,
                        textDecoration = if (task.status == TaskStatus.DONE)
                            TextDecoration.LineThrough else TextDecoration.None
                    ),
                    modifier = Modifier.weight(1f)
                )
                StatusBadge(task.status)
            }

            // Source badge
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                val (sourceIcon, sourceLabel) = when (task.source) {
                    TaskSource.IMAGE -> Icons.Default.Image to "Created from image"
                    TaskSource.VOICE -> Icons.Default.Mic to "Created from voice"
                    TaskSource.MANUAL -> Icons.Default.EditNote to "Created manually"
                }
                Icon(sourceIcon, contentDescription = null,
                    tint = MaterialTheme.colorScheme.secondary,
                    modifier = Modifier.size(16.dp))
                Text(sourceLabel,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.secondary)
            }

            Divider()

            // Description
            if (task.description.isNotBlank()) {
                DetailSection(title = "Description") {
                    Text(task.description, style = MaterialTheme.typography.bodyMedium)
                }
            }

            // Priority
            DetailSection(title = "Priority") {
                PriorityChip(task.priority)
            }

            // Assignees
            if (task.assignedTo.isNotBlank() || task.assignedBy.isNotBlank()) {
                DetailSection(title = "People") {
                    if (task.assignedBy.isNotBlank()) {
                        PersonRow(label = "Assigned by", name = task.assignedBy,
                            icon = Icons.Default.PersonAdd)
                    }
                    if (task.assignedTo.isNotBlank()) {
                        PersonRow(label = "Assigned to", name = task.assignedTo,
                            icon = Icons.Default.Person)
                    }
                }
            }

            // Dates
            if (task.dueDate != null || task.reminderDate != null) {
                DetailSection(title = "Dates") {
                    val fmt = DateTimeFormatter.ofPattern("EEE, MMM d yyyy  HH:mm")
                    task.dueDate?.let {
                        DateRow(
                            label = "Due",
                            epochMillis = it,
                            formatter = fmt,
                            isOverdue = it < System.currentTimeMillis() && task.status != TaskStatus.DONE
                        )
                    }
                    task.reminderDate?.let {
                        DateRow(label = "Reminder", epochMillis = it, formatter = fmt)
                    }
                }
            }

            // Tags
            if (task.tagList().isNotEmpty()) {
                DetailSection(title = "Tags") {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        task.tagList().forEach { tag ->
                            SuggestionChip(
                                onClick = {},
                                label = { Text("#$tag") }
                            )
                        }
                    }
                }
            }

            // Source image preview
            task.imageUri?.let { uri ->
                DetailSection(title = "Source Image") {
                    Card(shape = RoundedCornerShape(8.dp)) {
                        AsyncImage(
                            model = uri,
                            contentDescription = "Source image",
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(max = 300.dp)
                        )
                    }
                }
            }

            // Created / Updated timestamps
            DetailSection(title = "Audit") {
                val shortFmt = DateTimeFormatter.ofPattern("MMM d yyyy, HH:mm")
                DateRow("Created", task.createdAt, shortFmt)
                DateRow("Updated", task.updatedAt, shortFmt)
            }

            // Mark done / reopen button
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = { viewModel.toggleTaskDone(task) },
                modifier = Modifier.fillMaxWidth()
            ) {
                Icon(
                    if (task.status == TaskStatus.DONE) Icons.Default.Refresh else Icons.Default.Check,
                    contentDescription = null
                )
                Spacer(Modifier.width(8.dp))
                Text(if (task.status == TaskStatus.DONE) "Re-open Task" else "Mark as Done")
            }
        }
    }
}

// ── Sub-composables ───────────────────────────────────────────────────────────

@Composable
private fun DetailSection(
    title: String,
    content: @Composable ColumnScope.() -> Unit
) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(
            text = title.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        content()
    }
}

@Composable
private fun StatusBadge(status: TaskStatus) {
    val color = when (status) {
        TaskStatus.PENDING -> MaterialTheme.colorScheme.primary
        TaskStatus.IN_PROGRESS -> MaterialTheme.colorScheme.tertiary
        TaskStatus.DONE -> MaterialTheme.colorScheme.secondary
        TaskStatus.CANCELLED -> MaterialTheme.colorScheme.error
    }
    Surface(shape = RoundedCornerShape(8.dp), color = color.copy(alpha = 0.15f)) {
        Text(
            text = status.name.replace('_', ' '),
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp),
            style = MaterialTheme.typography.labelMedium,
            color = color
        )
    }
}

@Composable
private fun PriorityChip(priority: TaskPriority) {
    val (emoji, label) = when (priority) {
        TaskPriority.LOW -> "🟢" to "Low"
        TaskPriority.MEDIUM -> "🟡" to "Medium"
        TaskPriority.HIGH -> "🟠" to "High"
        TaskPriority.URGENT -> "🔴" to "Urgent"
    }
    Text("$emoji  $label", style = MaterialTheme.typography.bodyMedium)
}

@Composable
private fun PersonRow(
    label: String,
    name: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector
) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(18.dp),
            tint = MaterialTheme.colorScheme.primary)
        Column {
            Text(label, style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(name, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun DateRow(
    label: String,
    epochMillis: Long,
    formatter: DateTimeFormatter,
    isOverdue: Boolean = false
) {
    val text = Instant.ofEpochMilli(epochMillis)
        .atZone(ZoneId.systemDefault())
        .format(formatter)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Icon(
            Icons.Default.Schedule,
            contentDescription = null,
            modifier = Modifier.size(18.dp),
            tint = if (isOverdue) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant
        )
        Column {
            Text(label, style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(
                text = if (isOverdue) "⚠️ Overdue · $text" else text,
                style = MaterialTheme.typography.bodyMedium,
                color = if (isOverdue) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurface
            )
        }
    }
}
