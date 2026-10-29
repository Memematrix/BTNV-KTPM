# Gateway latency measurement

Measured: 2026-10-29T02:27:51.802593+00:00

100 successful requests per path to `/users/me`, after 5 warm-up requests.

| Path | Mean (ms) | Median (ms) | p95 (ms) |
|---|---:|---:|---:|
| Direct User service | 2.622 | 2.654 | 3.71 |
| Through gateway | 5.144 | 5.078 | 6.717 |

Mean gateway overhead: **2.523 ms**.

Sequential paired requests, alternating order, persistent HTTP connections. Direct service validates JWT; gateway validates JWT and forwards trusted identity. Failed requests are not included: they abort the run.

Pairs are separated by 0.12s to respect the 10 req/s rate limit. These local measurements depend on machine load and are not a production capacity test.
