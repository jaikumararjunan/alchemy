package com.alchemy.taskapp

import com.alchemy.taskapp.data.Task
import com.alchemy.taskapp.data.TaskPriority
import com.alchemy.taskapp.data.TaskSource
import com.alchemy.taskapp.data.TaskStatus
import com.alchemy.taskapp.util.TaskJsonParser
import org.junit.Assert.*
import org.junit.Test

class TaskJsonParserTest {

    @Test
    fun `parses well-formed JSON correctly`() {
        val json = """
            {
              "title": "Fix login bug",
              "description": "The login button is broken on Android 14",
              "priority": "HIGH",
              "assignedTo": "Alice",
              "assignedBy": "Bob",
              "dueDate": "2025-06-15T14:30:00",
              "tags": "bug,android,urgent"
            }
        """.trimIndent()

        val task = TaskJsonParser.parseTaskJson(json)

        assertEquals("Fix login bug", task.title)
        assertEquals("The login button is broken on Android 14", task.description)
        assertEquals(TaskPriority.HIGH, task.priority)
        assertEquals("Alice", task.assignedTo)
        assertEquals("Bob", task.assignedBy)
        assertNotNull(task.dueDate)
        assertEquals("bug,android,urgent", task.tags)
    }

    @Test
    fun `handles JSON embedded in extra LLM text`() {
        val raw = """
            Sure! Here is the task JSON:
            {
              "title": "Deploy to production",
              "description": "Deploy the new version",
              "priority": "URGENT",
              "assignedTo": null,
              "assignedBy": null,
              "dueDate": null,
              "tags": "deploy"
            }
            Let me know if you need anything else.
        """.trimIndent()

        val task = TaskJsonParser.parseTaskJson(raw)

        assertEquals("Deploy to production", task.title)
        assertEquals(TaskPriority.URGENT, task.priority)
        assertEquals("", task.assignedTo)   // null → empty string
    }

    @Test
    fun `falls back gracefully on empty input`() {
        val task = TaskJsonParser.parseTaskJson("")
        assertEquals("Task", task.title)
    }

    @Test
    fun `falls back gracefully on no JSON`() {
        val task = TaskJsonParser.parseTaskJson("No JSON here at all")
        assertEquals("Task", task.title)
    }

    @Test
    fun `defaults priority to MEDIUM on unknown value`() {
        val json = """{"title": "My task", "priority": "EXTREME", "description": ""}"""
        val task = TaskJsonParser.parseTaskJson(json)
        assertEquals(TaskPriority.MEDIUM, task.priority)
    }

    @Test
    fun `parses date-only format`() {
        val json = """{"title": "Review PR", "dueDate": "2025-12-01", "priority": "LOW", "description": ""}"""
        val task = TaskJsonParser.parseTaskJson(json)
        assertNotNull(task.dueDate)
    }
}

class TaskEntityTest {

    @Test
    fun `tagList splits correctly`() {
        val task = Task(title = "Test", tags = "urgent,  finance , Q1 ")
        assertEquals(listOf("urgent", "finance", "Q1"), task.tagList())
    }

    @Test
    fun `tagList returns empty list for blank tags`() {
        val task = Task(title = "Test", tags = "")
        assertTrue(task.tagList().isEmpty())
    }

    @Test
    fun `dueDateLocal returns null when no due date`() {
        val task = Task(title = "Test")
        assertNull(task.dueDateLocal())
    }

    @Test
    fun `dueDateLocal returns non-null for set due date`() {
        val epochMillis = System.currentTimeMillis() + 86_400_000L  // tomorrow
        val task = Task(title = "Test", dueDate = epochMillis)
        assertNotNull(task.dueDateLocal())
    }

    @Test
    fun `default task has PENDING status and MANUAL source`() {
        val task = Task(title = "New")
        assertEquals(TaskStatus.PENDING, task.status)
        assertEquals(TaskSource.MANUAL, task.source)
        assertEquals(TaskPriority.MEDIUM, task.priority)
    }

    @Test
    fun `task id is auto-generated and unique`() {
        val t1 = Task(title = "A")
        val t2 = Task(title = "B")
        assertNotEquals(t1.id, t2.id)
    }
}
