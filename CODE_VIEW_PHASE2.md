# Phase 2: WhatsApp Bridge - Code Review

## Implementation Status: ⚠️ INCOMPLETE - Critical Issues Found

---

## File Structure

```
whatsapp-bridge/
├── main.go              # Entry point, starts bridge + HTTP server
├── config.go            # Configuration loading, ValidateUserID, ValidationError
├── config_test.go
├── bridge.go           # Bridge struct, Start(), Stop(), pollUsers(), user management
├── bridge_test.go
├── user_client.go       # UserClient struct, QRCodeEvent, UserInfo
├── user_handler.go      # WhatsApp event handling, QR generation
├── message_store.go    # UserMessageStore, SQLite per user
├── message_store_test.go
├── api_client.go        # DjangoAPIClient, service key auth
├── api_client_test.go
├── rest_api.go          # HTTP endpoints for MCP
├── go.mod
├── go.sum
└── whatsapp-client     # Compiled binary (should be ignored)
```

---

## What's Implemented ✅

| Component | Status | Notes |
|-----------|--------|-------|
| Config loading | ✅ | JWT_SECRET, SERVICE_KEY, MAX_CONCURRENT_USERS, PORT, etc. |
| ValidateUserID | ✅ | Regex `^[a-zA-Z0-9\-_]{1,64}$` - path traversal prevention |
| DjangoAPIClient | ✅ | X-Service-Key header, GetUsers, UpdateUser, PushQR |
| User polling loop | ✅ | pollUsers() every PollInterval, diffs with local map |
| User lifecycle | ✅ | addUser(), updateUser(), removeUser() |
| Max users limit | ✅ | Respects MAX_CONCURRENT_USERS |
| MessageStore | ✅ | Per-user SQLite at store/{userID}/messages.db |
| REST API skeleton | ✅ | /api/send/, /api/download/, /api/status/, /health/ |

---

## 🔴 Critical Issues Found

### Issue 1: UserClient.Client Never Initialized

**Location**: `bridge.go:addUser()` (line 88-94)

```go
func (b *Bridge) addUser(user UserInfo) {
    userID := fmt.Sprintf("%d", user.ID)
    store := NewUserMessageStore("store", userID)
    uc := NewUserClient(userID, user.Username, store)
    uc.SetStatus(user.Status)
    b.users[userID] = uc
    // MISSING: initUserClient(uc, logger)
}
```

**Problem**: `initUserClient()` is defined in `user_handler.go:114-128` but never called. `UserClient.Client` remains `nil`.

**Impact**:
- `uc.Client.IsConnected()` will panic (nil pointer)
- All WhatsApp operations fail

---

### Issue 2: QR Code Never Pushed to Django

**Location**: `user_handler.go:43-80`

```go
func (b *Bridge) handlePendingInitRequest(ctx context.Context, uc *UserClient) {
    qrChan, err := uc.Client.GetQRChannel(ctx)  // PANIC: uc.Client is nil
    // ...
    select {
    case uc.QRChan <- qr:
    default:
    }
    // NO: b.api.PushQR(ctx, userID, qr.ImageData, qr.ExpiresAt)
}
```

**Problems**:
1. `uc.Client` is nil → `GetQRChannel()` panics
2. Even if QR generated, `b.api.PushQR()` never called
3. Admin cannot see QR to scan

---

### Issue 3: QR Event Loop Exits Immediately

**Location**: `user_handler.go:76-79`

```go
if qrReceived {
    break  // Exits after first QR, before success event
}
```

**Problem**: QR event loop breaks after first QR code received, never waits for "success" event.

---

### Issue 4: REST API Endpoints Are Stubs

**Location**: `rest_api.go:87-102`

```go
func (b *Bridge) handleSend(w http.ResponseWriter, r *http.Request) {
    // ... validation ...
    if !uc.Client.IsConnected() {  // PANIC: nil pointer
    }
    json.NewEncoder(w).Encode(SendResponse{
        Success: true,
        Message: "Message sent",  // FAKE - no actual sending
    })
}
```

**Problem**: All endpoints return fake success without actual WhatsApp interaction.

---

### Issue 5: No WhatsApp Event Handler

**Problem**: Even if client initialized, no `client.AddEventHandler()` registered to handle:
- Incoming messages
- History sync
- Connection/disconnection events

---

### Issue 6: QRChan Has No Reader

**Problem**: `uc.QRChan` is written to in `handlePendingInitRequest()` but nothing reads from it to push to Django.

---

## Test Coverage

| Test File | Coverage |
|-----------|----------|
| `config_test.go` | Config defaults, ValidateUserID, ValidationError, UserClient status/stop |
| `bridge_test.go` | NewBridge, UserCount, HasCapacity, removeUser, ValidateUserID |
| `api_client_test.go` | Client construction, request building, GetUsers, PushQR, UpdateUserStatus |
| `message_store_test.go` | SaveChat, GetChats, SaveMessage, GetMessages with limit |

---

## Configuration (config.go)

```go
type Config struct {
    DjangoURL    string
    JWTSecret    string
    ServiceKey   string
    PollInterval time.Duration
    MaxUsers     int        // Default: 5
    LogLevel     string     // Default: "INFO"
    Port         int        // Default: 8080
    StorePath    string     // Default: "store"
}
```

---

## API Endpoints (rest_api.go)

| Endpoint | Method | Auth | Status |
|----------|--------|------|--------|
| `/api/send/` | POST | - | ❌ Stub - returns fake success |
| `/api/download/` | POST | - | ❌ Stub - returns fake success |
| `/api/status/{user_id}/` | GET | - | ✅ Returns status from local map |
| `/health/` | GET | None | ✅ Returns {healthy, user_count} |

---

## Django API Client (api_client.go)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GetUsers | GET /api/users/ | Poll all users from Django |
| GetUser | GET /api/users/{id}/ | Get single user |
| UpdateUser | PATCH /api/users/{id}/ | Update status/whatsapp_jid |
| PushQR | PATCH /api/users/{id}/qr/ | Push QR to Django |
| UpdateUserStatus | PATCH /api/users/{id}/ | Update status only |

All requests include `X-Service-Key` header.

---

## User Lifecycle Flow

```
pollUsers()
    ↓
Django returns [UserInfo{id, username, status}]
    ↓
For each new user (not in local map):
    addUser() → creates UserClient + MessageStore
        ↓
For each existing user:
    updateUser() → updates status
        ↓
For each removed user (in local but not Django):
    removeUser() → stops goroutine, closes DB
```

---

## What's Missing

1. ❌ `initUserClient()` must be called in `addUser()`
2. ❌ QR must be pushed to Django via `b.api.PushQR()`
3. ❌ Event handler registration (`client.AddEventHandler()`)
4. ❌ QRChan must be read and pushed to Django
5. ❌ Actual send message implementation
6. ❌ Actual download implementation
7. ❌ Message event handler to store incoming messages
8. ❌ History sync handler

---

## Recommendation

**Phase 2 is NOT ready for Phase 3 integration.** Critical WhatsApp functionality is missing.

The architecture is sound, but implementation is incomplete. Agent needs to:
1. Call `initUserClient()` in `addUser()`
2. Implement QR reading loop that pushes to Django
3. Register WhatsApp event handlers
4. Implement actual send/download logic

---

## Not Ready for Phase 3 ❌