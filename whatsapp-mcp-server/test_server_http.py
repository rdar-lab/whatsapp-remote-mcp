import os
import pytest
from unittest.mock import patch, MagicMock

os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only"
os.environ["SERVICE_KEY"] = "test-service-key-123"
os.environ["BRIDGE_API_URL"] = "http://localhost:8080/api"
os.environ["DJANGO_API_URL"] = "http://localhost:18080"

from auth import validate_jwt


class TestHealthEndpoint:
    """Tests for /health/ endpoint."""

    def setup_method(self):
        from server_http import app
        self.client = self.app = MagicMock()
        import httpx
        from fastapi.testclient import TestClient
        from server_http import app as server_app
        self.client = TestClient(server_app)

    def test_health_returns_200(self):
        response = self.client.get("/health/")
        assert response.status_code == 200

    def test_health_returns_status_healthy(self):
        response = self.client.get("/health/")
        assert response.json()["status"] == "healthy"

    def test_health_returns_service_name(self):
        response = self.client.get("/health/")
        assert response.json()["service"] == "whatsapp-mcp-http"

    def test_health_returns_version(self):
        response = self.client.get("/health/")
        assert "version" in response.json()


class TestRootEndpoint:
    """Tests for / endpoint."""

    def setup_method(self):
        from server_http import app as server_app
        from fastapi.testclient import TestClient
        self.client = TestClient(server_app)

    def test_root_returns_200(self):
        response = self.client.get("/")
        assert response.status_code == 200

    def test_root_returns_service_info(self):
        response = self.client.get("/")
        data = response.json()
        assert data["service"] == "whatsapp-mcp-http"
        assert "endpoints" in data


class TestMCPLoginEndpoint:
    """Tests for /mcp/ GET endpoint."""

    def setup_method(self):
        from server_http import app as server_app
        from fastapi.testclient import TestClient
        self.client = TestClient(server_app)

    def test_mcp_get_without_auth_returns_401(self):
        response = self.client.get("/mcp/")
        assert response.status_code == 401

    def test_mcp_get_with_invalid_auth_returns_401(self):
        response = self.client.get("/mcp/", headers={"Authorization": "Bearer invalid"})
        assert response.status_code == 401

    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_mcp_get_with_valid_jwt_returns_connected(self, mock_validate_jwt, mock_check_user):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True

        response = self.client.get("/mcp/", headers={"Authorization": "Bearer valid.jwt.token"})
        assert response.status_code == 200
        assert response.json()["status"] == "connected"
        assert response.json()["user_id"] == "user123"

    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_mcp_get_deleted_user_returns_403(self, mock_validate_jwt, mock_check_user):
        mock_validate_jwt.return_value = "deleteduser"
        mock_check_user.return_value = False

        response = self.client.get("/mcp/", headers={"Authorization": "Bearer valid.jwt.token"})
        assert response.status_code == 403
        assert "no longer exists" in response.json()["detail"]


class TestMCPPostEndpoint:
    """Tests for /mcp/ POST endpoint."""

    def setup_method(self):
        from server_http import app as server_app
        from fastapi.testclient import TestClient
        self.client = TestClient(server_app)

    def test_mcp_post_without_auth_returns_401(self):
        response = self.client.post("/mcp/", json={"tool": "search_contacts", "arguments": {}})
        assert response.status_code == 401

    @patch("server_http.validate_no_user_id_in_arguments")
    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_mcp_post_with_valid_jwt_accepts_request(self, mock_validate_jwt, mock_check_user, mock_validate_args):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True

        response = self.client.post(
            "/mcp/",
            headers={"Authorization": "Bearer valid.jwt.token"},
            json={"tool": "search_contacts", "arguments": {"query": "test"}}
        )
        assert response.status_code == 200

    @patch("server_http.validate_no_user_id_in_arguments")
    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_mcp_post_rejects_user_id_in_arguments(self, mock_validate_jwt, mock_check_user, mock_validate_args):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True
        mock_validate_args.side_effect = PermissionError("user_id cannot be passed as tool argument")

        response = self.client.post(
            "/mcp/",
            headers={"Authorization": "Bearer valid.jwt.token"},
            json={"tool": "search_contacts", "arguments": {"user_id": "attacker"}}
        )
        assert response.status_code == 403

    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_mcp_post_deleted_user_returns_403(self, mock_validate_jwt, mock_check_user):
        mock_validate_jwt.return_value = "deleteduser"
        mock_check_user.return_value = False

        response = self.client.post(
            "/mcp/",
            headers={"Authorization": "Bearer valid.jwt.token"},
            json={"tool": "search_contacts", "arguments": {}}
        )
        assert response.status_code == 403

    @patch("server_http.validate_no_user_id_in_arguments")
    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_mcp_post_missing_tool_returns_400(self, mock_validate_jwt, mock_check_user, mock_validate_args):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True

        response = self.client.post(
            "/mcp/",
            headers={"Authorization": "Bearer valid.jwt.token"},
            json={"arguments": {}}
        )
        assert response.status_code == 400
        assert "Missing tool name" in response.json()["detail"]


class TestExecuteTool:
    """Tests for execute_tool function."""

    def setup_method(self):
        from server_http import app as server_app
        from fastapi.testclient import TestClient
        self.client = TestClient(server_app)

    @patch("server_http.whatsapp_search_contacts")
    @patch("server_http.validate_no_user_id_in_arguments")
    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_execute_search_contacts(self, mock_validate_jwt, mock_check_user, mock_validate_args, mock_search):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True
        mock_search.return_value = []

        response = self.client.post(
            "/mcp/",
            headers={"Authorization": "Bearer valid.jwt.token"},
            json={"tool": "search_contacts", "arguments": {"query": "John"}}
        )
        assert response.status_code == 200
        mock_search.assert_called_once_with("user123", "John")

    @patch("server_http.whatsapp_list_chats")
    @patch("server_http.validate_no_user_id_in_arguments")
    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_execute_list_chats(self, mock_validate_jwt, mock_check_user, mock_validate_args, mock_list):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True
        mock_list.return_value = []

        response = self.client.post(
            "/mcp/",
            headers={"Authorization": "Bearer valid.jwt.token"},
            json={"tool": "list_chats", "arguments": {"limit": 10}}
        )
        assert response.status_code == 200
        mock_list.assert_called_once()

    @patch("server_http.whatsapp_send_message")
    @patch("server_http.validate_no_user_id_in_arguments")
    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_execute_send_message(self, mock_validate_jwt, mock_check_user, mock_validate_args, mock_send):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True
        mock_send.return_value = {"success": True, "message": "Sent"}

        response = self.client.post(
            "/mcp/",
            headers={"Authorization": "Bearer valid.jwt.token"},
            json={"tool": "send_message", "arguments": {"recipient": "123456", "message": "Hello"}}
        )
        assert response.status_code == 200
        mock_send.assert_called_once()

    @patch("server_http.validate_no_user_id_in_arguments")
    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_execute_unknown_tool_returns_400(self, mock_validate_jwt, mock_check_user, mock_validate_args):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True

        response = self.client.post(
            "/mcp/",
            headers={"Authorization": "Bearer valid.jwt.token"},
            json={"tool": "nonexistent_tool", "arguments": {}}
        )
        assert response.status_code == 400
        assert "Unknown tool" in response.json()["detail"]


class TestJWTAuthFlow:
    """Integration tests for JWT authentication flow."""

    def setup_method(self):
        from server_http import app as server_app
        from fastapi.testclient import TestClient
        self.client = TestClient(server_app)

    def test_bearer_without_prefix_returns_401(self):
        response = self.client.get("/mcp/", headers={"Authorization": "some-token"})
        assert response.status_code == 401

    def test_empty_bearer_returns_401(self):
        response = self.client.get("/mcp/", headers={"Authorization": "Bearer "})
        assert response.status_code == 401

    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_user_id_from_jwt_propagates_to_tool(self, mock_validate_jwt, mock_check_user):
        mock_validate_jwt.return_value = "jwt_user_123"
        mock_check_user.return_value = True

        with patch("server_http.whatsapp_list_chats") as mock_list:
            mock_list.return_value = []
            response = self.client.post(
                "/mcp/",
                headers={"Authorization": "Bearer valid.jwt.token"},
                json={"tool": "list_chats", "arguments": {}}
            )
            mock_list.assert_called_with(user_id="jwt_user_123", query=None, limit=20, page=0,
                                          include_last_message=True, sort_by="last_active")


class TestServiceKeyAuth:
    """Tests for service key authentication."""

    def setup_method(self):
        from server_http import app as server_app
        from fastapi.testclient import TestClient
        self.client = TestClient(server_app)

    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_mcp_get_requires_bearer_token_not_service_key(self, mock_validate_jwt, mock_check_user):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True

        response = self.client.get(
            "/mcp/",
            headers={"X-Service-Key": "some-service-key"}
        )
        assert response.status_code == 401


class TestValidateAndGetUserId:
    """Tests for validate_and_get_user_id function."""

    def setup_method(self):
        from server_http import app as server_app
        from fastapi.testclient import TestClient
        self.client = TestClient(server_app)

    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_valid_jwt_and_existing_user_returns_user_id(self, mock_validate_jwt, mock_check_user):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True

        from server_http import validate_and_get_user_id
        result = validate_and_get_user_id("Bearer valid.jwt.token")
        assert result == "user123"

    @patch("server_http.validate_jwt")
    def test_invalid_jwt_raises_401(self, mock_validate_jwt):
        mock_validate_jwt.return_value = None

        from server_http import validate_and_get_user_id
        with pytest.raises(Exception) as exc_info:
            validate_and_get_user_id("Bearer invalid.jwt.token")
        assert exc_info.value.status_code == 401


class TestErrorHandling:
    """Tests for error handling."""

    def setup_method(self):
        from server_http import app as server_app
        from fastapi.testclient import TestClient
        self.client = TestClient(server_app)

    def test_malformed_authorization_header_handled(self):
        response = self.client.get("/mcp/", headers={"Authorization": "Bearer"})
        assert response.status_code == 401

    @patch("server_http.check_user_exists_in_django")
    @patch("server_http.validate_jwt")
    def test_database_error_returns_500(self, mock_validate_jwt, mock_check_user):
        mock_validate_jwt.return_value = "user123"
        mock_check_user.return_value = True

        with patch("server_http.whatsapp_list_messages") as mock_list:
            mock_list.side_effect = Exception("Database error")
            response = self.client.post(
                "/mcp/",
                headers={"Authorization": "Bearer valid.jwt.token"},
                json={"tool": "list_messages", "arguments": {}}
            )
            assert response.status_code == 500