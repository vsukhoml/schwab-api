import logging
import os
import queue
import ssl
import subprocess
import tempfile
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

logger = logging.getLogger(__name__)


def manual_auth_flow(
    auth_url: str, callback_url: str, logger: Optional[logging.Logger] = None
) -> str:
    """Fallback manual authentication flow."""
    _logger = logger or logging.getLogger(__name__)
    print(
        f"\n[Schwab API] Please open the following URL in your browser to authenticate:"
    )
    print(f"\n{auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception as e:
        _logger.warning(f"Could not open browser automatically: {e}")

    auth_callback = input(
        f"[Schwab API] After authorizing, paste the full redirect URL (starts with {callback_url}) here: "
    ).strip()
    return auth_callback


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default HTTP server logging

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)

        # Check if the code is in the query params
        query = urllib.parse.parse_qs(parsed_path.query)
        if "code" in query:
            self.server.oauth_queue.put(self.path)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Schwab API Authentication Successful!</h1><p>You can now close this tab.</p></body></html>"
            )
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Schwab API Authentication Failed</h1><p>No authorization code found in the URL.</p></body></html>"
            )


def automated_auth_flow(
    auth_url: str,
    callback_url: str,
    timeout: int = 120,
    config_path: str = "~/.config/schwab-api",
    logger: Optional[logging.Logger] = None,
) -> str:
    """Attempts to run a local HTTP server to catch the OAuth redirect."""
    _logger = logger or logging.getLogger(__name__)
    parsed_url = urllib.parse.urlparse(callback_url)

    # We only support localhost/127.0.0.1 for the automated flow
    if parsed_url.hostname not in ("127.0.0.1", "localhost"):
        _logger.warning(
            f"Automated flow requires 127.0.0.1 or localhost as callback. Falling back to manual flow."
        )
        return manual_auth_flow(auth_url, callback_url, logger=_logger)

    port = parsed_url.port if parsed_url.port else 443
    if port < 1024:
        _logger.warning(
            f"Automated flow on ports < 1024 might require root privileges. Falling back to manual flow if server fails to start."
        )

    oauth_queue: queue.Queue = queue.Queue()

    try:

        class _CustomHTTPServer(HTTPServer):
            oauth_queue: queue.Queue = queue.Queue()

        server = _CustomHTTPServer((parsed_url.hostname, port), _OAuthCallbackHandler)
        server.oauth_queue = oauth_queue

        cert_path = None
        if parsed_url.scheme == "https":
            try:
                # Schwab requires HTTPS for callback URLs. We generate a persistent ad-hoc
                # ECDSA P-256 certificate to fulfill this requirement for localhost.
                cert_dir = os.path.join(os.path.expanduser(config_path), "certs")
                os.makedirs(cert_dir, exist_ok=True)
                cert_path = os.path.join(cert_dir, "cert.pem")
                key_path = os.path.join(cert_dir, "key.pem")

                # Only generate if it doesn't exist to allow users to permanently trust it in browser
                if not os.path.exists(cert_path) or not os.path.exists(key_path):
                    subprocess.run(
                        [
                            "openssl",
                            "req",
                            "-x509",
                            "-newkey",
                            "ec",
                            "-pkeyopt",
                            "ec_paramgen_curve:prime256v1",
                            "-keyout",
                            key_path,
                            "-out",
                            cert_path,
                            "-days",
                            "3650",
                            "-nodes",
                            "-subj",
                            f"/CN={parsed_url.hostname}",
                            "-addext",
                            f"subjectAltName=DNS:{parsed_url.hostname},DNS:localhost,IP:127.0.0.1",
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.load_cert_chain(certfile=cert_path, keyfile=key_path)
                server.socket = context.wrap_socket(server.socket, server_side=True)
            except Exception as e:
                _logger.warning(
                    f"Failed to generate or load adhoc SSL certificate: {e}. Falling back to manual flow."
                )
                server.server_close()
                return manual_auth_flow(auth_url, callback_url, logger=_logger)

        # Run the server in a daemon thread to avoid blocking the main execution.
        # This allows us to open the browser and wait for the callback concurrently.
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        print(f"\n[Schwab API] Please authenticate in the opened browser window.")
        print(f"If the browser doesn't open, navigate to:\n{auth_url}\n")
        if cert_path:
            print(
                f"Note: A self-signed certificate is used. You can permanently trust the certificate at: {cert_path}"
            )

        try:
            webbrowser.open(auth_url)
        except Exception as e:
            _logger.warning(f"Could not open browser automatically: {e}")

        try:
            # We use a Queue to safely pass the redirect path from the server thread
            # (which runs in _OAuthCallbackHandler.do_GET) back to the main thread.
            callback_path = oauth_queue.get(timeout=timeout)

            # Construct the full callback URL
            scheme = parsed_url.scheme or "https"
            result_url = f"{scheme}://{parsed_url.netloc}{callback_path}"
            server.shutdown()
            server.server_close()
            return result_url

        except queue.Empty:
            print(f"\n[Schwab API] Timed out waiting for browser callback.")
            server.shutdown()
            server.server_close()
            return manual_auth_flow(auth_url, callback_url, logger=_logger)

    except Exception as e:
        _logger.warning(
            f"Failed to start local HTTP server on {parsed_url.hostname}:{port}: {e}. Falling back to manual flow."
        )
        return manual_auth_flow(auth_url, callback_url, logger=_logger)


def default_auth_flow(
    auth_url: str,
    callback_url: str,
    config_path: str = "~/.config/schwab-api",
    logger: Optional[logging.Logger] = None,
) -> str:
    """Default flow: tries automated, falls back to manual."""
    return automated_auth_flow(
        auth_url, callback_url, config_path=config_path, logger=logger
    )
