"""Partage temporaire des photos avec Google Drive."""
from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
OAUTH_CLIENT_FILE = "google_drive_client.json"
OAUTH_TOKEN_FILE = "google_drive_token.json"
DRIVE_STATE_FILE = "google_drive_state.json"
SHARES_DB_FILE = "google_drive_shares.sqlite3"
DRIVE_FOLDER_NAME = "Photobooth"
LINK_LIFETIME = timedelta(days=30)
TASK_NAME = "PhotoBoothDriveCleanup"


@dataclass(frozen=True)
class SharedMedia:
    url: str
    expires_at: datetime


def _paths(base_dir: Path) -> tuple[Path, Path, Path, Path]:
    data_dir = base_dir / "data"
    return (data_dir / OAUTH_CLIENT_FILE, data_dir / OAUTH_TOKEN_FILE,
            data_dir / DRIVE_STATE_FILE, data_dir / SHARES_DB_FILE)


def _drive_service(base_dir: Path):
    """Construit un client Drive avec délai réseau borné."""
    try:
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
    except ImportError as exc:
        raise RuntimeError("Dépendances Google manquantes. Réinstalle requirements.txt.") from exc

    client_path, token_path, _, _ = _paths(base_dir)
    if not client_path.is_file():
        raise RuntimeError(
            f"Fichier OAuth absent : {client_path}. Consulte la section QR code de MODE_EMPLOI.md."
        )
    if not token_path.is_file():
        raise RuntimeError("Google Drive n'est pas connecté. Lance photobooth-outils --configurer-drive.")

    credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    if not credentials.valid:
        raise RuntimeError("La connexion Google Drive a expiré. Relance --configurer-drive.")

    http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=30))
    return build("drive", "v3", http=http, cache_discovery=False)


def authorize_google_drive(base_dir: Path) -> None:
    """Ouvre OAuth dans le navigateur puis conserve le jeton localement."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError("Dépendances Google manquantes. Installe requirements.txt.") from exc

    client_path, token_path, _, _ = _paths(base_dir)
    if not client_path.is_file():
        raise RuntimeError(
            f"Télécharge le client OAuth de type Application de bureau et place-le ici : {client_path}"
        )
    token_path.parent.mkdir(parents=True, exist_ok=True)
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    credentials = flow.run_local_server(port=0, open_browser=True, timeout_seconds=180)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    # La première connexion prépare aussi le dossier de destination et vérifie l'accès à l'API.
    DriveShareService(base_dir).ensure_folder(_drive_service(base_dir))


def register_cleanup_task(base_dir: Path, config_path: Path | None = None) -> bool:
    """Installe une tâche Windows horaire pour retirer les liens arrivés à échéance."""
    if sys.platform != "win32":
        return False
    if getattr(sys, "frozen", False):
        command = f'"{sys.executable}"'
    else:
        entrypoint = base_dir / "main.py"
        command = f'"{sys.executable}" "{entrypoint}"'
    if config_path is not None and config_path.resolve() != (base_dir / "config.ini").resolve():
        command += f' --config "{config_path.resolve()}"'
    command += " --cleanup-drive-links"
    try:
        result = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", command,
             "/SC", "HOURLY", "/MO", "1", "/ST", "00:15", "/F", "/IT"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        log.exception("Impossible de créer la tâche Windows de nettoyage Drive")
        return False
    if result.returncode:
        log.warning("Création de la tâche Windows impossible : %s", result.stderr.strip())
        return False
    return True


class DriveShareService:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self._client_path, self._token_path, self._state_path, self._db_path = _paths(base_dir)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS shares (
                file_id TEXT PRIMARY KEY,
                permission_id TEXT NOT NULL,
                expires_at INTEGER NOT NULL
            )""")

    def is_configured(self) -> bool:
        return self._client_path.is_file() and self._token_path.is_file()

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self._db_path, timeout=15)
        try:
            db.execute("PRAGMA journal_mode=WAL")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def ensure_folder(self, drive) -> str:
        state: dict[str, str] = {}
        try:
            state = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        folder_id = state.get("folder_id", "")
        if folder_id:
            try:
                folder = drive.files().get(fileId=folder_id, fields="id,mimeType,trashed").execute()
                if folder.get("mimeType") == "application/vnd.google-apps.folder" and not folder.get("trashed"):
                    return folder_id
            except Exception:
                log.info("Dossier Drive mémorisé introuvable ; recherche d'un autre dossier")

        escaped_name = DRIVE_FOLDER_NAME.replace("'", "\\'")
        response = drive.files().list(
            q=f"name = '{escaped_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            spaces="drive", pageSize=10, fields="files(id,name)",
        ).execute()
        folders = response.get("files", [])
        if folders:
            folder_id = folders[0]["id"]
        else:
            folder = drive.files().create(
                body={"name": DRIVE_FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            ).execute()
            folder_id = folder["id"]
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps({"folder_id": folder_id}), encoding="utf-8")
        return folder_id

    def upload_and_share(self, media_path: Path) -> SharedMedia:
        if not media_path.is_file():
            raise RuntimeError("Le fichier photo à partager est introuvable.")
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as exc:
            raise RuntimeError("Dépendances Google manquantes. Réinstalle requirements.txt.") from exc

        drive = _drive_service(self.base_dir)
        folder_id = self.ensure_folder(drive)
        metadata = {"name": media_path.name, "parents": [folder_id]}
        uploaded = drive.files().create(
            body=metadata,
            media_body=MediaFileUpload(str(media_path), resumable=True),
            fields="id",
        ).execute()
        file_id = uploaded["id"]
        try:
            permission = drive.permissions().create(
                fileId=file_id, body={"type": "anyone", "role": "reader"}, fields="id",
            ).execute()
        except Exception:
            log.exception("Impossible d'activer le partage public pour %s", file_id)
            raise

        expires_at = datetime.now(timezone.utc) + LINK_LIFETIME
        try:
            with self._connect() as db:
                db.execute("INSERT OR REPLACE INTO shares(file_id, permission_id, expires_at) VALUES (?, ?, ?)",
                           (file_id, permission["id"], int(expires_at.timestamp())))
        except Exception:
            # Évite un lien public sans échéance suivie si la base locale est inaccessible.
            try:
                drive.permissions().delete(fileId=file_id, permissionId=permission["id"]).execute()
            finally:
                raise
        file_info = drive.files().get(fileId=file_id, fields="webContentLink").execute()
        download_url = (file_info.get("webContentLink")
                        or f"https://drive.google.com/uc?export=download&id={file_id}")
        log.info("Média partagé via Drive jusqu'au %s : %s", expires_at.isoformat(), media_path.name)
        return SharedMedia(download_url, expires_at)

    def revoke_expired(self) -> tuple[int, int]:
        """Révoque les liens échus ; garde en base ceux qui ont échoué pour retenter plus tard."""
        now = int(datetime.now(timezone.utc).timestamp())
        with self._connect() as db:
            pending = db.execute(
                "SELECT file_id, permission_id FROM shares WHERE expires_at <= ?", (now,)
            ).fetchall()
        if not pending:
            return 0, 0
        drive = _drive_service(self.base_dir)
        revoked = failed = 0
        for file_id, permission_id in pending:
            try:
                drive.permissions().delete(fileId=file_id, permissionId=permission_id).execute()
            except Exception as exc:
                # 404 signifie que le partage a déjà été supprimé manuellement.
                if getattr(getattr(exc, "resp", None), "status", None) != 404:
                    log.warning("Révocation Drive à réessayer pour %s : %s", file_id, exc)
                    failed += 1
                    continue
            with self._connect() as db:
                db.execute("DELETE FROM shares WHERE file_id = ?", (file_id,))
            revoked += 1
            log.info("Lien public Drive révoqué ; fichier conservé : %s", file_id)
        return revoked, failed
