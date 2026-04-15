package com.alchemy.taskapp.ai

import android.content.Context
import android.net.Uri
import android.util.Log
import com.alchemy.taskapp.data.Task
import com.alchemy.taskapp.data.TaskPriority
import com.alchemy.taskapp.data.TaskSource
import com.alchemy.taskapp.util.TaskJsonParser
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.suspendCancellableCoroutine
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume

/**
 * Converts a photo / gallery image into a structured [Task].
 *
 * Pipeline:
 *  1. **ML Kit OCR** – extracts all visible text from the image.
 *  2. **Local LLM (Gemma 2B)** – interprets the extracted text and returns a
 *     structured JSON task object.
 *  3. **JSON parser** – maps the JSON to a [Task] data class.
 */
@Singleton
class ImageToTaskProcessor @Inject constructor(
    @ApplicationContext private val context: Context,
    private val llmManager: LocalLLMManager
) {
    companion object {
        private const val TAG = "ImageToTaskProcessor"
    }

    private val textRecognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    /**
     * Processes [imageUri] and returns a partially-filled [Task] ready for user review.
     */
    suspend fun process(imageUri: Uri): Result<Task> {
        // Step 1 – OCR
        val ocrText = extractText(imageUri).getOrElse { e ->
            Log.e(TAG, "OCR failed", e)
            return Result.failure(e)
        }

        if (ocrText.isBlank()) {
            return Result.failure(IllegalArgumentException("No text found in image."))
        }

        Log.d(TAG, "OCR extracted: $ocrText")

        // Step 2 – LLM structured extraction
        if (!llmManager.isReady) {
            // Graceful fallback: create a minimal task from raw OCR text
            return Result.success(buildFallbackTask(ocrText, imageUri))
        }

        val prompt = buildImagePrompt(ocrText)
        val llmResult = llmManager.generateText(prompt)

        return llmResult.map { json ->
            TaskJsonParser.parseTaskJson(json)
                .copy(source = TaskSource.IMAGE, imageUri = imageUri.toString())
        }.recoverCatching { e ->
            Log.w(TAG, "LLM parse failed, using OCR fallback: ${e.message}")
            buildFallbackTask(ocrText, imageUri)
        }
    }

    // ── OCR ───────────────────────────────────────────────────────────────────

    private suspend fun extractText(imageUri: Uri): Result<String> =
        suspendCancellableCoroutine { cont ->
            try {
                val image = InputImage.fromFilePath(context, imageUri)
                textRecognizer.process(image)
                    .addOnSuccessListener { visionText ->
                        cont.resume(Result.success(visionText.text))
                    }
                    .addOnFailureListener { e ->
                        cont.resume(Result.failure(e))
                    }
            } catch (e: Exception) {
                cont.resume(Result.failure(e))
            }
        }

    // ── Prompts ───────────────────────────────────────────────────────────────

    /**
     * Prompt instructs the LLM to extract a structured task from OCR text.
     * We request strict JSON so it's machine-parseable without extra formatting.
     */
    private fun buildImagePrompt(ocrText: String): String = """
<start_of_turn>user
You are a task extraction assistant. Analyse the following text extracted from an image and output a single JSON object describing the task. 

Text from image:
\"\"\"
$ocrText
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

    // ── Fallback ──────────────────────────────────────────────────────────────

    private fun buildFallbackTask(ocrText: String, imageUri: Uri): Task {
        val title = ocrText.lines().firstOrNull { it.isNotBlank() }
            ?.take(80) ?: "Task from image"
        return Task(
            title = title,
            description = ocrText.take(1000),
            source = TaskSource.IMAGE,
            imageUri = imageUri.toString(),
            priority = TaskPriority.MEDIUM
        )
    }
}
