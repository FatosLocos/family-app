"""MCP bridge for OpenClaw <-> FamilyApp.

Thin translation layer: exposes 3 MCP tools that each call one of the
existing bearer-token REST endpoints under /instellingen/api/openclaw/
(see django_app/integrations/openclaw_views.py). No FamilyApp/Django code
runs in this process — it only forwards HTTP calls, so the REST API
remains the single source of truth and this bridge has nothing to keep
in sync beyond the token and base URL.

Run directly: FAMILY_APP_TOKEN=... python server.py
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

FAMILY_APP_BASE_URL = os.environ.get("FAMILY_APP_BASE_URL", "http://127.0.0.1:8088").rstrip("/")
FAMILY_APP_TOKEN = os.environ.get("FAMILY_APP_TOKEN", "")
BRIDGE_HOST = os.environ.get("MCP_BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.environ.get("MCP_BRIDGE_PORT", "8899"))

if not FAMILY_APP_TOKEN:
    raise SystemExit("FAMILY_APP_TOKEN is not set — create one in FamilyApp under Instellingen > OpenClaw first.")

mcp = FastMCP("family-app", host=BRIDGE_HOST, port=BRIDGE_PORT)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=FAMILY_APP_BASE_URL,
        headers={"Authorization": f"Bearer {FAMILY_APP_TOKEN}", "Accept": "application/json"},
        timeout=15.0,
    )


@mcp.tool()
def vandaag() -> dict:
    """Get today's open tasks, shopping list, and calendar events for this household."""
    with _client() as client:
        response = client.get("/instellingen/api/openclaw/vandaag/")
        response.raise_for_status()
        return response.json()


@mcp.tool()
def taak_toevoegen(title: str, due_at: str | None = None, priority: int | None = None, notes: str | None = None) -> dict:
    """Add a new task to the household's task list.

    Args:
        title: What the task is (required).
        due_at: Optional ISO 8601 deadline, e.g. "2026-07-20T18:00:00".
        priority: Optional priority: 1 (low), 2 (normal, default), 3 (high).
        notes: Optional free-text notes.
    """
    payload = {"title": title}
    if due_at:
        payload["due_at"] = due_at
    if priority:
        payload["priority"] = priority
    if notes:
        payload["notes"] = notes
    with _client() as client:
        response = client.post("/instellingen/api/openclaw/taken/", json=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
def taak_afronden(task_id: int) -> dict:
    """Mark a task as done, given its numeric id (from vandaag()'s tasks_open list)."""
    with _client() as client:
        response = client.post(f"/instellingen/api/openclaw/taken/{task_id}/afronden/")
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
