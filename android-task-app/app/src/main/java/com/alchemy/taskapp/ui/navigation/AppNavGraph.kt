package com.alchemy.taskapp.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.alchemy.taskapp.ui.screens.CreateTaskScreen
import com.alchemy.taskapp.ui.screens.TaskDetailScreen
import com.alchemy.taskapp.ui.screens.TaskListScreen

/** All app routes as constants to avoid stringly-typed bugs. */
object Routes {
    const val TASK_LIST = "task_list"
    const val TASK_DETAIL = "task_detail/{taskId}"
    const val CREATE_TASK = "create_task"
    const val EDIT_TASK = "edit_task/{taskId}"

    fun taskDetail(taskId: String) = "task_detail/$taskId"
    fun editTask(taskId: String) = "edit_task/$taskId"
}

@Composable
fun AppNavGraph(
    navController: NavHostController = rememberNavController()
) {
    NavHost(
        navController = navController,
        startDestination = Routes.TASK_LIST
    ) {
        composable(Routes.TASK_LIST) {
            TaskListScreen(
                onNavigateToCreate = { navController.navigate(Routes.CREATE_TASK) },
                onNavigateToDetail = { id -> navController.navigate(Routes.taskDetail(id)) }
            )
        }

        composable(
            route = Routes.TASK_DETAIL,
            arguments = listOf(navArgument("taskId") { type = NavType.StringType })
        ) { backStackEntry ->
            val taskId = backStackEntry.arguments?.getString("taskId") ?: return@composable
            TaskDetailScreen(
                taskId = taskId,
                onNavigateBack = { navController.popBackStack() },
                onNavigateToEdit = { id -> navController.navigate(Routes.editTask(id)) }
            )
        }

        composable(Routes.CREATE_TASK) {
            CreateTaskScreen(
                taskId = null,
                onNavigateBack = { navController.popBackStack() }
            )
        }

        composable(
            route = Routes.EDIT_TASK,
            arguments = listOf(navArgument("taskId") { type = NavType.StringType })
        ) { backStackEntry ->
            val taskId = backStackEntry.arguments?.getString("taskId") ?: return@composable
            CreateTaskScreen(
                taskId = taskId,
                onNavigateBack = { navController.popBackStack() }
            )
        }
    }
}
