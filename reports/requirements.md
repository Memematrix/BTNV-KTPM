# Assignment completion checklist

Verified on 2026-10-29 with separate local processes for the User service,
Order service, gateway and a real MinIO server built from upstream
`RELEASE.2025-10-15T17-29-55Z`. Temporary databases and processes were removed
or stopped after verification. No external deployment was performed.

| Requirement | Implementation | Verification |
|---|---|---|
| Two services plus one API Gateway | `src/services/users.py`, `src/services/orders.py`, `src/gateway.py`; separate SQLite files | Isolated table checks in integration tests; live health checks for three processes |
| Route `/users` and `/orders` | Gateway forwards requests to configured service URLs | Registration, login, profile and order operations through the live gateway |
| JWT validation at gateway | Gateway checks signature, required claims, expiry and UUID; forwards trusted identity with a separate secret | Missing/invalid/expired JWT rejection; forged header rejection; upstream request has verified identity and no bearer JWT |
| 10 requests/second | Rolling one-second window per client IP; 429 and `Retry-After` on excess | Unit clock-boundary checks plus live concurrent burst: ten 200 responses and one 429 |
| `/dashboard` aggregation | Concurrent calls to User profile and Order service, with `mine=true` | Ownership and admin filtering tests; live profile and own order combination |
| MinIO avatar Valet Key, five-minute expiry | User-scoped presigned PUT URL; `X-Amz-Expires=300`; private bucket | Actual direct PUT and byte-for-byte GET; another user's object key and an expired five-minute signature both rejected |
| Gateway versus direct latency | `scripts/benchmark.py` | 100 successful requests per path; raw samples and summary in `latency.json` and `latency.md` |

12 automated integration/unit tests passed. 22 live smoke checks passed.
See `smoke.json` for the live check list.

The latency run used persistent connections to the same authenticated
`/users/me` endpoint. Mean latency was 2.622 ms direct and 5.144 ms through the
gateway; measured mean overhead was 2.523 ms (computed from unrounded samples).
These are local measurements, not deployment capacity estimates.

Docker Compose configuration was validated and the Python application image
built successfully. The complete container stack was not run to completion:
the initial MinIO compilation overwhelmed the Docker VM's 2 GB memory limit.
`Dockerfile.minio` now limits compilation concurrency and Go memory usage. The
full end-to-end verification above used standalone processes, not containers.
