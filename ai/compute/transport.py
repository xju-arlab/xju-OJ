"""Small bounded HTTP client; credentials never follow redirects or enter errors."""
import json
import urllib.error
import urllib.parse
import urllib.request


class RemoteError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise RemoteError("Unexpected HTTP redirect")


class Client:
    def __init__(self, base_url, token, scheme):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("Invalid service URL")
        self.base = base_url.rstrip("/") + "/"
        self.authorization = scheme + " " + token
        self.opener = urllib.request.build_opener(NoRedirect())

    def call(self, method, path, data=None):
        if path.startswith(("/", "http:", "https:")) or ".." in path:
            raise ValueError("Service paths must be relative")
        raw = None if data is None else json.dumps(data, allow_nan=False).encode()
        request = urllib.request.Request(self.base + path, data=raw, method=method,
                                         headers={"Authorization": self.authorization, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=15) as response:
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise RemoteError("Service response exceeded limit")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            raise RemoteError("Service returned HTTP " + str(exc.code)) from None
        except (OSError, ValueError) as exc:
            raise RemoteError("Service request failed (" + type(exc).__name__ + ")") from None

    def put_zip(self, url, content, allowed_origin):
        parsed = urllib.parse.urlsplit(url)
        origin = parsed.scheme + "://" + parsed.netloc
        if origin != allowed_origin.rstrip("/") or parsed.username or parsed.fragment:
            raise RemoteError("Object storage origin is not allowed")
        request = urllib.request.Request(url, data=content, method="PUT", headers={"Content-Type": "application/zip"})
        try:
            with self.opener.open(request, timeout=20) as response:
                response.read(1024)
        except (OSError, ValueError):
            raise RemoteError("Object upload failed") from None
