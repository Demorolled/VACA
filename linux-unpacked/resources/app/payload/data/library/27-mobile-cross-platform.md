# 📱 Mobile & Cross-Platform Development

> Reference for building mobile applications and cross-platform solutions — native iOS/Android, React Native, Flutter, and mobile architecture patterns.
> Extracted from The Programming Bible's Mobile/Cross-Platform level.

---

## 1. Platform Comparison

| Aspect | iOS (Swift) | Android (Kotlin) | React Native | Flutter |
|---|---|---|---|---|
| **Language** | Swift | Kotlin, Java | JavaScript/TypeScript | Dart |
| **UI Framework** | SwiftUI / UIKit | Jetpack Compose | React components | Widget-based |
| **Rendering** | Native | Native | Native components | Skia/Impeller engine |
| **Performance** | Native | Native | Near-native | Native |
| **Code Sharing** | iOS only | Android only | Up to 95% cross-platform | 100% single codebase |
| **Hot Reload** | Xcode Previews | Compose Preview | Fast Refresh | Hot Reload |
| **Learning Curve** | Medium | Medium | Low (if know React) | Medium (new language) |

### Platform Decision Tree

```
Need maximum native performance?
├── Yes → iOS native (Swift/SwiftUI) OR Android native (Kotlin/Compose)
└── No → Need shared code across platforms?
    ├── Yes → Experience with React?
    │   ├── Yes → React Native (TypeScript)
    │   └── No → Flutter (Dart) — best cross-platform experience
    └── No → Build separate native apps
```

---

## 2. React Native Architecture

### Thread Architecture

```
┌─────────────────────────────────────────────┐
│             React Native App                 │
│                                               │
│  ┌──────────────┐  ┌──────────────────────┐ │
│  │ JS Thread    │  │  Native/Main Thread   │ │
│  │              │  │                       │ │
│  │ React Code   │  │  UI Components        │ │
│  │ Business Logic│  │  Gesture Handling    │ │
│  │ State Mgmt   │  │  Platform APIs        │ │
│  │ API Calls    │  │                       │ │
│  └──────┬───────┘  └──────────┬───────────┘ │
│         │                    │               │
│         └─────────┬──────────┘               │
│                   │                          │
│         ┌─────────▼─────────┐                │
│         │  JSI (C++ Layer)  │                │
│         │  Direct, sync     │                │
│         │  communication    │                │
│         └───────────────────┘                │
└─────────────────────────────────────────────┘
```

### React Native Component Patterns

```typescript
import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  RefreshControl,
  Alert,
} from 'react-native';

// Screen-level component
interface User {
  id: string;
  name: string;
  email: string;
  avatar: string;
}

function UserListScreen() {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchUsers = useCallback(async () => {
    try {
      const response = await fetch('/api/users');
      const data = await response.json();
      setUsers(data);
    } catch (err) {
      Alert.alert('Error', 'Failed to load users');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    fetchUsers();
  }, [fetchUsers]);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  return (
    <FlatList
      data={users}
      keyExtractor={item => item.id}
      renderItem={({ item }) => (
        <TouchableOpacity style={styles.card} onPress={() => handleUserPress(item)}>
          <View style={styles.avatar} />
          <View style={styles.info}>
            <Text style={styles.name}>{item.name}</Text>
            <Text style={styles.email}>{item.email}</Text>
          </View>
        </TouchableOpacity>
      )}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    />
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  card: { flexDirection: 'row', padding: 16, borderBottomWidth: 1, borderColor: '#eee' },
  avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: '#ddd' },
  info: { marginLeft: 12, justifyContent: 'center' },
  name: { fontSize: 16, fontWeight: '600' },
  email: { fontSize: 14, color: '#666', marginTop: 2 },
});
```

### Navigation Pattern

```typescript
// React Navigation setup
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';

type RootStackParams = {
  Home: undefined;
  Profile: { userId: string };
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParams>();
const Tab = createBottomTabNavigator();

function RootNavigator() {
  return (
    <NavigationContainer>
      <Tab.Navigator screenOptions={{ headerShown: false }}>
        <Tab.Screen name="Home" component={HomeStack} />
        <Tab.Screen name="Search" component={SearchScreen} />
        <Tab.Screen name="Profile" component={ProfileStack} />
      </Tab.Navigator>
    </NavigationContainer>
  );
}

function HomeStack() {
  return (
    <Stack.Navigator>
      <Stack.Screen name="Home" component={UserListScreen} />
      <Stack.Screen name="Profile" component={UserDetailScreen} />
    </Stack.Navigator>
  );
}
```

---

## 3. Flutter Architecture

### Flutter Widget Tree

```
MaterialApp
└── Scaffold
    ├── AppBar
    │   └── Text("My App")
    └── Body
        └── ListView
            ├── ListTile(title: Text("Item 1"))
            ├── ListTile(title: Text("Item 2"))
            └── ListTile(title: Text("Item 3"))
```

### Flutter Patterns

```dart
import 'package:flutter/material.dart';

// Stateful widget example
class UserListWidget extends StatefulWidget {
  const UserListWidget({super.key});

  @override
  State<UserListWidget> createState() => _UserListWidgetState();
}

class _UserListWidgetState extends State<UserListWidget> {
  List<User> _users = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadUsers();
  }

  Future<void> _loadUsers() async {
    try {
      final response = await fetchUsers();
      setState(() {
        _users = response;
        _loading = false;
        _error = null;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.error_outline, size: 48, color: Colors.red),
            const SizedBox(height: 16),
            Text('Error: $_error'),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadUsers,
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _loadUsers,
      child: ListView.builder(
        itemCount: _users.length,
        itemBuilder: (context, index) {
          final user = _users[index];
          return Card(
            child: ListTile(
              leading: CircleAvatar(child: Text(user.name[0])),
              title: Text(user.name),
              subtitle: Text(user.email),
              onTap: () => _navigateToProfile(context, user.id),
            ),
          );
        },
      ),
    );
  }
}
```

---

## 4. Mobile Architecture Patterns

### Offline-First with Local Storage

```typescript
// SQLite local storage for offline support
import Database from 'better-sqlite3';

class OfflineStore {
  private db: Database.Database;

  constructor() {
    this.db = new Database('app.db');
    this.initialize();
  }

  private initialize(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS sync_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        operation TEXT NOT NULL CHECK(operation IN ('create','update','delete')),
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        synced INTEGER NOT NULL DEFAULT 0
      )
    `);
  }

  // Save data locally (always)
  saveLocal(entity: string, id: string, data: unknown): void {
    this.db.prepare(`
      INSERT OR REPLACE INTO ${entity} (id, data, updated_at)
      VALUES (?, ?, datetime('now'))
    `).run(id, JSON.stringify(data));
  }

  // Queue for sync when online
  queueSync(entity: string, id: string, operation: string, data: unknown): void {
    this.db.prepare(`
      INSERT INTO sync_queue (entity_type, entity_id, operation, payload)
      VALUES (?, ?, ?, ?)
    `).run(entity, id, operation, JSON.stringify(data));
  }

  // Process sync queue when online
  async processSyncQueue(): Promise<void> {
    const pending = this.db.prepare(
      'SELECT * FROM sync_queue WHERE synced = 0 ORDER BY created_at ASC'
    ).all() as any[];

    for (const item of pending) {
      try {
        const payload = JSON.parse(item.payload);
        // Send to server
        await this.syncToServer(item.entity_type, item.operation, payload);

        // Mark as synced
        this.db.prepare('UPDATE sync_queue SET synced = 1 WHERE id = ?').run(item.id);
      } catch (err) {
        console.error('Sync failed for item', item.id, err);
        // Will retry on next sync cycle
      }
    }
  }
}
```

### Push Notification Pattern

```typescript
// React Native push notifications
import { Platform } from 'react-native';
import messaging from '@react-native-firebase/messaging';

async function setupPushNotifications(): Promise<void> {
  // 1. Request permission
  const authStatus = await messaging().requestPermission();
  const enabled =
    authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
    authStatus === messaging.AuthorizationStatus.PROVISIONAL;

  if (!enabled) return;

  // 2. Get FCM token
  const token = await messaging().getToken();
  await registerDeviceToken(token);

  // 3. Handle foreground messages
  messaging().onMessage(async (remoteMessage) => {
    // Display in-app notification
    Alert.alert(
      remoteMessage.notification?.title ?? '',
      remoteMessage.notification?.body ?? '',
    );
  });

  // 4. Handle background messages
  messaging().setBackgroundMessageHandler(async (remoteMessage) => {
    // Update local data, refresh cache
    console.log('Background message:', remoteMessage);
  });

  // 5. Handle notification open
  messaging().onNotificationOpenedApp((remoteMessage) => {
    // Navigate to specific screen based on notification data
    const screen = remoteMessage.data?.screen;
    if (screen) navigateToScreen(screen as string);
  });
}
```

---

## 5. Mobile CI/CD

```yaml
# .github/workflows/mobile-ci.yml
name: Mobile CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20

      # React Native
      - name: Install dependencies
        run: npm ci

      - name: Type check
        run: npx tsc --noEmit

      - name: Run tests
        run: npx jest --coverage

      # Flutter
      - name: Flutter analyze
        run: flutter analyze

      - name: Flutter tests
        run: flutter test --coverage

  build:
    needs: test
    runs-on: macos-latest  # Needed for iOS builds
    steps:
      - uses: actions/checkout@v4

      # Android
      - name: Build Android APK
        run: cd android && ./gradlew assembleRelease

      # iOS
      - name: Build iOS release
        run: |
          cd ios
          xcodebuild -workspace App.xcworkspace \
            -scheme App \
            -configuration Release \
            -sdk iphoneos \
            -archivePath App.xcarchive archive
```

---

## Quick Reference: Mobile by Node Type

| Node Type | Mobile Mapping |
|---|---|
| **Input** | Touch gestures, camera input, voice, push notification tap |
| **Logic** | Mobile business logic, offline queue, background sync |
| **Database** | SQLite local store, Realm, MMKV, SharedPreferences |
| **UI** | Native components, navigation, animations, theming |
| **API** | REST/GraphQL client, push notification service, WebSocket |

---

*For deeper mobile concepts, see Bible level `31-mobile-cross-platform/` — iOS native, Android, React Native, Flutter, Kotlin Multiplatform, and mobile performance.*
