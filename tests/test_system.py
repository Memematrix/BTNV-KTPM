import os
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import AsyncExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values

test_environment = dotenv_values(Path(__file__).resolve().parents[1] / ".env.example")
test_environment.update({
    "SECRET_KEY": "test-jwt-secret-with-at-least-32-bytes",
    "GATEWAY_SECRET": "test-gateway-secret-with-at-least-32-bytes",
    "MINIO_ACCESS_KEY": "test-minio-access-key",
    "MINIO_SECRET_KEY": "test-minio-secret-key",
})
for key, value in test_environment.items():
    if value is not None:
        os.environ.setdefault(key, value)

import httpx
import jwt
from fastapi import HTTPException

from src.common.auth.jwt import create_access_token, verify_access_token
from src.common.config import settings
from src.common.storage import AvatarStorage, get_avatar_storage
from src.gateway import RateLimiter, create_app as create_gateway
from src.services.orders import create_app as create_orders
from src.services.users import create_app as create_users


class ServiceTransport(httpx.AsyncBaseTransport):
    def __init__(self, users, orders):
        self.routes = {
            "users.test": httpx.ASGITransport(app=users),
            "orders.test": httpx.ASGITransport(app=orders),
        }
        self.requests = []
        self.failure = None

    async def handle_async_request(self, request):
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure("Upstream unavailable", request=request)
        return await self.routes[request.url.host].handle_async_request(request)


class SystemTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.stack = AsyncExitStack()
        await self.stack.__aenter__()
        self.addAsyncCleanup(self.stack.aclose)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.user_db = Path(directory) / "users.db"
        self.order_db = Path(directory) / "orders.db"
        self.users = create_users(f"sqlite+aiosqlite:///{self.user_db}")
        self.orders = create_orders(f"sqlite+aiosqlite:///{self.order_db}")
        self.transport = ServiceTransport(self.users, self.orders)
        self.gateway = create_gateway("http://users.test", "http://orders.test", self.transport)
        for app in (self.users, self.orders, self.gateway):
            await self.stack.enter_async_context(app.router.lifespan_context(app))
        self.client = await self.stack.enter_async_context(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.gateway), base_url="http://gateway.test"
        ))
        self.direct_users = await self.stack.enter_async_context(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.users), base_url="http://users.test"
        ))
        self.direct_orders = await self.stack.enter_async_context(httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.orders), base_url="http://orders.test"
        ))
        response = await self.client.post("/users/register", json={
            "username": "alice", "password": "secret123", "name": "Alice",
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.user = response.json()
        response = await self.client.post("/users/login", json={"username": "alice", "password": "secret123"})
        self.assertEqual(response.status_code, 200, response.text)
        self.token = response.json()["access_token"]
        self.auth = {"Authorization": f"Bearer {self.token}"}
        self.now = [100.0]
        self.gateway.state.limiter = RateLimiter(clock=lambda: self.now[0])
        self.transport.requests.clear()

    async def test_separate_databases_and_routing(self):
        for path, expected in ((self.user_db, "users"), (self.order_db, "orders")):
            with sqlite3.connect(path) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertEqual(tables, {expected})
        response = await self.client.get("/users/me", headers=self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.user["id"])
        response = await self.client.post("/orders", headers=self.auth, json={"total_amount": "19.95"})
        self.assertEqual(response.status_code, 201, response.text)
        order = response.json()
        self.assertEqual(order["user_id"], self.user["id"])
        self.assertEqual(order["total_amount"], "19.95")
        self.assertEqual((await self.client.get(f"/orders/{order['id']}", headers=self.auth)).status_code, 200)
        self.assertEqual((await self.client.delete(f"/orders/{order['id']}", headers=self.auth)).status_code, 204)
        self.assertEqual((await self.client.get("/orders", headers=self.auth)).json(), [])
        hosts = {request.url.host for request in self.transport.requests}
        self.assertEqual(hosts, {"users.test", "orders.test"})
        self.assertTrue(all("authorization" not in request.headers for request in self.transport.requests))
        self.assertTrue(all(request.headers["x-user-id"] == self.user["id"] for request in self.transport.requests))

    async def test_jwt_rejection_before_forwarding(self):
        expired = create_access_token(uuid.UUID(self.user["id"]), "customer", expires_minutes=-1)
        for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": f"Bearer {expired}"}):
            response = await self.client.get("/users/me", headers=headers)
            self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.transport.requests, [])

    async def test_identity_header_spoofing(self):
        forged = {"x-user-id": str(uuid.uuid4()), "x-user-role": "admin", "x-gateway-key": "fake"}
        self.assertEqual((await self.client.get("/orders", headers=forged)).status_code, 401)
        self.assertEqual((await self.direct_orders.get("/orders", headers=forged)).status_code, 401)
        self.assertEqual((await self.direct_orders.get("/orders", headers=[(b"x-gateway-key", b"\xff")])).status_code, 401)
        response = await self.client.post("/orders", headers=self.auth | forged, json={})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["user_id"], self.user["id"])
        self.assertEqual(self.transport.requests[-1].headers["x-user-role"], "customer")

    async def test_ten_requests_per_rolling_second(self):
        responses = [await self.client.get("/orders", headers=self.auth) for _ in range(11)]
        self.assertEqual([response.status_code for response in responses], [200] * 10 + [429])
        self.assertEqual(responses[-1].headers["Retry-After"], "1")
        self.assertEqual(len(self.transport.requests), 10)
        self.now[0] += 1.01
        self.assertEqual((await self.client.get("/orders", headers=self.auth)).status_code, 200)

    async def test_dashboard_ownership_and_admin_filter(self):
        response = await self.direct_users.post("/users/register", json={
            "username": "bob", "password": "secret123", "name": "Bob",
        })
        bob_id = uuid.UUID(response.json()["id"])
        bob_auth = {"Authorization": f"Bearer {create_access_token(bob_id, 'customer')}"}
        bob_order = (await self.client.post("/orders", headers=bob_auth, json={"total_amount": "7.00"})).json()
        alice_order = (await self.client.post("/orders", headers=self.auth, json={"total_amount": "3.50"})).json()
        self.assertEqual((await self.client.get(f"/orders/{bob_order['id']}", headers=self.auth)).status_code, 404)
        self.assertEqual((await self.client.delete(f"/orders/{bob_order['id']}", headers=self.auth)).status_code, 404)
        admin_auth = {"Authorization": f"Bearer {create_access_token(uuid.UUID(self.user['id']), 'admin')}"}
        self.assertEqual(len((await self.client.get("/orders", headers=admin_auth)).json()), 2)
        response = await self.client.get("/dashboard", headers=admin_auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["user"]["id"], self.user["id"])
        self.assertEqual([order["id"] for order in response.json()["orders"]], [alice_order["id"]])
        self.assertEqual(str(self.transport.requests[-1].url.query, "ascii"), "mine=true")

    async def test_validation_and_account_errors(self):
        response = await self.client.post("/users/register", json={"username": "alice", "password": "secret123", "name": "Alice"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual((await self.client.post("/users/login", json={"username": "alice", "password": "wrong"})).status_code, 401)
        for payload in ({"user_id": str(uuid.uuid4())}, {"total_amount": "-1"}, {"total_amount": "1.001"}):
            self.assertEqual((await self.client.post("/orders", headers=self.auth, json=payload)).status_code, 422)
        self.assertEqual((await self.client.post("/users/register", json={"username": "unicode", "password": "界" * 30, "name": "Test"})).status_code, 422)

    async def test_avatar_urls_are_scoped_and_expire_in_300_seconds(self):
        storage = AvatarStorage()
        storage.internal = MagicMock()
        storage.internal.bucket_exists.return_value = True
        self.users.dependency_overrides[get_avatar_storage] = lambda: storage
        response = await self.client.post("/users/me/avatar/upload-url", headers=self.auth, json={"content_type": "image/png"})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["expires_in"], 300)
        self.assertEqual(data["method"], "PUT")
        self.assertEqual(data["object_key"], f"avatars/{self.user['id']}/avatar")
        self.assertEqual(data["headers"], {"Content-Type": "image/png"})
        parsed = urlsplit(data["upload_url"])
        self.assertEqual(parsed.netloc, settings.minio_public_endpoint)
        self.assertEqual(parse_qs(parsed.query)["X-Amz-Expires"], ["300"])
        self.assertIn(self.user["id"], parsed.path)
        self.assertEqual((await self.client.get("/users/me/avatar", headers=self.auth)).status_code, 200)
        self.assertEqual((await self.client.post("/users/me/avatar/upload-url", headers=self.auth, json={"content_type": "text/html"})).status_code, 422)

    async def test_upstream_failure_and_timeout(self):
        for failure, status in ((httpx.ConnectError, 502), (httpx.ReadTimeout, 504)):
            self.transport.failure = failure
            self.assertEqual((await self.client.get("/users/me", headers=self.auth)).status_code, status)
            self.assertEqual((await self.client.get("/dashboard", headers=self.auth)).status_code, status)

    async def test_direct_service_still_requires_valid_auth(self):
        self.assertEqual((await self.direct_users.get("/users/me")).status_code, 401)
        self.assertEqual((await self.direct_orders.get("/orders")).status_code, 401)
        self.assertEqual((await self.direct_users.get("/users/me", headers=self.auth)).status_code, 200)
        self.assertEqual((await self.direct_orders.get("/orders", headers=self.auth)).status_code, 200)

    async def test_service_redirect_keeps_the_public_gateway_host(self):
        response = await self.client.get("/orders/", headers=self.auth)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "http://gateway.test/orders")
        response = await self.client.get("/orders/", headers=self.auth, follow_redirects=True)
        self.assertEqual(response.status_code, 200)


class TokenAndLimiterTests(unittest.TestCase):
    def test_malformed_signed_claims_return_401(self):
        now = datetime.now(timezone.utc)
        good = {"sub": str(uuid.uuid4()), "role": "customer", "iat": now, "exp": now + timedelta(minutes=5)}
        invalid = [good | {"sub": "not-a-uuid"}, good | {"role": "owner"}, good | {"role": None}, good | {"role": []}]
        invalid.append({key: value for key, value in good.items() if key != "exp"})
        for payload in invalid:
            token = jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)
            with self.assertRaises(HTTPException) as error:
                verify_access_token(token)
            self.assertEqual(error.exception.status_code, 401)

    def test_limiter_is_per_client_and_uses_a_rolling_window(self):
        now = [0.0]
        limiter = RateLimiter(clock=lambda: now[0])
        for _ in range(10):
            self.assertIsNone(limiter.retry_after("alice"))
        self.assertEqual(limiter.retry_after("alice"), 1)
        self.assertIsNone(limiter.retry_after("bob"))
        now[0] = 0.99
        self.assertEqual(limiter.retry_after("alice"), 1)
        now[0] = 1.0
        self.assertIsNone(limiter.retry_after("alice"))
        now[0] = 61
        self.assertIsNone(limiter.retry_after("carol"))
        self.assertEqual(set(limiter.clients), {"carol"})


if __name__ == "__main__":
    unittest.main()
