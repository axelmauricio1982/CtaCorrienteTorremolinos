from __future__ import annotations

import json
import os
import ssl
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    import msal
except ImportError:  # La interfaz explica como instalar la dependencia opcional.
    msal = None

try:
    import requests
except ImportError:  # MSAL instala requests como dependencia.
    requests = None

try:
    import certifi
except ImportError:  # MSAL normalmente ya instala certifi como dependencia.
    certifi = None


CLIENT_ID = os.environ.get(
    "ONEDRIVE_CLIENT_ID",
    "783c3d89-46d0-4280-b8b9-0fdfcd88aab1",
)
AUTHORITY = "https://login.microsoftonline.com/consumers"
SCOPES = ["Files.ReadWrite.AppFolder"]
GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


def _ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


class OneDriveError(RuntimeError):
    pass


_state_lock = threading.Lock()
_login_state: dict[str, object] = {
    "status": "idle",
    "message": "OneDrive aun no esta conectado.",
}


def _safe_error(result: dict[str, object]) -> str:
    return str(
        result.get("error_description")
        or result.get("error")
        or "Microsoft no pudo completar el inicio de sesion."
    ).splitlines()[0]


def _load_cache(cache_path: Path):
    if msal is None:
        raise OneDriveError("Falta instalar MSAL. Ejecuta: python3 -m pip install -r requirements.txt")
    cache = msal.SerializableTokenCache()
    try:
        serialized = cache_path.read_text(encoding="utf-8")
    except OSError:
        serialized = ""
    if serialized:
        try:
            cache.deserialize(serialized)
        except (ValueError, json.JSONDecodeError):
            pass
    return cache


def _save_cache(cache, cache_path: Path) -> None:
    if not cache.has_state_changed:
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temporary.write_text(cache.serialize(), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(cache_path)
    try:
        cache_path.chmod(0o600)
    except OSError:
        pass


def _application(cache):
    http_client = None
    if requests is not None:
        # Some frozen macOS builds fail while urllib3 decompresses Microsoft's
        # discovery response. Identity encoding avoids that packaging-specific
        # failure without changing the TLS connection or response contents.
        http_client = requests.Session()
        http_client.headers["Accept-Encoding"] = "identity"
    return msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
        http_client=http_client,
    )


def connection_status(cache_path: Path) -> dict[str, object]:
    if msal is None:
        return {
            "status": "dependency_missing",
            "message": "Falta instalar MSAL para conectar directamente con OneDrive.",
            "connected": False,
        }

    with _state_lock:
        state = dict(_login_state)
    if state.get("status") == "pending":
        state["connected"] = False
        return state

    cache = _load_cache(cache_path)
    accounts = list(cache.search(msal.TokenCache.CredentialType.ACCOUNT))
    if accounts:
        return {
            "status": "connected",
            "message": "OneDrive Personal conectado.",
            "connected": True,
            "username": accounts[0].get("username", "") or accounts[0].get("preferred_username", ""),
        }
    if state.get("status") == "error":
        state["connected"] = False
        return state
    return {
        "status": "disconnected",
        "message": "OneDrive aun no esta conectado.",
        "connected": False,
    }


def _finish_device_login(application, cache, cache_path: Path, flow: dict[str, object]) -> None:
    global _login_state
    try:
        result = application.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise OneDriveError(_safe_error(result))
        _save_cache(cache, cache_path)
        accounts = application.get_accounts()
        username = accounts[0].get("username", "") if accounts else ""
        with _state_lock:
            _login_state = {
                "status": "connected",
                "message": "OneDrive Personal conectado correctamente.",
                "connected": True,
                "username": username,
            }
    except Exception as error:
        with _state_lock:
            _login_state = {
                "status": "error",
                "message": str(error),
                "connected": False,
            }


def start_device_login(cache_path: Path) -> dict[str, object]:
    global _login_state
    current = connection_status(cache_path)
    if current.get("status") == "pending":
        return current

    cache = _load_cache(cache_path)
    application = _application(cache)
    flow = application.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise OneDriveError(_safe_error(flow))

    state = {
        "status": "pending",
        "message": flow.get("message", "Completa el inicio de sesion de Microsoft."),
        "connected": False,
        "user_code": flow["user_code"],
        "verification_uri": flow.get("verification_uri", "https://microsoft.com/devicelogin"),
        "expires_at": int(flow.get("expires_at", 0) or 0),
    }
    with _state_lock:
        _login_state = state
    threading.Thread(
        target=_finish_device_login,
        args=(application, cache, cache_path, flow),
        daemon=True,
        name="onedrive-device-login",
    ).start()
    return dict(state)


def access_token(cache_path: Path) -> str | None:
    if msal is None:
        return None
    cache = _load_cache(cache_path)
    application = _application(cache)
    accounts = application.get_accounts()
    if not accounts:
        return None
    result = application.acquire_token_silent(SCOPES, account=accounts[0])
    _save_cache(cache, cache_path)
    if not result or "access_token" not in result:
        return None
    return str(result["access_token"])


def upload_file(cache_path: Path, local_path: Path, remote_name: str, content_type: str) -> dict[str, object]:
    token = access_token(cache_path)
    if not token:
        raise OneDriveError("La sesion de OneDrive no esta disponible. Vuelve a conectarla.")
    if not local_path.is_file():
        raise OneDriveError("No se encontro el archivo local de evidencia.")

    remote_path = quote(f"Evidencias/{remote_name}", safe="/")
    request = Request(
        f"{GRAPH_ROOT}/me/drive/special/approot:/{remote_path}:/content",
        data=local_path.read_bytes(),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type or "application/octet-stream",
        },
    )
    try:
        with urlopen(request, timeout=120, context=_ssl_context()) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8")).get("error", {}).get("message", "")
        except (ValueError, AttributeError, json.JSONDecodeError):
            detail = ""
        raise OneDriveError(detail or f"OneDrive respondio con HTTP {error.code}.") from error
    except (URLError, TimeoutError, OSError) as error:
        raise OneDriveError(f"No se pudo contactar OneDrive: {error}") from error

    item_id = str(result.get("id", ""))
    remote_size = int(result.get("size", -1))
    if not item_id or remote_size != local_path.stat().st_size:
        raise OneDriveError("OneDrive no confirmo correctamente el archivo cargado.")
    return {
        "id": item_id,
        "web_url": str(result.get("webUrl", "")),
        "size": remote_size,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
