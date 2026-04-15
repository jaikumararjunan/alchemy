package com.alchemy.taskapp.ai

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import com.alchemy.taskapp.data.Task
import com.alchemy.taskapp.data.TaskPriority
import com.alchemy.taskapp.data.TaskSource
import com.alchemy.taskapp.util.TaskJsonParser
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.suspendCancellableCoroutine
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

/**
 * Converts spoken audio into a structured [Task].
 *
 * Pipeline:
 *  1. **Android SpeechRecognizer** – converts audio to a transcript string.
 *  2. **Local LLM (Gemma 2B)** – interprets the transcript and returns a
 *     structured JSON task object.
 *  3. **JSON parser** – maps the JSON to a [Task] data class.
 *
 * Usage example:
 * ```kotlin
 * val transcriptFlow = voiceProcessor.startListening()
 * // Collect VoiceState events to update UI
 * transcriptFlow.collect { state ->
 *     when (state) {
 *         is VoiceState.Listening -> showMic()
 *         is VoiceState.Partial   -> showHint(state.text)
 *         is VoiceState.Done      -> handleTask(state.task)
 *         is VoiceState.Error     -> showError(state.message)
 *     }
 * }
 * ```
 */
@Singleton
class VoiceToTaskProcessor @Inject constructor(
    @ApplicationContext private val context: Context,
    private val llmManager: LocalLLMManager
) {
    companion object {
        private const val TAG = "VoiceToTaskProcessor"
    }

    /** Sealed class representing the real-time states emitted during voice capture. */
    sealed class VoiceState {
        /** SpeechRecognizer is actively listening. */
        object Listening : VoiceState()

        /** Partial transcript available (interim result). */
        data class Partial(val text: String) : VoiceState()

        /** Final transcript ready — LLM is processing. */
        data class Processing(val transcript: String) : VoiceState()

        /** Task successfully extracted from voice input. */
        data class Done(val task: Task, val transcript: String) : VoiceState()

        /** An error occurred during speech recognition or LLM processing. */
        data class Error(val message: String, val transcript: String? = null) : VoiceState()
    }

    /**
     * Starts the on-device speech recognizer and emits [VoiceState] events.
     * The flow completes after the final result (or an error).
     *
     * Must be called from the **main thread** (SpeechRecognizer requirement).
     */
    fun startListening(languageTag: String = "en-US"): Flow<VoiceState> = callbackFlow {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            trySend(VoiceState.Error("Speech recognition not available on this device."))
            close()
            return@callbackFlow
        }

        val recognizer = SpeechRecognizer.createSpeechRecognizer(context)

        recognizer.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) {
                trySend(VoiceState.Listening)
            }

            override fun onPartialResults(partialResults: Bundle?) {
                val partial = partialResults
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull() ?: return
                trySend(VoiceState.Partial(partial))
            }

            override fun onResults(results: Bundle?) {
                val transcript = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull() ?: run {
                    trySend(VoiceState.Error("No speech detected."))
                    close()
                    return
                }

                trySend(VoiceState.Processing(transcript))

                // Use the callbackFlow's own coroutine scope to avoid scope leaks.
                // `this` inside callbackFlow is a ProducerScope which is also a CoroutineScope.
                kotlinx.coroutines.launch(kotlinx.coroutines.Dispatchers.Default) {
                    val task = buildTaskFromTranscript(transcript)
                    trySend(VoiceState.Done(task, transcript))
                    close()
                }
            }

            override fun onError(error: Int) {
                val msg = speechErrorMessage(error)
                Log.e(TAG, "SpeechRecognizer error: $msg ($error)")
                trySend(VoiceState.Error(msg))
                close()
            }

            // Unused callbacks
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(eventType: Int, params: Bundle?) {}
        })

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, languageTag)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }

        recognizer.startListening(intent)

        awaitClose {
            recognizer.stopListening()
            recognizer.destroy()
        }
    }

    // ── LLM task extraction ───────────────────────────────────────────────────

    private suspend fun buildTaskFromTranscript(transcript: String): Task {
        if (!llmManager.isReady) {
            return buildFallbackTask(transcript)
        }

        val prompt = buildVoicePrompt(transcript)
        return llmManager.generateText(prompt).map { json ->
            TaskJsonParser.parseTaskJson(json).copy(source = TaskSource.VOICE)
        }.getOrElse {
            Log.w(TAG, "LLM parse failed, using fallback: ${it.message}")
            buildFallbackTask(transcript)
        }
    }

    private fun buildVoicePrompt(transcript: String): String = """
<start_of_turn>user
You are a task management assistant. Convert the following voice transcript into a structured task.

Transcript:
\"\"\"
$transcript
\"\"\"

Output ONLY valid JSON with these exact keys (use null for missing values):
{
  "title": "short task title",
  "description": "detailed description",
  "priority": "LOW|MEDIUM|HIGH|URGENT",
  "assignedTo": "name or null",
  "assignedBy": "name or null",
  "dueDate": "YYYY-MM-DDTHH:mm:ss or null",
  "tags": "comma separated tags or empty string"
}
<end_of_turn>
<start_of_turn>model
""".trimIndent()

    private fun buildFallbackTask(transcript: String): Task {
        val title = transcript.take(80).ifBlank { "Voice task" }
        return Task(
            title = title,
            description = transcript,
            source = TaskSource.VOICE,
            priority = TaskPriority.MEDIUM
        )
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private fun speechErrorMessage(error: Int): String = when (error) {
        SpeechRecognizer.ERROR_AUDIO -> "Audio recording error"
        SpeechRecognizer.ERROR_CLIENT -> "Client side error"
        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Microphone permission denied"
        SpeechRecognizer.ERROR_NETWORK -> "Network error (check connection)"
        SpeechRecognizer.ERROR_NETWORK_TIMEOUT -> "Network timeout"
        SpeechRecognizer.ERROR_NO_MATCH -> "No speech matched"
        SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> "Recognition service busy"
        SpeechRecognizer.ERROR_SERVER -> "Server error"
        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "No speech input"
        else -> "Unknown error ($error)"
    }
}


