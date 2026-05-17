# Phase 1: Django Server - Code Review

## Implementation Status: ✅ Complete (35 tests passing)

---

## File Structure

```
django-server/
├── manage.py
├── requirements.txt
├── db.sqlite3
├── whatsapp_mgr/
│   ├── __init__.py
│   ├── settings.py          # JWT_SECRET, SERVICE_KEY, MAX_CONCURRENT_USERS
│   ├── urls.py             # /admin/, /api/, /health/
│   └── wsgi.py
└── users/
    ├── __init__.py
    ├── apps.py
    ├── models.py            # User (status, whatsapp_jid), QRCode
    ├── admin.py             # Show QR + Generate API Key actions
    ├── views.py             # UserViewSet, QRCodeViewSet
    ├── serializers.py       # UserSerializer, QRCodeSerializer
    ├── urls.py              # Router config
    ├── authentication.py    # ServiceKeyAuthentication
    ├── tests.py             # 35 unit tests
    └── migrations/
        └── 0001_initial.py
```

---

## What Was Built

### Models (models.py)
- `User` extending AbstractUser with status choices and whatsapp_jid
- `QRCode` with FK to User, image_data, expires_at, verified
- Proper ordering, cascade delete, __str__ methods

### REST API (views.py, serializers.py)
- `UserViewSet`: CRUD + `/users/{id}/qr/` GET/PATCH + `/users/{id}/status/` PATCH
- `QRCodeViewSet`: Read-only
- ServiceKeyAuthentication on all endpoints
- Proper serializers with validation

### Django Admin (admin.py)
- List display: username, status, whatsapp_jid, created_at
- Filters: status, created_at
- Actions: "Show WhatsApp QR", "Generate API Key"
- Status field editable in change form

### Authentication (authentication.py)
- ServiceKeyAuthentication class
- X-Service-Key header validation
- Timing-safe comparison via secrets.compare_digest()
- Proper 401 responses

### Logging (settings.py)
- JSON formatter configured
- LOG_LEVEL from environment
- Separate loggers for 'users' and 'django'

---

## Issues Found

### Issue 1: JWT user_id Uses Database PK (Minor)

**Location**: `users/admin.py:62-67`

```python
payload = {
    "user_id": user.id,  # Integer PK
    "username": user.username,
    "iat": datetime.utcnow(),
}
```

**Impact**: Bridge constructs paths as `store/{user_id}/messages.db`. If Bridge expects string, may cause issues.

**Recommendation**: Confirm with Bridge implementation. If needed, use `str(user.id)` or username.

### Issue 2: QR GET Returns 404 When None (Minor)

**Location**: `users/views.py:60-65`

Returns 404 if no pending QR exists. May be confusing for Bridge.

**Current**: `{'detail': 'No pending QR code found'}` → 404
**Alternative**: Return empty object or different status

---

## Test Coverage (35 tests)

| Test Class | Tests | Coverage |
|------------|-------|----------|
| ProjectSetupTestCase | 4 | Settings, installed apps, custom user model |
| UserModelTestCase | 4 | Creation, status choices, ordering |
| QRCodeModelTestCase | 5 | Creation, user relationship, cascade delete |
| SerializerTestCase | 4 | UserSerializer, UserCreateSerializer, QRCodeSerializer |
| ServiceKeyAuthTestCase | 3 | Key required, valid key, invalid key rejected |
| APIEndpointsTestCase | 8 | CRUD, QR endpoints, status update, health |
| AdminInterfaceTestCase | 5 | User list, change form, actions, filters |
| LoggingTestCase | 2 | Logging configured, log level from env |

---

## Configuration (settings.py)

```python
JWT_SECRET = os.environ.get('JWT_SECRET', '')
SERVICE_KEY = os.environ.get('SERVICE_KEY', '')
BRIDGE_POLL_INTERVAL = int(os.environ.get('BRIDGE_POLL_INTERVAL', '60'))
MAX_CONCURRENT_USERS = int(os.environ.get('MAX_CONCURRENT_USERS', '5'))
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
```

---

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/users/` | ServiceKey | List all users |
| POST | `/api/users/` | ServiceKey | Create user |
| GET | `/api/users/{id}/` | ServiceKey | Get user |
| PATCH | `/api/users/{id}/` | ServiceKey | Update user |
| DELETE | `/api/users/{id}/` | ServiceKey | Delete user |
| GET | `/api/users/{id}/qr/` | ServiceKey | Get pending QR |
| PATCH | `/api/users/{id}/qr/` | ServiceKey | Push new QR (Bridge) |
| PATCH | `/api/users/{id}/status/` | ServiceKey | Update status |
| GET | `/api/qrcodes/` | ServiceKey | List QR codes |
| GET | `/health/` | None | Health check |

---

## Admin Actions

1. **Show WhatsApp QR**: Displays base64 QR image in admin message
2. **Generate API Key**: Displays JWT token in admin message

Both actions require selecting exactly one user.

---

## Ready for Phase 2: ✅

Core implementation is solid. Issues found are minor and can be addressed during Bridge implementation if needed.

---

## Notes for Phase 2

- Bridge will poll `/api/users/` every 60s
- Bridge pushes QR via PATCH `/api/users/{id}/qr/`
- Bridge updates status via PATCH `/api/users/{id}/status/`
- JWT user_id should be string-compatible for path construction