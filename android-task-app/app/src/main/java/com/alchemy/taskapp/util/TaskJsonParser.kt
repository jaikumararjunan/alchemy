package com.alchemy.taskapp.util

import android.util.Log
import com.alchemy.taskapp.data.Task
import com.alchemy.taskapp.data.TaskPriority
import org.json.JSONObject
import java.time.LocalDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.time.format.DateTimeParseException

/**
 * Parses the JSON returned by the local LLM into a [Task] object.
 *
 * The LLM is prompted to return strict JSON, but it may include extra text
 * before/after the braces. This parser extracts the first valid JSON object.
 */
object TaskJsonParser {

    private const val TAG = "TaskJsonParser"

    private val DATE_FORMATS = listOf(
        DateTimeFormatter.ISO_LOCAL_DATE_TIME,          // 2025-06-15T14:30:00
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"),
        DateTimeFormatter.ofPattern("yyyy-MM-dd"),
    )

    /**
     * Parses a JSON string (possibly embedded in extra text) into a [Task].
     * Falls back to a minimal task with the raw text as description on failure.
     */
    fun parseTaskJson(rawResponse: String): Task {
        val json = extractJsonObject(rawResponse) ?: run {
            Log.w(TAG, "No JSON object found in response")
            return Task(title = "Task", description = rawResponse.take(500))
        }

        return try {
            val title = json.optString("title", "").ifBlank { "Untitled Task" }
            val description = json.optString("description", "")
            val priorityStr = json.optString("priority", "MEDIUM").uppercase()
            val assignedTo = json.optString("assignedTo", "").takeUnless { it == "null" } ?: ""
            val assignedBy = json.optString("assignedBy", "").takeUnless { it == "null" } ?: ""
            val dueDateStr = json.optString("dueDate", "").takeUnless { it == "null" }
            val tags = json.optString("tags", "")

            val priority = runCatching { TaskPriority.valueOf(priorityStr) }
                .getOrDefault(TaskPriority.MEDIUM)

            val dueDate = dueDateStr?.let { parseDateToEpochMillis(it) }

            Task(
                title = title.take(200),
                description = description.take(2000),
                priority = priority,
                assignedTo = assignedTo.take(100),
                assignedBy = assignedBy.take(100),
                dueDate = dueDate,
                tags = tags.take(200)
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to map JSON to Task: ${e.message}", e)
            Task(title = "Parsed Task", description = rawResponse.take(500))
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Finds the first `{...}` JSON object within [text], even if there is
     * surrounding LLM preamble text.
     */
    private fun extractJsonObject(text: String): JSONObject? {
        val start = text.indexOf('{')
        val end = text.lastIndexOf('}')
        if (start == -1 || end == -1 || end <= start) return null
        return try {
            JSONObject(text.substring(start, end + 1))
        } catch (e: Exception) {
            Log.w(TAG, "JSON parse error: ${e.message}")
            null
        }
    }

    private fun parseDateToEpochMillis(dateStr: String): Long? {
        for (fmt in DATE_FORMATS) {
            try {
                return LocalDateTime.parse(dateStr, fmt)
                    .toInstant(ZoneOffset.UTC)
                    .toEpochMilli()
            } catch (_: DateTimeParseException) {
                // try next format
            }
        }
        Log.w(TAG, "Could not parse date: $dateStr")
        return null
    }
}
