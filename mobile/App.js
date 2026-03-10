import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';

import DashboardScreen from './src/screens/DashboardScreen';
import PositionsScreen from './src/screens/PositionsScreen';
import IntelligenceScreen from './src/screens/IntelligenceScreen';
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
              Intelligence: focused ? 'brain' : 'bulb-outline',
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
          name="Settings"
          component={SettingsScreen}
          options={{ headerTitle: 'Bot Configuration' }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}
