package com.alchemy.taskapp.ui.screens

import android.Manifest
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.*
import androidx.compose.foundation.border
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import com.alchemy.taskapp.ai.VoiceToTaskProcessor
import com.alchemy.taskapp.data.TaskPriority
import com.alchemy.taskapp.data.TaskSource
import com.alchemy.taskapp.data.TaskStatus
import com.alchemy.taskapp.viewmodel.TaskViewModel
import com.google.accompanist.permissions.ExperimentalPermissionsApi
import com.google.accompanist.permissions.isGranted
import com.google.accompanist.permissions.rememberPermissionState
import java.io.File
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter

@OptIn(ExperimentalMaterial3Api::class, ExperimentalPermissionsApi::class)
@Composable
fun CreateTaskScreen(
    taskId: String?,
    onNavigateBack: () -> Unit,
    viewModel: TaskViewModel = hiltViewModel()
) {
    val isEditing = taskId != null
    val context = LocalContext.current

    // Load existing task or reset for new task
    LaunchedEffect(taskId) {
        if (taskId != null) viewModel.loadTaskForEdit(taskId)
        else viewModel.resetForm()
    }

    val state by viewModel.formState.collectAsStateWithLifecycle()
    val task = state.task

    // Navigate back on successful save
    LaunchedEffect(state.savedSuccessfully) {
        if (state.savedSuccessfully) onNavigateBack()
    }

    // --- Permissions ---
    val cameraPermission = rememberPermissionState(Manifest.permission.CAMERA)
    val micPermission = rememberPermissionState(Manifest.permission.RECORD_AUDIO)

    // --- Camera capture ---
    var cameraImageUri by remember { mutableStateOf<Uri?>(null) }
    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { success ->
        if (success) cameraImageUri?.let { viewModel.processImage(it) }
    }

    fun launchCamera() {
        val photoFile = File.createTempFile("task_img_", ".jpg", context.cacheDir)
        val uri = FileProvider.getUriForFile(
            context, "${context.packageName}.fileprovider", photoFile
        )
        cameraImageUri = uri
        cameraLauncher.launch(uri)
    }

    // --- Gallery pick ---
    val galleryLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri -> uri?.let { viewModel.processImage(it) } }

    // --- Date/time picker state ---
    var showDueDatePicker by remember { mutableStateOf(false) }
    var showReminderDatePicker by remember { mutableStateOf(false) }

    // --- Snackbar ---
    val snackbarHostState = remember { SnackbarHostState() }
    LaunchedEffect(state.errorMessage) {
        state.errorMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearFormError()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(if (isEditing) "Edit Task" else "New Task") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    TextButton(
                        onClick = viewModel::saveTask,
                        enabled = !state.isSaving && task.title.isNotBlank()
                    ) {
                        if (state.isSaving) {
                            CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        } else {
                            Icon(Icons.Default.Save, contentDescription = null)
                            Spacer(Modifier.width(4.dp))
                            Text("Save")
                        }
                    }
                }
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) }
    ) { padding ->

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {

            // ── AI Input Buttons ──────────────────────────────────────────────
            AiInputRow(
                isProcessing = state.isProcessingAi,
                voiceState = state.voiceState,
                onCamera = {
                    if (cameraPermission.status.isGranted) launchCamera()
                    else cameraPermission.launchPermissionRequest()
                },
                onGallery = { galleryLauncher.launch("image/*") },
                onVoice = {
                    if (micPermission.status.isGranted) viewModel.startVoiceCapture()
                    else micPermission.launchPermissionRequest()
                }
            )

            // Source image preview (if from image)
            if (task.source == TaskSource.IMAGE && task.imageUri != null) {
                AsyncImage(
                    model = task.imageUri,
                    contentDescription = "Source image",
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 200.dp)
                        .clip(RoundedCornerShape(12.dp))
                        .border(1.dp, MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(12.dp))
                )
            }

            // ── Title ─────────────────────────────────────────────────────────
            OutlinedTextField(
                value = task.title,
                onValueChange = viewModel::updateTitle,
                label = { Text("Task Title *") },
                placeholder = { Text("What needs to be done?") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                leadingIcon = { Icon(Icons.Default.Title, contentDescription = null) },
                isError = task.title.isBlank()
            )

            // ── Description ───────────────────────────────────────────────────
            OutlinedTextField(
                value = task.description,
                onValueChange = viewModel::updateDescription,
                label = { Text("Description") },
                placeholder = { Text("Add details…") },
                modifier = Modifier.fillMaxWidth().heightIn(min = 96.dp),
                maxLines = 6,
                leadingIcon = { Icon(Icons.Default.Notes, contentDescription = null) }
            )

            // ── Priority & Status ─────────────────────────────────────────────
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                PriorityDropdown(
                    selected = task.priority,
                    onSelect = viewModel::updatePriority,
                    modifier = Modifier.weight(1f)
                )
                StatusDropdown(
                    selected = task.status,
                    onSelect = viewModel::updateStatus,
                    modifier = Modifier.weight(1f)
                )
            }

            // ── Assignees ─────────────────────────────────────────────────────
            Text(
                "People",
                style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold)
            )
            OutlinedTextField(
                value = task.assignedBy,
                onValueChange = viewModel::updateAssignedBy,
                label = { Text("Assigned By") },
                placeholder = { Text("Who is assigning this?") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                leadingIcon = { Icon(Icons.Default.PersonAdd, contentDescription = null) }
            )
            OutlinedTextField(
                value = task.assignedTo,
                onValueChange = viewModel::updateAssignedTo,
                label = { Text("Assigned To") },
                placeholder = { Text("Who should complete this?") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                leadingIcon = { Icon(Icons.Default.Person, contentDescription = null) }
            )

            // ── Due Date ──────────────────────────────────────────────────────
            Text(
                "Dates & Times",
                style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold)
            )
            DateTimePickerField(
                label = "Due Date / Time",
                epochMillis = task.dueDate,
                onDateSelected = viewModel::updateDueDate,
                onClear = { viewModel.updateDueDate(null) }
            )
            DateTimePickerField(
                label = "Reminder",
                epochMillis = task.reminderDate,
                onDateSelected = viewModel::updateReminderDate,
                onClear = { viewModel.updateReminderDate(null) }
            )

            // ── Tags ──────────────────────────────────────────────────────────
            OutlinedTextField(
                value = task.tags,
                onValueChange = viewModel::updateTags,
                label = { Text("Tags") },
                placeholder = { Text("urgent, finance, Q1  (comma-separated)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                leadingIcon = { Icon(Icons.Default.Label, contentDescription = null) }
            )

            Spacer(Modifier.height(80.dp)) // scroll clearance
        }
    }
}

// ── AI Input Row ──────────────────────────────────────────────────────────────

@Composable
private fun AiInputRow(
    isProcessing: Boolean,
    voiceState: VoiceToTaskProcessor.VoiceState?,
    onCamera: () -> Unit,
    onGallery: () -> Unit,
    onVoice: () -> Unit
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.4f)
        ),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                "✨  AI Create from…",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.secondary
            )

            if (isProcessing) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                    val label = when (voiceState) {
                        is VoiceToTaskProcessor.VoiceState.Listening -> "Listening…"
                        is VoiceToTaskProcessor.VoiceState.Partial -> "\"${voiceState.text}\""
                        is VoiceToTaskProcessor.VoiceState.Processing -> "Processing with AI…"
                        else -> "Analysing…"
                    }
                    Text(label, style = MaterialTheme.typography.bodySmall)
                }
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(
                        onClick = onCamera,
                        modifier = Modifier.weight(1f)
                    ) {
                        Icon(Icons.Default.CameraAlt, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Camera")
                    }
                    OutlinedButton(
                        onClick = onGallery,
                        modifier = Modifier.weight(1f)
                    ) {
                        Icon(Icons.Default.Image, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Gallery")
                    }
                    OutlinedButton(
                        onClick = onVoice,
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = MaterialTheme.colorScheme.tertiary
                        )
                    ) {
                        Icon(Icons.Default.Mic, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Voice")
                    }
                }
            }
        }
    }
}

// ── Priority Dropdown ─────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PriorityDropdown(
    selected: TaskPriority,
    onSelect: (TaskPriority) -> Unit,
    modifier: Modifier = Modifier
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }, modifier = modifier) {
        OutlinedTextField(
            value = selected.name,
            onValueChange = {},
            readOnly = true,
            label = { Text("Priority") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            modifier = Modifier.menuAnchor()
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            TaskPriority.values().forEach { p ->
                DropdownMenuItem(
                    text = { Text(p.name) },
                    onClick = { onSelect(p); expanded = false }
                )
            }
        }
    }
}

// ── Status Dropdown ───────────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun StatusDropdown(
    selected: TaskStatus,
    onSelect: (TaskStatus) -> Unit,
    modifier: Modifier = Modifier
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(expanded = expanded, onExpandedChange = { expanded = it }, modifier = modifier) {
        OutlinedTextField(
            value = selected.name.replace('_', ' '),
            onValueChange = {},
            readOnly = true,
            label = { Text("Status") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
            modifier = Modifier.menuAnchor()
        )
        ExposedDropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            TaskStatus.values().forEach { s ->
                DropdownMenuItem(
                    text = { Text(s.name.replace('_', ' ')) },
                    onClick = { onSelect(s); expanded = false }
                )
            }
        }
    }
}

// ── Date Time Picker Field ────────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DateTimePickerField(
    label: String,
    epochMillis: Long?,
    onDateSelected: (Long) -> Unit,
    onClear: () -> Unit
) {
    var showDatePicker by remember { mutableStateOf(false) }
    var showTimePicker by remember { mutableStateOf(false) }

    // Temp holder while picking date before time
    var pendingDate by remember { mutableStateOf<Long?>(null) }

    val displayText = epochMillis?.let {
        val fmt = DateTimeFormatter.ofPattern("EEE, MMM d yyyy  HH:mm")
        Instant.ofEpochMilli(it).atZone(ZoneId.systemDefault()).format(fmt)
    } ?: ""

    OutlinedTextField(
        value = displayText,
        onValueChange = {},
        readOnly = true,
        label = { Text(label) },
        placeholder = { Text("Tap to set…") },
        modifier = Modifier.fillMaxWidth(),
        leadingIcon = { Icon(Icons.Default.CalendarToday, contentDescription = null) },
        trailingIcon = {
            if (epochMillis != null) {
                IconButton(onClick = onClear) {
                    Icon(Icons.Default.Clear, contentDescription = "Clear date")
                }
            } else {
                IconButton(onClick = { showDatePicker = true }) {
                    Icon(Icons.Default.Add, contentDescription = "Set date")
                }
            }
        }
    )

    // Date picker dialog
    if (showDatePicker) {
        val datePickerState = rememberDatePickerState(
            initialSelectedDateMillis = epochMillis ?: System.currentTimeMillis()
        )
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    showDatePicker = false
                    pendingDate = datePickerState.selectedDateMillis
                    showTimePicker = true
                }) { Text("Next: Time") }
            },
            dismissButton = {
                TextButton(onClick = { showDatePicker = false }) { Text("Cancel") }
            }
        ) {
            DatePicker(state = datePickerState)
        }
    }

    // Time picker dialog
    if (showTimePicker) {
        val existing = epochMillis?.let {
            LocalDateTime.ofInstant(Instant.ofEpochMilli(it), ZoneId.systemDefault())
        }
        val timePickerState = rememberTimePickerState(
            initialHour = existing?.hour ?: 9,
            initialMinute = existing?.minute ?: 0
        )
        AlertDialog(
            onDismissRequest = { showTimePicker = false },
            title = { Text("Select Time") },
            text = { TimePicker(state = timePickerState) },
            confirmButton = {
                TextButton(onClick = {
                    showTimePicker = false
                    pendingDate?.let { dateMillis ->
                        // Combine date (UTC midnight) with local time
                        val dateLdt = LocalDateTime.ofInstant(
                            Instant.ofEpochMilli(dateMillis), ZoneOffset.UTC
                        )
                        val combined = LocalDateTime.of(
                            dateLdt.year, dateLdt.month, dateLdt.dayOfMonth,
                            timePickerState.hour, timePickerState.minute
                        )
                        onDateSelected(combined.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli())
                    }
                    pendingDate = null
                }) { Text("Confirm") }
            },
            dismissButton = {
                TextButton(onClick = { showTimePicker = false; pendingDate = null }) { Text("Cancel") }
            }
        )
    }
}
