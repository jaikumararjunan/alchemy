package com.alchemy.taskapp.ai

import android.content.Context
import android.util.Log
import com.google.mediapipe.tasks.genai.llminference.LlmInference
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Manages the on-device Gemma 2B LLM via MediaPipe Tasks GenAI.
 *
 * ## Model setup
 * Place the quantised Gemma 2B model file (e.g. `gemma-2b-it-gpu-int4.bin` or
 * `gemma-2b-it-cpu-int4.bin`) inside the app's `assets/models/` directory at build time,
 * or download it once and cache it in [Context.getFilesDir].
 *
 * Supported model files (pick one):
 *   - gemma-2b-it-gpu-int4.bin   (~1.3 GB)  — GPU-accelerated (recommended for Vulkan devices)
 *   - gemma-2b-it-cpu-int4.bin   (~1.3 GB)  — CPU-only fallback
 *
 * Download from: https://www.kaggle.com/models/google/gemma/frameworks/tfLite
 * (requires a free Kaggle account)
 */
@Singleton
class LocalLLMManager @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        private const val TAG = "LocalLLMManager"

        // File name expected in the app's internal files/models/ directory
        private const val MODEL_FILE = "gemma-2b-it-gpu-int4.bin"
        private const val MODEL_FALLBACK = "gemma-2b-it-cpu-int4.bin"

        // Inference parameters
        private const val MAX_TOKENS = 1024
        private const val TEMPERATURE = 0.7f
        private const val TOP_K = 40
    }

    @Volatile
    private var llmInference: LlmInference? = null

    /** True when the model is loaded and ready to use. */
    val isReady: Boolean get() = llmInference != null

    /**
     * Loads the LLM model from the app's internal storage.
     * Call once (e.g. in a splash/init coroutine) before using [generateText].
     *
     * @return true on success, false if the model file is not found.
     */
    suspend fun initialize(): Boolean = withContext(Dispatchers.IO) {
        if (llmInference != null) return@withContext true

        val modelFile = resolveModelFile() ?: run {
            Log.w(TAG, "Model file not found. Copy $MODEL_FILE to ${modelDir().absolutePath}")
            return@withContext false
        }

        return@withContext try {
            val options = LlmInference.LlmInferenceOptions.builder()
                .setModelPath(modelFile.absolutePath)
                .setMaxTokens(MAX_TOKENS)
                .setTemperature(TEMPERATURE)
                .setTopK(TOP_K)
                .build()

            llmInference = LlmInference.createFromOptions(context, options)
            Log.i(TAG, "LLM loaded: ${modelFile.name}")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load LLM: ${e.message}", e)
            false
        }
    }

    /**
     * Generates a response for the given [prompt] and returns it as a cold [Flow]
     * that emits text tokens progressively (streaming).
     */
    fun generateTextStream(prompt: String): Flow<String> = callbackFlow {
        val llm = llmInference
        if (llm == null) {
            close(IllegalStateException("LLM not initialised. Call initialize() first."))
            return@callbackFlow
        }
        try {
            llm.generateResponseAsync(prompt) { partialResult, done ->
                trySend(partialResult)
                if (done) close()
            }
        } catch (e: Exception) {
            close(e)
        }
        awaitClose()
    }

    /**
     * Generates a complete response (non-streaming) for the given [prompt].
     */
    suspend fun generateText(prompt: String): Result<String> = withContext(Dispatchers.Default) {
        val llm = llmInference
            ?: return@withContext Result.failure(IllegalStateException("LLM not initialised. Call initialize() first."))
        return@withContext try {
            val response = llm.generateResponse(prompt)
            Result.success(response)
        } catch (e: Exception) {
            Log.e(TAG, "LLM inference failed: ${e.message}", e)
            Result.failure(e)
        }
    }

    /** Releases the model from memory. Call when the app goes to background for an extended time. */
    fun release() {
        llmInference?.close()
        llmInference = null
        Log.i(TAG, "LLM released")
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /** Returns the directory where model files are stored on internal storage. */
    fun modelDir(): File = File(context.filesDir, "models").also { it.mkdirs() }

    private fun resolveModelFile(): File? {
        val dir = modelDir()
        for (name in listOf(MODEL_FILE, MODEL_FALLBACK)) {
            val f = File(dir, name)
            if (f.exists()) return f
        }
        return null
    }
}
