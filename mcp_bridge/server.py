"""MCP bridge for OpenClaw <-> FamilyApp.

Thin translation layer: exposes MCP tools that each call one of the
existing bearer-token REST endpoints under /instellingen/api/openclaw/
(see django_app/integrations/openclaw_views.py). No FamilyApp/Django code
runs in this process — it only forwards HTTP calls, so the REST API
remains the single source of truth and this bridge has nothing to keep
in sync beyond the token and base URL.

One bridge instance can serve several family members at once: each
OpenClaw registration passes its own `Authorization` header (see
`openclaw mcp add ... --header "Authorization=Bearer <token>"`), which is
forwarded to FamilyApp as-is per call. FAMILY_APP_TOKEN is only a
fallback for callers that register without a header.

Run directly: FAMILY_APP_TOKEN=... python server.py
"""
from __future__ import annotations

import base64
import hashlib
import os
import time

import httpx
from mcp.server.fastmcp import Context, FastMCP

FAMILY_APP_BASE_URL = os.environ.get("FAMILY_APP_BASE_URL", "http://127.0.0.1:8088").rstrip("/")
FAMILY_APP_TOKEN = os.environ.get("FAMILY_APP_TOKEN", "")
BRIDGE_HOST = os.environ.get("MCP_BRIDGE_HOST", "127.0.0.1")
BRIDGE_PORT = int(os.environ.get("MCP_BRIDGE_PORT", "8899"))
# Must be readable by whatever user runs the OpenClaw agent (a setgid directory shared
# between this bridge's user and that one) — this bridge and OpenClaw run on the same host.
DROPBOX_DOWNLOAD_DIR = os.environ.get("DROPBOX_DOWNLOAD_DIR", "/var/lib/family-app-dropbox-cache")
DROPBOX_DOWNLOAD_MAX_AGE_SECONDS = 24 * 60 * 60

mcp = FastMCP("family-app", host=BRIDGE_HOST, port=BRIDGE_PORT)


def _authorization_header(ctx: Context) -> str:
    """Prefer the caller's own Authorization header; fall back to the shared token."""
    request = ctx.request_context.request
    incoming = request.headers.get("authorization") if request else None
    if incoming:
        return incoming
    if FAMILY_APP_TOKEN:
        return f"Bearer {FAMILY_APP_TOKEN}"
    raise RuntimeError(
        "No Authorization header on the request and FAMILY_APP_TOKEN is not set — "
        "register this MCP server with --header \"Authorization=Bearer <token>\"."
    )


def _client(ctx: Context) -> httpx.Client:
    return httpx.Client(
        base_url=FAMILY_APP_BASE_URL,
        headers={"Authorization": _authorization_header(ctx), "Accept": "application/json"},
        timeout=15.0,
    )


def _checked(response: httpx.Response) -> dict:
    """Raise with FamilyApp's own Dutch error message instead of httpx's generic status text.

    `response.raise_for_status()` alone drops the JSON body — the agent would only
    see "400 Bad Request" and have no way to explain or self-correct the mistake.
    """
    if response.status_code >= 400:
        try:
            detail = response.json().get("error") or response.text
        except ValueError:
            detail = response.text
        raise RuntimeError(f"FamilyApp gaf een fout ({response.status_code}): {detail}")
    return response.json()


@mcp.tool()
def vandaag(ctx: Context) -> dict:
    """Get today's open tasks, shopping list, and calendar events for this household."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/vandaag/"))


@mcp.tool()
def taak_toevoegen(ctx: Context, title: str, due_at: str | None = None, priority: int | None = None, notes: str | None = None, list_name: str | None = None, assigned_to: str | None = None, source_label: str | None = None, source_url: str | None = None) -> dict:
    """Add a new task to the household's task list.

    Args:
        title: What the task is (required).
        due_at: Optional ISO 8601 deadline, e.g. "2026-07-20T18:00:00".
        priority: Optional priority: 1 (low), 2 (normal, default), 3 (high).
        notes: Optional free-text notes.
        list_name: Optional name of a task list to file this under, e.g. "Boodschappen" or
            "Klussen". Created automatically if it doesn't exist yet — see taak_lijsten()
            for the existing ones. Omit to leave the task unsorted ("Zonder lijst").
        assigned_to: Optional household member to assign this to, by name — a real
            assignment the app understands, not just text in the title or notes. Use
            gezinsleden() to see valid names first if unsure; an ambiguous or unknown
            name returns a clear error instead of silently guessing.
        source_label: Where this task came from, e.g. "Notulen jeugdcommissie 12 juli 2026"
            or "WhatsApp-gesprek met Denise". Shown as a badge on the task so the household
            always knows where it originated. ALWAYS fill this in whenever the task was
            derived from a document, conversation, or meeting rather than said directly —
            it's the whole point of letting an agent create tasks unsupervised. Didn't know
            the source at creation time? Set it later with taak_bijwerken.
        source_url: Optional link to that source (e.g. a Dropbox shared link), shown as a
            clickable link on the badge. Omit if there's no link, e.g. for a spoken
            conversation.
    """
    payload = {"title": title}
    if due_at:
        payload["due_at"] = due_at
    if priority:
        payload["priority"] = priority
    if notes:
        payload["notes"] = notes
    if list_name:
        payload["list_name"] = list_name
    if assigned_to:
        payload["assigned_to"] = assigned_to
    if source_label:
        payload["source_label"] = source_label
    if source_url:
        payload["source_url"] = source_url
    with _client(ctx) as client:
        return _checked(client.post("/instellingen/api/openclaw/taken/", json=payload))


@mcp.tool()
def gezinsleden(ctx: Context) -> dict:
    """List the household's members by their exact name, each with a numeric id. Use this
    before assigning a task with taak_toevoegen's or taak_bijwerken's `assigned_to`, so
    the name you pass matches exactly."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/gezinsleden/"))


@mcp.tool()
def taak_bijwerken(ctx: Context, task_id: int, title: str | None = None, notes: str | None = None, due_at: str | None = None, priority: int | None = None, list_name: str | None = None, assigned_to: str | None = None, source_label: str | None = None, source_url: str | None = None) -> dict:
    """Update one or more fields on an EXISTING task — the one tool for changing anything
    about a task except its completion state (use taak_afronden for that). Only the
    arguments you actually pass are changed; everything else is left as-is. This is also
    how you set a source on a task that didn't get one at creation time.

    Args:
        task_id: The task's numeric id (from taken() or vandaag()).
        title: New title, if renaming.
        notes: New free-text notes. Pass "" to clear.
        due_at: New ISO 8601 deadline. Pass "" to clear.
        priority: New priority: 1 (low), 2 (normal), 3 (high).
        list_name: Move to this list by name — created automatically if it doesn't exist
            yet. Pass "" to move the task back out of any list ("Zonder lijst").
        assigned_to: Assign to this household member by name (see gezinsleden()). Pass ""
            to unassign.
        source_label: Where this task came from — set this whenever you learn the origin
            of a task that doesn't have one yet, e.g. after finding the source document
            later. Pass "" to clear.
        source_url: Optional link to that source. Pass "" to clear.
    """
    payload = {}
    if title is not None:
        payload["title"] = title
    if notes is not None:
        payload["notes"] = notes
    if due_at is not None:
        payload["due_at"] = due_at
    if priority is not None:
        payload["priority"] = priority
    if list_name is not None:
        payload["list_name"] = list_name
    if assigned_to is not None:
        payload["assigned_to"] = assigned_to
    if source_label is not None:
        payload["source_label"] = source_label
    if source_url is not None:
        payload["source_url"] = source_url
    with _client(ctx) as client:
        return _checked(client.post(f"/instellingen/api/openclaw/taken/{task_id}/bijwerken/", json=payload))


@mcp.tool()
def taak_lijsten(ctx: Context) -> dict:
    """List the household's task lists ("lijstjes"), each with how many open tasks it has.
    Use this to see what lists already exist before deciding whether taak_toevoegen's or
    taak_bijwerken's `list_name` argument should reuse one or create a new one."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/taken/lijstjes/"))


@mcp.tool()
def taak_lijst_aanmaken(ctx: Context, name: str) -> dict:
    """Create a new, empty task list ("lijstje"). If a list with this name already exists,
    returns that one instead of creating a duplicate — safe to call speculatively.
    Usually unnecessary: taak_toevoegen's/taak_bijwerken's `list_name` argument creates the
    list automatically if needed, so only call this to make an empty list with no task yet.

    Args:
        name: The list's name, e.g. "Klussen" or "Verjaardag Emma".
    """
    with _client(ctx) as client:
        return _checked(client.post("/instellingen/api/openclaw/taken/lijstjes/toevoegen/", json={"name": name}))


@mcp.tool()
def taak_lijst_bijwerken(ctx: Context, list_id: int, name: str) -> dict:
    """Rename an existing task list. Use taak_lijsten() to find the list's id first.

    Args:
        list_id: The list's numeric id (from taak_lijsten()).
        name: The new name.
    """
    with _client(ctx) as client:
        return _checked(client.post(f"/instellingen/api/openclaw/taken/lijstjes/{list_id}/bijwerken/", json={"name": name}))


@mcp.tool()
def taken(ctx: Context) -> dict:
    """Get ALL open tasks for the household — not capped to a handful like vandaag()'s
    preview. Each task includes its list ("list", null if unsorted), notes, due date,
    priority, source, and whether OpenClaw created it. Use this before organizing tasks
    with taak_bijwerken, so nothing gets missed."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/taken/alle/"))


@mcp.tool()
def taak_afronden(ctx: Context, task_id: int, reden: str | None = None) -> dict:
    """Mark a task as done, given its numeric id (from vandaag()'s tasks_open list or taken()).

    Args:
        task_id: The task's numeric id.
        reden: Optional reason why it's done, e.g. "al geregeld", "niet meer nodig" — shown
            to the household as context alongside the task, so give one whenever you know why.
    """
    payload = {"reason": reden} if reden else {}
    with _client(ctx) as client:
        return _checked(client.post(f"/instellingen/api/openclaw/taken/{task_id}/afronden/", json=payload))


@mcp.tool()
def boodschappen(ctx: Context) -> dict:
    """Get the household's full open shopping list (not capped, unlike vandaag()'s preview)."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/boodschappen/"))


@mcp.tool()
def boodschap_toevoegen(ctx: Context, name: str, quantity: str | None = None, category: str | None = None) -> dict:
    """Add an item to the household's shopping list.

    Args:
        name: What to buy (required), e.g. "melk".
        quantity: Optional free-text amount, e.g. "2 pakken".
        category: Optional free-text category, e.g. "zuivel".
    """
    payload = {"name": name}
    if quantity:
        payload["quantity"] = quantity
    if category:
        payload["category"] = category
    with _client(ctx) as client:
        return _checked(client.post("/instellingen/api/openclaw/boodschappen/toevoegen/", json=payload))


@mcp.tool()
def boodschap_bijwerken(ctx: Context, item_id: int, name: str | None = None, quantity: str | None = None, category: str | None = None) -> dict:
    """Update one or more fields on an existing shopping list item. Only the arguments you
    pass are changed.

    Args:
        item_id: The item's numeric id (from boodschappen()).
        name: New product name.
        quantity: New free-text amount. Pass "" to clear.
        category: New free-text category. Pass "" to clear.
    """
    payload = {}
    if name is not None:
        payload["name"] = name
    if quantity is not None:
        payload["quantity"] = quantity
    if category is not None:
        payload["category"] = category
    with _client(ctx) as client:
        return _checked(client.post(f"/instellingen/api/openclaw/boodschappen/{item_id}/bijwerken/", json=payload))


@mcp.tool()
def boodschap_afvinken(ctx: Context, item_id: int) -> dict:
    """Mark a shopping list item as bought/done, given its numeric id (from boodschappen())."""
    with _client(ctx) as client:
        return _checked(client.post(f"/instellingen/api/openclaw/boodschappen/{item_id}/afvinken/", json={}))


@mcp.tool()
def huis(ctx: Context) -> dict:
    """List controllable and readable devices in the house: lights, switches, covers, thermostats, media players, cars, appliances."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/huis/"))


@mcp.tool()
def huis_bedienen(ctx: Context, entity_id: int, action: str, value: str | None = None) -> dict:
    """Control a device in the house, given its numeric id (from huis()'s entities list).

    Valid actions depend on the device's `domain` (from huis()):
        light/switch: "on", "off"
        scene: "activate"
        script: "run"
        cover: "open", "close", "stop"
        climate: "on", "off", "set_temperature" (needs `value` = target °C)
        media_player: "on", "off", "play_pause", "volume_up", "volume_down"
    Other sources (Sonos, Spotify, Smartcar, Google Home, LG ThinQ, Home Connect) support
    additional actions particular to that device — check the device's `attributes` from
    huis() or simply try a natural action; an invalid one returns a clear Dutch error.

    Args:
        entity_id: The device's numeric id.
        action: What to do, e.g. "on", "off", "play_pause", "set_temperature".
        value: Optional value the action needs, e.g. a target temperature.
    """
    payload = {"action": action}
    if value is not None:
        payload["value"] = value
    with _client(ctx) as client:
        return _checked(client.post(f"/instellingen/api/openclaw/huis/{entity_id}/bedienen/", json=payload))


@mcp.tool()
def agenda(ctx: Context, start: str | None = None, end: str | None = None) -> dict:
    """Get calendar events. Returns the ENTIRE calendar (past and future) unless narrowed.

    Args:
        start: Optional ISO date/datetime — only events ending on or after this. Omit for no lower bound.
        end: Optional ISO date/datetime — only events starting before this. Omit for no upper bound.
    """
    params = {}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/agenda/", params=params))


@mcp.tool()
def afspraak_toevoegen(ctx: Context, title: str, starts_at: str, ends_at: str, is_all_day: bool = False, location: str | None = None, notes: str | None = None) -> dict:
    """Add a new event to the household's shared calendar.

    Args:
        title: What the event is (required).
        starts_at: ISO 8601 start datetime, e.g. "2026-07-20T18:00:00".
        ends_at: ISO 8601 end datetime, e.g. "2026-07-20T19:00:00".
        is_all_day: Whether this is an all-day event (default False).
        location: Optional location.
        notes: Optional free-text notes.
    """
    payload = {"title": title, "starts_at": starts_at, "ends_at": ends_at, "is_all_day": is_all_day}
    if location:
        payload["location"] = location
    if notes:
        payload["notes"] = notes
    with _client(ctx) as client:
        return _checked(client.post("/instellingen/api/openclaw/agenda/toevoegen/", json=payload))


@mcp.tool()
def afspraak_bijwerken(ctx: Context, event_id: int, title: str | None = None, starts_at: str | None = None, ends_at: str | None = None, is_all_day: bool | None = None, location: str | None = None, notes: str | None = None) -> dict:
    """Update one or more fields on an existing calendar event. Only the arguments you
    pass are changed.

    Args:
        event_id: The event's numeric id (from agenda()).
        title: New title.
        starts_at: New ISO 8601 start datetime.
        ends_at: New ISO 8601 end datetime.
        is_all_day: Whether it's an all-day event.
        location: New location. Pass "" to clear.
        notes: New free-text notes. Pass "" to clear.
    """
    payload = {}
    if title is not None:
        payload["title"] = title
    if starts_at is not None:
        payload["starts_at"] = starts_at
    if ends_at is not None:
        payload["ends_at"] = ends_at
    if is_all_day is not None:
        payload["is_all_day"] = is_all_day
    if location is not None:
        payload["location"] = location
    if notes is not None:
        payload["notes"] = notes
    with _client(ctx) as client:
        return _checked(client.post(f"/instellingen/api/openclaw/agenda/{event_id}/bijwerken/", json=payload))


@mcp.tool()
def geld(ctx: Context) -> dict:
    """Get bank account balances, the 20 most recent transactions, and monthly budget status. Read-only — there is no tool to add or categorize transactions."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/geld/"))


@mcp.tool()
def meldingen(ctx: Context) -> dict:
    """Get notifications this user has opted into proactively receiving (configured in FamilyApp Instellingen),
    that have not yet been delivered. Each has an id, title, body, kind ("info"/"warning"), and created_at.
    After delivering these to the user, call meldingen_afgeleverd with their ids so they aren't repeated.
    If empty, there is nothing new to report — do not send a message in that case."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/meldingen/"))


@mcp.tool()
def meldingen_afgeleverd(ctx: Context, ids: list[int]) -> dict:
    """Mark notifications as delivered after you have sent them to the user, so they are not repeated next time.

    Args:
        ids: The notification ids (from meldingen()) that were just delivered.
    """
    with _client(ctx) as client:
        return _checked(client.post("/instellingen/api/openclaw/meldingen/afgeleverd/", json={"ids": ids}))


@mcp.tool()
def dropbox_overzicht(ctx: Context) -> dict:
    """Get the top-level folders and files in the household's Dropbox — a fast table of contents.
    Use this first, then dropbox_map to look inside a specific folder or dropbox_zoeken to search
    by name across the whole account. Never returns file content, and there is no tool to read
    file content or write to Dropbox. Requires Dropbox to be connected in FamilyApp Instellingen."""
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/dropbox/"))


@mcp.tool()
def dropbox_map(ctx: Context, pad: str) -> dict:
    """List the direct contents (one level deep) of a specific Dropbox folder.

    Args:
        pad: The folder path, e.g. "/Conquesto" or "/Conquesto/Competitie" (from dropbox_overzicht or a previous dropbox_map call).
    """
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/dropbox/map/", params={"pad": pad}))


@mcp.tool()
def dropbox_zoeken(ctx: Context, q: str, pad: str | None = None) -> dict:
    """Search the household's Dropbox by name across the whole account (or a subfolder) — server-side
    search, so it reliably finds files regardless of how deep they're nested.

    Args:
        q: What to search for, e.g. "bruiloft" or "contributie 2026".
        pad: Optional folder to limit the search to, e.g. "/Conquesto".
    """
    params = {"q": q}
    if pad:
        params["pad"] = pad
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/dropbox/zoeken/", params=params))


@mcp.tool()
def dropbox_lezen(ctx: Context, pad: str) -> dict:
    """Read the text content of a specific Dropbox document — txt, md, csv, json, pdf, or docx only.
    For spreadsheets, presentations, images, or any other format, use dropbox_bestand_ruw_lezen
    instead. Large files are refused; long documents are truncated. Find the path first via
    dropbox_map or dropbox_zoeken.

    Args:
        pad: The file path, e.g. "/Conquesto/Financiën/Jaarverslag 2025.pdf".
    """
    with _client(ctx) as client:
        return _checked(client.get("/instellingen/api/openclaw/dropbox/lezen/", params={"pad": pad}))


def _prune_dropbox_downloads() -> None:
    """Delete cached downloads older than DROPBOX_DOWNLOAD_MAX_AGE_SECONDS.

    Runs opportunistically on every download rather than via a separate cron/timer — cheap
    for the small number of files this directory ever holds, and keeps household documents
    from lingering on disk indefinitely.
    """
    cutoff = time.time() - DROPBOX_DOWNLOAD_MAX_AGE_SECONDS
    try:
        entries = os.scandir(DROPBOX_DOWNLOAD_DIR)
    except FileNotFoundError:
        return
    with entries:
        for entry in entries:
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    os.remove(entry.path)
            except OSError:
                pass


@mcp.tool()
def dropbox_bestand_ruw_lezen(ctx: Context, path: str) -> dict:
    """Download a Dropbox file exactly as-is, regardless of format, and save it to a local
    file — use this for spreadsheets, presentations, images, or anything else dropbox_lezen's
    text extraction doesn't handle. Open local_path directly with Bash + the appropriate
    library (e.g. openpyxl for .xlsx, python-pptx for .pptx). There is no inline file content
    in this response — do not attempt to reconstruct the file from text, and never retype or
    paste file bytes by hand; read the path instead. Bounded to a smaller size than
    dropbox_lezen — for large text-heavy documents, prefer dropbox_lezen instead.

    Args:
        path: The file path, e.g. "/Conquesto/Begroting 2026.xlsx". Find it first via
            dropbox_map or dropbox_zoeken.
    """
    with _client(ctx) as client:
        result = _checked(client.get("/instellingen/api/openclaw/dropbox/ruw/", params={"path": path}))
    content = base64.b64decode(result.pop("content_base64"))

    _prune_dropbox_downloads()
    os.makedirs(DROPBOX_DOWNLOAD_DIR, exist_ok=True)
    unique_prefix = f"{int(time.time())}_{hashlib.sha1(path.encode()).hexdigest()[:8]}"
    local_path = os.path.join(DROPBOX_DOWNLOAD_DIR, f"{unique_prefix}_{os.path.basename(result['name'])}")
    with open(local_path, "wb") as f:
        f.write(content)
    os.chmod(local_path, 0o640)

    result["local_path"] = local_path
    return result


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
