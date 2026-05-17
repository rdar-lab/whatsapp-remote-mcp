#!/usr/bin/env python3
"""
HTTP MCP Server with JWT authentication.
This server provides MCP protocol over HTTP with JWT Bearer token validation.
"""

import os
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Request
from pydantic import BaseModel

from auth import validate_jwt, check_user_exists_in_django, validate_no_user_id_in_arguments
from whatsapp import (
    search_contacts as whatsapp_search_contacts,
    list_messages as whatsapp_list_messages,
    list_chats as whatsapp_list_chats,
    get_chat as whatsapp_get_chat,
    get_direct_chat_by_contact as whatsapp_get_direct_chat_by_contact,
    get_contact_chats as whatsapp_get_contact_chats,
    get_last_interaction as whatsapp_get_last_interaction,
    get_message_context as whatsapp_get_message_context,
    send_message as whatsapp_send_message,
    send_file as whatsapp_send_file,
    send_audio_message as whatsapp_audio_voice_message,
    download_media as whatsapp_download_media
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SERVICE_KEY", "")
BRIDGE_API_URL = os.environ.get("BRIDGE_API_URL", "http://localhost:8080/api")

app = FastAPI(title="WhatsApp MCP HTTP Server")


class ToolRequest(BaseModel):
    tool: str
    arguments: dict


def get_user_id_from_jwt(authorization: str) -> Optional[str]:
    """Extract and validate JWT from Authorization header."""
    if not authorization:
        return None
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return validate_jwt(token)


def validate_and_get_user_id(authorization: str) -> str:
    """Validate JWT and check user exists in Django."""
    user_id = get_user_id_from_jwt(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing or invalid JWT")

    if not check_user_exists_in_django(user_id):
        raise HTTPException(status_code=403, detail="User no longer exists")

    return user_id


@app.get("/health/")
def health_check():
    """Health check endpoint - no auth required."""
    return {
        "status": "healthy",
        "service": "whatsapp-mcp-http",
        "version": "0.1.0"
    }


@app.get("/mcp/")
def mcp_get(authorization: Optional[str] = Header(None)):
    """MCP GET endpoint - establishes connection."""
    user_id = validate_and_get_user_id(authorization) if authorization else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing or invalid JWT")

    logger.info(f"MCP GET connection opened for user_id: {user_id}")
    return {"status": "connected", "user_id": user_id}


@app.post("/mcp/")
async def mcp_post(request: Request, authorization: Optional[str] = Header(None)):
    """MCP POST endpoint - handles tool calls."""
    user_id = validate_and_get_user_id(authorization) if authorization else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing or invalid JWT")

    try:
        body = await request.json()
        tool_name = body.get("tool")
        arguments = body.get("arguments", {})

        if not tool_name:
            raise HTTPException(status_code=400, detail="Missing tool name")

        validate_no_user_id_in_arguments(arguments)

        result = await execute_tool(user_id, tool_name, arguments)

        return {"success": True, "result": result}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except HTTPException as e:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def execute_tool(user_id: str, tool_name: str, arguments: dict):
    """Execute MCP tool by name using context-based user_id."""
    logger.info(f"Executing tool {tool_name} for user {user_id}")

    if tool_name == "search_contacts":
        return whatsapp_search_contacts(user_id, arguments.get("query"))
    elif tool_name == "list_messages":
        return whatsapp_list_messages(
            user_id=user_id,
            after=arguments.get("after"),
            before=arguments.get("before"),
            sender_phone_number=arguments.get("sender_phone_number"),
            chat_jid=arguments.get("chat_jid"),
            query=arguments.get("query"),
            limit=arguments.get("limit", 20),
            page=arguments.get("page", 0),
            include_context=arguments.get("include_context", True),
            context_before=arguments.get("context_before", 1),
            context_after=arguments.get("context_after", 1)
        )
    elif tool_name == "list_chats":
        return whatsapp_list_chats(
            user_id=user_id,
            query=arguments.get("query"),
            limit=arguments.get("limit", 20),
            page=arguments.get("page", 0),
            include_last_message=arguments.get("include_last_message", True),
            sort_by=arguments.get("sort_by", "last_active")
        )
    elif tool_name == "get_chat":
        return whatsapp_get_chat(
            user_id=user_id,
            chat_jid=arguments.get("chat_jid"),
            include_last_message=arguments.get("include_last_message", True)
        )
    elif tool_name == "get_direct_chat_by_contact":
        return whatsapp_get_direct_chat_by_contact(
            user_id=user_id,
            sender_phone_number=arguments.get("sender_phone_number")
        )
    elif tool_name == "get_contact_chats":
        return whatsapp_get_contact_chats(
            user_id=user_id,
            jid=arguments.get("jid"),
            limit=arguments.get("limit", 20),
            page=arguments.get("page", 0)
        )
    elif tool_name == "get_last_interaction":
        return whatsapp_get_last_interaction(
            user_id=user_id,
            jid=arguments.get("jid")
        )
    elif tool_name == "get_message_context":
        return whatsapp_get_message_context(
            message_id=arguments.get("message_id"),
            user_id=user_id,
            before=arguments.get("before", 5),
            after=arguments.get("after", 5)
        )
    elif tool_name == "send_message":
        return whatsapp_send_message(
            user_id=user_id,
            recipient=arguments.get("recipient"),
            message=arguments.get("message")
        )
    elif tool_name == "send_file":
        return whatsapp_send_file(
            user_id=user_id,
            recipient=arguments.get("recipient"),
            media_path=arguments.get("media_path")
        )
    elif tool_name == "send_audio_message":
        return whatsapp_audio_voice_message(
            user_id=user_id,
            recipient=arguments.get("recipient"),
            media_path=arguments.get("media_path")
        )
    elif tool_name == "download_media":
        return whatsapp_download_media(
            user_id=user_id,
            message_id=arguments.get("message_id"),
            chat_jid=arguments.get("chat_jid")
        )
    else:
        raise ValueError(f"Unknown tool: {tool_name}")


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "service": "whatsapp-mcp-http",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health/",
            "mcp": "/mcp/"
        }
    }


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8001"))
    logger.info(f"Starting WhatsApp MCP HTTP server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)