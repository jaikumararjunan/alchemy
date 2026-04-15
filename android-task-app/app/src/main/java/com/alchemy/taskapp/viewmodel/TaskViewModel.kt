package com.alchemy.taskapp.viewmodel

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.alchemy.taskapp.ai.ImageToTaskProcessor
import com.alchemy.taskapp.ai.LocalLLMManager
import com.alchemy.taskapp.ai.VoiceToTaskProcessor
import com.alchemy.taskapp.data.Task
import com.alchemy.taskapp.data.TaskPriority
import com.alchemy.taskapp.data.TaskRepository
import com.alchemy.taskapp.data.TaskSource
import com.alchemy.taskapp.data.TaskStatus
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import java.time.Instant
import javax.inject.Inject

/** Immutable snapshot of the task-list screen state. */
data class TaskListUiState(
    val tasks: List<Task> = emptyList(),
    val filterStatus: TaskStatus? = null,
    val searchQuery: String = "",
    val isLoading: Boolean = false,
    val llmReady: Boolean = false,
    val llmInitialising: Boolean = false,
    val snackbarMessage: String? = null
)

/** Immutable snapshot of the task-creation/edit screen state. */
data class TaskFormUiState(
    val task: Task = Task(title = ""),
    val isProcessingAi: Boolean = false,
    val voiceState: VoiceToTaskProcessor.VoiceState? = null,
    val isSaving: Boolean = false,
    val savedSuccessfully: Boolean = false,
    val errorMessage: String? = null
)

@HiltViewModel
class TaskViewModel @Inject constructor(
    private val repository: TaskRepository,
    private val llmManager: LocalLLMManager,
    private val imageProcessor: ImageToTaskProcessor,
    private val voiceProcessor: VoiceToTaskProcessor
) : ViewModel() {

    // ── List State ────────────────────────────────────────────────────────────

    private val _listState = MutableStateFlow(TaskListUiState())
    val listState: StateFlow<TaskListUiState> = _listState.asStateFlow()

    // ── Form State ────────────────────────────────────────────────────────────

    private val _formState = MutableStateFlow(TaskFormUiState())
    val formState: StateFlow<TaskFormUiState> = _formState.asStateFlow()

    init {
        observeTasks()
        initialiseLlm()
    }

    // ── LLM init ──────────────────────────────────────────────────────────────

    private fun initialiseLlm() {
        viewModelScope.launch {
            _listState.update { it.copy(llmInitialising = true) }
            val ready = llmManager.initialize()
            _listState.update { it.copy(llmReady = ready, llmInitialising = false) }
        }
    }

    // ── Task list ─────────────────────────────────────────────────────────────

    private fun observeTasks() {
        viewModelScope.launch {
            repository.getAllTasks()
                .catch { e ->
                    _listState.update { it.copy(snackbarMessage = "Load error: ${e.message}") }
                }
                .collect { tasks ->
                    val query = _listState.value.searchQuery
                    val filtered = applyFilter(tasks, query, _listState.value.filterStatus)
                    _listState.update { it.copy(tasks = filtered, isLoading = false) }
                }
        }
    }

    fun setSearchQuery(query: String) {
        _listState.update { it.copy(searchQuery = query) }
        viewModelScope.launch {
            repository.getAllTasks().first().let { tasks ->
                _listState.update {
                    it.copy(tasks = applyFilter(tasks, query, it.filterStatus))
                }
            }
        }
    }

    fun setStatusFilter(status: TaskStatus?) {
        _listState.update { it.copy(filterStatus = status) }
        viewModelScope.launch {
            repository.getAllTasks().first().let { tasks ->
                _listState.update {
                    it.copy(tasks = applyFilter(tasks, it.searchQuery, status))
                }
            }
        }
    }

    private fun applyFilter(
        tasks: List<Task>,
        query: String,
        status: TaskStatus?
    ): List<Task> {
        var result = tasks
        if (status != null) result = result.filter { it.status == status }
        if (query.isNotBlank()) {
            val q = query.lowercase()
            result = result.filter {
                it.title.lowercase().contains(q) ||
                        it.description.lowercase().contains(q) ||
                        it.assignedTo.lowercase().contains(q) ||
                        it.tags.lowercase().contains(q)
            }
        }
        return result
    }

    fun deleteTask(task: Task) {
        viewModelScope.launch {
            repository.deleteTask(task)
            _listState.update { it.copy(snackbarMessage = "Task deleted") }
        }
    }

    fun toggleTaskDone(task: Task) {
        viewModelScope.launch {
            val newStatus = if (task.status == TaskStatus.DONE) TaskStatus.PENDING else TaskStatus.DONE
            repository.updateStatus(task.id, newStatus)
        }
    }

    fun clearSnackbar() = _listState.update { it.copy(snackbarMessage = null) }

    // ── Task form ─────────────────────────────────────────────────────────────

    fun loadTaskForEdit(taskId: String) {
        viewModelScope.launch {
            repository.getTaskById(taskId).firstOrNull()?.let { task ->
                _formState.update { it.copy(task = task) }
            }
        }
    }

    fun resetForm(prefillSource: TaskSource = TaskSource.MANUAL) {
        _formState.value = TaskFormUiState(task = Task(title = "", source = prefillSource))
    }

    fun updateTitle(title: String) =
        _formState.update { it.copy(task = it.task.copy(title = title)) }

    fun updateDescription(desc: String) =
        _formState.update { it.copy(task = it.task.copy(description = desc)) }

    fun updatePriority(priority: TaskPriority) =
        _formState.update { it.copy(task = it.task.copy(priority = priority)) }

    fun updateStatus(status: TaskStatus) =
        _formState.update { it.copy(task = it.task.copy(status = status)) }

    fun updateAssignedTo(name: String) =
        _formState.update { it.copy(task = it.task.copy(assignedTo = name)) }

    fun updateAssignedBy(name: String) =
        _formState.update { it.copy(task = it.task.copy(assignedBy = name)) }

    fun updateDueDate(epochMillis: Long?) =
        _formState.update { it.copy(task = it.task.copy(dueDate = epochMillis)) }

    fun updateReminderDate(epochMillis: Long?) =
        _formState.update { it.copy(task = it.task.copy(reminderDate = epochMillis)) }

    fun updateTags(tags: String) =
        _formState.update { it.copy(task = it.task.copy(tags = tags)) }

    fun saveTask() {
        val current = _formState.value.task
        if (current.title.isBlank()) {
            _formState.update { it.copy(errorMessage = "Title is required") }
            return
        }
        viewModelScope.launch {
            _formState.update { it.copy(isSaving = true) }
            try {
                repository.saveTask(current.copy(updatedAt = Instant.now().toEpochMilli()))
                _formState.update { it.copy(isSaving = false, savedSuccessfully = true) }
            } catch (e: Exception) {
                _formState.update {
                    it.copy(isSaving = false, errorMessage = "Save failed: ${e.message}")
                }
            }
        }
    }

    fun clearFormError() = _formState.update { it.copy(errorMessage = null) }

    // ── Image → Task ──────────────────────────────────────────────────────────

    fun processImage(imageUri: Uri) {
        viewModelScope.launch {
            _formState.update { it.copy(isProcessingAi = true, errorMessage = null) }
            imageProcessor.process(imageUri)
                .onSuccess { extracted ->
                    _formState.update {
                        it.copy(isProcessingAi = false, task = extracted)
                    }
                }
                .onFailure { e ->
                    _formState.update {
                        it.copy(
                            isProcessingAi = false,
                            errorMessage = "Image processing failed: ${e.message}"
                        )
                    }
                }
        }
    }

    // ── Voice → Task ──────────────────────────────────────────────────────────

    fun startVoiceCapture() {
        viewModelScope.launch {
            voiceProcessor.startListening().collect { state ->
                _formState.update { it.copy(voiceState = state) }
                when (state) {
                    is VoiceToTaskProcessor.VoiceState.Done -> {
                        _formState.update {
                            it.copy(
                                task = state.task,
                                isProcessingAi = false,
                                voiceState = null
                            )
                        }
                    }
                    is VoiceToTaskProcessor.VoiceState.Error -> {
                        _formState.update {
                            it.copy(
                                isProcessingAi = false,
                                voiceState = null,
                                errorMessage = state.message
                            )
                        }
                    }
                    is VoiceToTaskProcessor.VoiceState.Processing -> {
                        _formState.update { it.copy(isProcessingAi = true) }
                    }
                    else -> {}
                }
            }
        }
    }

    override fun onCleared() {
        super.onCleared()
        llmManager.release()
    }
}

// Uses kotlinx.coroutines.flow.firstOrNull() which is provided by the coroutines library
