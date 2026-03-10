import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';

import DashboardScreen from './src/screens/DashboardScreen';
import PositionsScreen from './src/screens/PositionsScreen';
import IntelligenceScreen from './src/screens/IntelligenceScreen';
import ForecastScreen from './src/screens/ForecastScreen';
import MLScreen from './src/screens/MLScreen';
import DerivativesScreen from './src/screens/DerivativesScreen';
import ScannerScreen from './src/screens/ScannerScreen';
import SettingsScreen from './src/screens/SettingsScreen';
import { colors } from './src/theme';

const Tab = createBottomTabNavigator();

export default function App() {
  return (
    <NavigationContainer theme={{ colors: { background: colors.bg } }}>
      <StatusBar style="light" />
      <Tab.Navigator
        screenOptions={({ route }) => ({
          tabBarIcon: ({ focused, color, size }) => {
            const icons = {
              Dashboard: focused ? 'home' : 'home-outline',
              Positions: focused ? 'analytics' : 'analytics-outline',
              Intelligence: focused ? 'bulb' : 'bulb-outline',
              Forecast: focused ? 'trending-up' : 'trending-up-outline',
              'ML/AI': focused ? 'hardware-chip' : 'hardware-chip-outline',
              Derivatives: focused ? 'bar-chart' : 'bar-chart-outline',
              Scanner: focused ? 'search' : 'search-outline',
              Settings: focused ? 'settings' : 'settings-outline',
            };
            return <Ionicons name={icons[route.name] || 'home-outline'} size={size} color={color} />;
          },
          tabBarActiveTintColor: colors.accent,
          tabBarInactiveTintColor: colors.text3,
          tabBarStyle: {
            backgroundColor: colors.bg2,
            borderTopColor: colors.border,
            paddingBottom: 4,
            height: 60,
          },
          tabBarLabelStyle: { fontSize: 10, fontWeight: '600' },
          headerStyle: { backgroundColor: colors.bg2, borderBottomColor: colors.border, borderBottomWidth: 1 },
          headerTintColor: colors.text,
          headerTitleStyle: { fontWeight: '700', fontSize: 16 },
          headerRight: () => null,
        })}
      >
        <Tab.Screen
          name="Dashboard"
          component={DashboardScreen}
          options={{ headerTitle: 'ALCHEMY  ·  Autonomous AI Trader' }}
        />
        <Tab.Screen
          name="Positions"
          component={PositionsScreen}
          options={{ headerTitle: 'Positions & Trade History' }}
        />
        <Tab.Screen
          name="Intelligence"
          component={IntelligenceScreen}
          options={{ headerTitle: 'Emotion Intelligence' }}
        />
        <Tab.Screen
          name="Forecast"
          component={ForecastScreen}
          options={{ headerTitle: 'Market Forecast & Technicals' }}
        />
        <Tab.Screen
          name="ML/AI"
          component={MLScreen}
          options={{ headerTitle: 'ML / AI Analysis Engine' }}
        />
        <Tab.Screen
          name="Derivatives"
          component={DerivativesScreen}
          options={{ headerTitle: 'Derivatives Intelligence' }}
        />
        <Tab.Screen
          name="Scanner"
          component={ScannerScreen}
          options={{ headerTitle: 'Contract Scanner · All Markets' }}
        />
        <Tab.Screen
          name="Settings"
          component={SettingsScreen}
          options={{ headerTitle: 'Bot Configuration' }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
