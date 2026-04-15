package com.alchemy.taskapp

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.alchemy.taskapp.ui.navigation.AppNavGraph
import com.alchemy.taskapp.ui.theme.AlchemyTaskTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AlchemyTaskTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    AppNavGraph()
                }
            }
        }
    }
}
