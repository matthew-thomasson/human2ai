# Production Service Level Objectives and Requirements

All production microservices MUST satisfy the availability targets defined below.

## Key Performance Indicators

- Uptime availability target: 99.95% over any rolling 30-day window.
- Ingestion latency p99: MUST NOT exceed 150ms.
- Default service port: 8080 (HTTPS required via port 8443).
- Retry policy: maximum of 3 attempts with exponential backoff starting at 200ms.
- Memory ceiling: 512MB per replica container.

## Compliance Deadlines

Audit logs for Q3 2026 MUST be archived by 2026-11-15.
Security certificate renewal is scheduled for October 20, 2026.

Operators SHALL configure the `--max-retries=3` flag and set `SERVICE_ENV=production` before deployment.