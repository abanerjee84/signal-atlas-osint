import time
from collections import OrderedDict

from starlette.responses import JSONResponse


class RequestLimits:
    """Bound body size and per-client request counters without an unbounded resident cache."""

    def __init__(self, app):
        self.app = app
        self.clients = OrderedDict()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        now = time.monotonic()
        client = (scope.get("client") or ("unknown",))[0]
        start, count = self.clients.get(client, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        self.clients[client] = start, count + 1
        self.clients.move_to_end(client)
        while len(self.clients) > 2048:
            self.clients.popitem(last=False)
        if count >= 120:
            return await JSONResponse(
                {"detail": "Request rate limit reached"}, status_code=429, headers={"Retry-After": "60"}
            )(scope, receive, send)
        # The authenticated media route streams and enforces its own configured byte limit.
        media_upload = scope.get("path") == "/api/v1/media/evidence" and scope["method"] == "POST"
        if scope["method"] in {"POST", "PUT", "PATCH"} and not media_upload:
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > 65536:
                    return await JSONResponse({"detail": "Request body too large"}, status_code=413)(
                        scope, receive, send
                    )
                if not message.get("more_body", False):
                    break
            delivered = False
            original_receive = receive

            async def bounded_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await original_receive()

            receive = bounded_receive
        await self.app(scope, receive, send)
