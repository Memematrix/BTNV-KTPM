"""Verify the running services, gateway and real MinIO avatar uploads."""
import argparse
import base64
import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx
from dotenv import dotenv_values
from minio import Minio


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway", default="http://127.0.0.1:8000")
    parser.add_argument("--users", default="http://127.0.0.1:8001")
    parser.add_argument("--orders", default="http://127.0.0.1:8002")
    args = parser.parse_args()
    gateway = args.gateway.rstrip("/")
    env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    def config(key, default=None):
        value = os.environ.get(key) or env.get(key) or default
        if value is None:
            raise RuntimeError(f"{key} must be set in .env or the environment")
        return value
    checks = []
    def check(condition, label):
        if not condition:
            raise AssertionError(label)
        checks.append(label)
        print(f"PASS: {label}")
    with httpx.Client(timeout=20, trust_env=False) as client:
        for base in (gateway, args.users.rstrip("/"), args.orders.rstrip("/")):
            check(client.get(f"{base}/health").status_code == 200, f"Health {base}")
        time.sleep(1.05)
        username, password = f"smoke-{uuid.uuid4().hex[:16]}", uuid.uuid4().hex
        response = client.post(f"{gateway}/users/register", json={"username": username, "password": password, "name": "Smoke test"})
        check(response.status_code == 201, "User registration routed through gateway")
        user_id = response.json()["id"]
        response = client.post(f"{gateway}/users/login", json={"username": username, "password": password})
        check(response.status_code == 200, "Login returns JWT")
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        check(client.get(f"{gateway}/orders").status_code == 401, "Gateway rejects missing JWT")
        forged = {"X-User-Id": user_id, "X-User-Role": "admin", "X-Gateway-Key": "forged"}
        check(client.get(f"{gateway}/orders", headers=forged).status_code == 401, "Gateway rejects forged identity")
        check(client.get(f"{args.orders.rstrip('/')}/orders", headers=forged).status_code == 401, "Direct service rejects forged identity")
        check(client.get(f"{gateway}/users/me", headers={"Authorization": "Bearer invalid"}).status_code == 401, "Gateway rejects invalid JWT")
        check(client.get(f"{gateway}/users/me", headers=headers).json()["id"] == user_id, "User profile routing")
        response = client.post(f"{gateway}/orders", headers=headers, json={"total_amount": "12.50"})
        check(response.status_code == 201, "Create order through gateway")
        order_id = response.json()["id"]
        response = client.get(f"{gateway}/dashboard", headers=headers)
        check(response.status_code == 200 and response.json()["user"]["id"] == user_id and response.json()["orders"][0]["id"] == order_id, "Dashboard aggregates current user and their orders")
        time.sleep(1.05)
        response = client.post(f"{gateway}/users/me/avatar/upload-url", headers=headers, json={"content_type": "image/png"})
        check(response.status_code == 200, "Issue avatar upload URL")
        upload = response.json()
        parsed = urlsplit(upload["upload_url"])
        check(upload["expires_in"] == 300 and parse_qs(parsed.query)["X-Amz-Expires"] == ["300"], "Presigned PUT expires after five minutes")
        check(upload["object_key"] == f"avatars/{user_id}/avatar", "Presigned PUT restricted to current user's avatar key")
        response = client.put(upload["upload_url"], content=PNG, headers=upload["headers"])
        check(response.status_code == 200, "Real direct upload to MinIO without application JWT")
        response = client.get(f"{gateway}/users/me/avatar", headers=headers)
        check(response.status_code == 200, "Issue avatar download URL")
        response = client.get(response.json()["download_url"])
        check(response.status_code == 200 and response.content == PNG, "Download matches uploaded avatar bytes")
        anonymous = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
        check(client.get(anonymous).status_code == 403, "Avatar bucket is private")
        forged_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path.replace(user_id, str(uuid.uuid4())), parsed.query, ""))
        check(client.put(forged_url, content=PNG).status_code == 403, "Signed URL cannot target another user's object")
        signer = Minio(
            parsed.netloc,
            access_key=config("MINIO_ACCESS_KEY"),
            secret_key=config("MINIO_SECRET_KEY"),
            secure=parsed.scheme == "https", region=config("MINIO_REGION", "us-east-1"),
        )
        expired = signer.get_presigned_url(
            "PUT", config("MINIO_BUCKET", "avatars"), upload["object_key"],
            expires=timedelta(seconds=300),
            request_date=datetime.now(timezone.utc) - timedelta(minutes=6),
        )
        response = client.put(expired, content=PNG)
        check(response.status_code == 403 and "expired" in response.text.lower(), "MinIO rejects an expired five-minute URL")
        time.sleep(1.05)
        with ThreadPoolExecutor(max_workers=11) as pool:
            responses = list(pool.map(lambda _: client.get(f"{gateway}/orders", headers=headers), range(11)))
        statuses = sorted(response.status_code for response in responses)
        check(statuses == [200] * 10 + [429], "Gateway permits ten requests and rejects request eleven")
    result = {"measured_at_utc": datetime.now(timezone.utc).isoformat(), "passed": len(checks), "checks": checks}
    output = Path("reports/smoke.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"All {len(checks)} live checks passed.")


if __name__ == "__main__":
    main()
