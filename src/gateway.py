import asyncio
import math
import time
from collections import deque
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from src.common.auth.jwt import verify_access_token
from src.common.config import settings
from src.schemas import DashboardResponse

# These headers belong to one connection and must not pass through a proxy.
HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "host", "content-length",
    "content-encoding",
}
IDENTITY_HEADERS = {"x-gateway-key", "x-user-id", "x-user-role"}
PUBLIC_ENDPOINTS = {("POST", "/users/login"), ("POST", "/users/register")}
METADATA_PATHS = {"/", "/health", "/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


class RateLimiter:
    """Exact rolling one-second window per socket client IP, for one gateway worker."""
    def __init__(self, limit: int = 10, clock=time.monotonic):
        self.limit = limit
        self.clock = clock
        self.clients: dict[str, deque[float]] = {}
        self.last_cleanup = clock()

    def retry_after(self, client: str) -> int | None:
        now = self.clock()
        if now - self.last_cleanup >= 60:
            self.clients = {
                key: values for key, values in self.clients.items()
                if values and values[-1] > now - 1
            }
            self.last_cleanup = now
        requests = self.clients.setdefault(client, deque())
        while requests and requests[0] <= now - 1:
            requests.popleft()
        if len(requests) >= self.limit:
            return max(1, math.ceil(requests[0] + 1 - now))
        requests.append(now)
        return None


def create_app(
    user_service_url: str | None = None,
    order_service_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    user_url = (user_service_url or settings.user_service_url).rstrip("/")
    order_url = (order_service_url or settings.order_service_url).rstrip("/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            timeout=settings.upstream_timeout_seconds, transport=transport, trust_env=False
        ) as client:
            app.state.http = client
            yield

    app = FastAPI(title="User / Order API Gateway", lifespan=lifespan)
    app.state.limiter = RateLimiter()

    @app.middleware("http")
    async def gateway_checks(request: Request, call_next):
        if request.url.path in METADATA_PATHS:
            return await call_next(request)
        # Forwarded-for is client-controlled in this local, directly exposed gateway.
        client_ip = request.client.host if request.client else "unknown"
        retry_after = app.state.limiter.retry_after(client_ip)
        if retry_after is not None:
            return JSONResponse(
                {"detail": "Rate limit exceeded: 10 requests per second"},
                status_code=429, headers={"Retry-After": str(retry_after)},
            )
        if (request.method, request.url.path) not in PUBLIC_ENDPOINTS:
            authorization = request.headers.get("authorization", "").split()
            if len(authorization) != 2 or authorization[0].lower() != "bearer":
                return JSONResponse(
                    {"detail": "Bearer access token required"}, status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            try:
                request.state.identity = verify_access_token(authorization[1])
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
        return await call_next(request)

    def upstream_headers(request: Request) -> dict[str, str]:
        connection_headers = {
            name.strip().lower() for name in request.headers.get("connection", "").split(",")
        }
        blocked = HOP_HEADERS | IDENTITY_HEADERS | connection_headers | {"authorization", "cookie"}
        headers = {key: value for key, value in request.headers.items() if key.lower() not in blocked}
        identity = getattr(request.state, "identity", None)
        if identity is not None:
            headers.update({
                "x-gateway-key": settings.gateway_secret.get_secret_value(),
                "x-user-id": str(identity.id),
                "x-user-role": identity.role,
            })
        return headers

    async def send(request: Request, url: str, **kwargs) -> httpx.Response:
        try:
            return await app.state.http.request(
                request.method if "method" not in kwargs else kwargs.pop("method"),
                url, headers=upstream_headers(request), **kwargs,
            )
        except httpx.TimeoutException as exc:
            raise HTTPException(status_code=504, detail="Upstream service timed out") from exc
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail="Upstream service unavailable") from exc

    def proxy_response(response: httpx.Response) -> Response:
        connection_headers = {
            name.strip().lower() for name in response.headers.get("connection", "").split(",")
        }
        result = Response(content=response.content, status_code=response.status_code)
        for name, value in response.headers.multi_items():
            if name.lower() not in HOP_HEADERS | connection_headers:
                result.headers.append(name, value)
        return result

    async def proxy(request: Request, base: str):
        url = httpx.URL(base).copy_with(raw_path=request.scope["raw_path"])
        url = url.copy_with(query=request.scope["query_string"])
        response = await send(request, str(url), content=await request.body())
        location = response.headers.get("location", "")
        if location.startswith(f"{base}/"):
            response.headers["location"] = str(request.base_url).rstrip("/") + location[len(base):]
        return proxy_response(response)

    @app.api_route("/users", methods=METHODS, tags=["routing"])
    @app.api_route("/users/{path:path}", methods=METHODS, tags=["routing"])
    async def users(request: Request, path: str = ""):
        return await proxy(request, user_url)

    @app.api_route("/orders", methods=METHODS, tags=["routing"])
    @app.api_route("/orders/{path:path}", methods=METHODS, tags=["routing"])
    async def orders(request: Request, path: str = ""):
        return await proxy(request, order_url)

    @app.get("/dashboard", response_model=DashboardResponse, tags=["aggregation"])
    async def dashboard(request: Request):
        user, orders = await asyncio.gather(
            send(request, f"{user_url}/users/me", method="GET"),
            send(request, f"{order_url}/orders?mine=true", method="GET"),
        )
        for upstream in (user, orders):
            if upstream.status_code >= 400:
                return proxy_response(upstream)
        try:
            return DashboardResponse.model_validate({"user": user.json(), "orders": orders.json()})
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=502, detail="Invalid upstream response") from exc

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "gateway"}

    @app.get("/")
    async def index():
        return {
            "service": "User / Order API Gateway",
            "routes": ["/users/register", "/users/login", "/users/me", "/orders", "/dashboard", "/users/me/avatar/upload-url"],
            "documentation": "/docs",
        }

    return app


app = create_app()
