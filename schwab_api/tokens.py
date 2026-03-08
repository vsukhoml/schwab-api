import base64
import datetime
import json
import logging
import os
import threading
import time
import urllib.parse
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .auth import default_auth_flow

try:
    from curl_cffi import requests as c_requests  # type: ignore[no-redef]

    HAS_CURL_CFFI = True
except ImportError:
    import requests as c_requests  # type: ignore[no-redef]

    HAS_CURL_CFFI = False

_ENC_PREFIX = "enc:"
DEFAULT_CONFIG_PATH = "~/.config/schwab-api"

logger = logging.getLogger(__name__)


class FileLock:
    def __init__(self, file_path: str):
        self.lock_file = file_path + ".lock"
        self.fd = None

    def __enter__(self):
        self.fd = os.open(self.lock_file, os.O_RDWR | os.O_CREAT | os.O_TRUNC)
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd is not None:
            if os.name == "nt":
                import msvcrt

                os.lseek(self.fd, 0, os.SEEK_SET)
                try:
                    msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
            self.fd = None


class Tokens:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        callback_url: str,
        config_path: str = DEFAULT_CONFIG_PATH,
        call_for_auth=None,
        logger: Optional[logging.Logger] = None,
    ):
        if not app_key or not app_secret or not callback_url or not config_path:
            raise ValueError("[Schwab API] Missing required parameters for tokens.")

        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.id_token: Optional[str] = None
        self.logger = logger or logging.getLogger(__name__)

        self._app_key = app_key
        self._app_secret = app_secret
        self._update_lock = threading.RLock()
        self._config_path: str = os.path.expanduser(config_path)
        self._callback_url = callback_url
        self._access_token_issued = datetime.datetime.min.replace(
            tzinfo=datetime.timezone.utc
        )
        self._refresh_token_issued = datetime.datetime.min.replace(
            tzinfo=datetime.timezone.utc
        )
        self._access_token_timeout = 30 * 60  # 30 min
        self._refresh_token_timeout = 7 * 24 * 60 * 60  # 7 days
        self._call_for_auth = call_for_auth or (
            lambda auth_url, callback_url: default_auth_flow(
                auth_url,
                callback_url,
                config_path=self._config_path,
                logger=self.logger,
            )
        )

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=app_key.encode("utf-8"),
            info=b"schwab-api-tokens",
        )
        self._encryption_key = hkdf.derive(app_secret.encode("utf-8"))

        self._tokens_file = os.path.join(self._config_path, "tokens.json")
        _dir = os.path.dirname(self._tokens_file)
        if _dir:
            os.makedirs(_dir, exist_ok=True)

        with self._update_lock:
            with FileLock(self._tokens_file):
                loaded = self._load_tokens_from_file()

        if loaded:
            self.update_tokens()
            at_delta = datetime.timedelta(seconds=self._access_token_timeout) - (
                datetime.datetime.now(datetime.timezone.utc) - self._access_token_issued
            )
            rt_delta = datetime.timedelta(seconds=self._refresh_token_timeout) - (
                datetime.datetime.now(datetime.timezone.utc)
                - self._refresh_token_issued
            )
            self.logger.info(f"Access token expires in: {str(at_delta).split('.')[0]}")
            self.logger.info(f"Refresh token expires in: {str(rt_delta).split('.')[0]}")
        else:
            self.logger.warning(
                "[Schwab API] Could not load tokens from file, starting authorization flow."
            )
            self.update_tokens(force_refresh_token=True)

    def _close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._close()

    def __del__(self):
        self._close()

    def _enc(self, s: Optional[str]) -> str:
        if not s:
            return ""
        aesgcm = AESGCM(self._encryption_key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, s.encode("utf-8"), None)
        return _ENC_PREFIX + base64.b64encode(nonce + ct).decode("utf-8")

    def _dec(self, s: Optional[str]) -> str:
        if not s:
            return ""
        if not s.startswith(_ENC_PREFIX):
            return s
        try:
            raw_token = s[len(_ENC_PREFIX) :]
            decoded = base64.b64decode(raw_token)
            nonce = decoded[:12]
            ct = decoded[12:]
            aesgcm = AESGCM(self._encryption_key)
            return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
        except Exception as e:
            raise Exception(f"Cannot decrypt token: {e}")

    def _load_tokens_from_file(self) -> bool:
        if not os.path.exists(self._tokens_file):
            return False

        try:
            with open(self._tokens_file, "r") as f:
                data = json.load(f)
        except Exception as e:
            self.logger.error(f"[Schwab API] Could not read tokens file ({e})")
            return False

        at_issued_str = data.get("access_token_issued")
        rt_issued_str = data.get("refresh_token_issued")
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        id_token = data.get("id_token", "")

        if (
            not at_issued_str
            or not rt_issued_str
            or not access_token
            or not refresh_token
        ):
            return False

        self._access_token_issued = datetime.datetime.fromisoformat(at_issued_str)
        if self._access_token_issued.tzinfo is None:
            self._access_token_issued = self._access_token_issued.replace(
                tzinfo=datetime.timezone.utc
            )
        self._refresh_token_issued = datetime.datetime.fromisoformat(rt_issued_str)
        if self._refresh_token_issued.tzinfo is None:
            self._refresh_token_issued = self._refresh_token_issued.replace(
                tzinfo=datetime.timezone.utc
            )

        self._access_token_timeout = data.get("expires_in", 1800)

        try:
            self.access_token = self._dec(access_token)
            self.refresh_token = self._dec(refresh_token)
        except Exception as e:
            self.logger.error(f"[Schwab API] Could not decrypt tokens ({e})")
            return False

        self.id_token = id_token
        return True

    def _set_tokens(
        self,
        at_issued: datetime.datetime,
        rt_issued: datetime.datetime,
        token_dictionary: dict,
    ) -> bool:
        new_access_token = token_dictionary.get("access_token", None)
        new_refresh_token = token_dictionary.get("refresh_token", None)
        new_id_token = token_dictionary.get("id_token", None)

        if new_access_token:
            self.access_token = new_access_token
        if new_refresh_token:
            self.refresh_token = new_refresh_token
        if new_id_token:
            self.id_token = new_id_token

        self._access_token_issued = at_issued
        self._refresh_token_issued = rt_issued
        self._access_token_timeout = token_dictionary.get("expires_in", 1800)
        token_type = token_dictionary.get("token_type", "Bearer")
        scope = token_dictionary.get("scope", "api")

        data = {
            "access_token_issued": at_issued.isoformat(),
            "refresh_token_issued": rt_issued.isoformat(),
            "access_token": self._enc(self.access_token),
            "refresh_token": self._enc(self.refresh_token),
            "id_token": self.id_token or "",
            "expires_in": self._access_token_timeout,
            "token_type": token_type,
            "scope": scope,
        }

        try:
            tmp_file = self._tokens_file + ".tmp"
            with open(tmp_file, "w") as f:
                json.dump(data, f)
            os.replace(tmp_file, self._tokens_file)
            return True
        except Exception as e:
            self.logger.error(f"[Schwab API] Could not write tokens ({e})")
            return False

    def _post_oauth_token(self, grant_type: str, code: Optional[str]):
        headers = {
            "Authorization": f'Basic {base64.b64encode(bytes(f"{self._app_key}:{self._app_secret}", "utf-8")).decode("utf-8")}',
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data: dict[str, Any]
        if grant_type == "authorization_code":
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._callback_url,
            }
        elif grant_type == "refresh_token":
            data = {"grant_type": "refresh_token", "refresh_token": code}
        else:
            raise Exception("Invalid grant type")

        kwargs: dict[str, Any] = {}
        if HAS_CURL_CFFI:
            kwargs["impersonate"] = "chrome"

        return c_requests.post(
            "https://api.schwabapi.com/v1/oauth/token",
            headers=headers,
            data=data,
            timeout=30,
            **kwargs,
        )

    def update_tokens(self, force_access_token=False, force_refresh_token=False):
        now = datetime.datetime.now(datetime.timezone.utc)
        rt_delta = datetime.timedelta(seconds=self._refresh_token_timeout) - (
            now - self._refresh_token_issued
        )
        at_delta = datetime.timedelta(seconds=self._access_token_timeout) - (
            now - self._access_token_issued
        )

        refresh_threshold = datetime.timedelta(seconds=3630)  # 60.5 mins
        access_threshold = datetime.timedelta(seconds=61)  # 61 seconds

        if (rt_delta < refresh_threshold) or force_refresh_token:
            self.logger.warning(
                f"The refresh token {'has expired' if rt_delta < datetime.timedelta(0) else 'is expiring soon'}."
            )
            self._update_refresh_token()
            return True
        elif (at_delta < access_threshold) or force_access_token:
            self.logger.debug("The access token has expired, updating...")
            self._update_access_token()
            return True
        else:
            return False

    def _update_access_token(self, overwrite: bool = False):
        with self._update_lock:
            last_known_at_issued = self._access_token_issued
            try:
                with FileLock(self._tokens_file):
                    self._load_tokens_from_file()
                    if (
                        self._access_token_issued > last_known_at_issued
                        and not overwrite
                    ):
                        self.logger.info("Access token updated elsewhere.")
                        return

                    now = datetime.datetime.now(datetime.timezone.utc)
                    response = self._post_oauth_token(
                        "refresh_token", self.refresh_token
                    )
                    if response.ok:
                        if self._set_tokens(
                            now, self._refresh_token_issued, response.json()
                        ):
                            self.logger.info("Access token updated successfully.")
                    else:
                        self.logger.error(
                            f"Could not get new access token. ({response.text})"
                        )
            except Exception as e:
                self.logger.error(f"[Schwab API] Could not update access token ({e})")

    def _update_refresh_token(self, overwrite: bool = False):
        def _get_new_tokens(url_or_code: str):
            code = None
            parsed = urllib.parse.urlparse(url_or_code)
            if parsed.scheme:
                code = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]
            else:
                code = urllib.parse.unquote(url_or_code)

            if not code:
                self.logger.error(
                    f"Could not parse authorization code from URL. ({url_or_code})"
                )
                return False

            response = self._post_oauth_token("authorization_code", code)
            if not response.ok:
                self.logger.error(f"Failed to get tokens: {response.text}")
                return False
            return response.json()

        with self._update_lock:
            last_known_rt_issued = self._refresh_token_issued
            try:
                with FileLock(self._tokens_file):
                    self._load_tokens_from_file()
                    if (
                        self._refresh_token_issued > last_known_rt_issued
                        and not overwrite
                    ):
                        return

                    auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?client_id={self._app_key}&redirect_uri={self._callback_url}"
                    now = datetime.datetime.now(datetime.timezone.utc)

                    auth_callback = self._call_for_auth(auth_url, self._callback_url)

                    if not auth_callback or len(auth_callback) < len(
                        self._callback_url
                    ):
                        self.logger.error("No authorization URL provided.")
                        return

                    tokens_json = _get_new_tokens(auth_callback)
                    if tokens_json and self._set_tokens(now, now, tokens_json):
                        self.logger.info(f"Tokens updated successfully.")
            except Exception as e:
                now = datetime.datetime.now(datetime.timezone.utc)
                if last_known_rt_issued < now and self._access_token_issued < now:
                    self.logger.critical(
                        f"Tokens invalid, couldn't get file lock ({e})."
                    )
