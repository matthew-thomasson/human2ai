# Database Migration Runbook

This guide describes how to run schema migrations on production PostgreSQL nodes.

Before starting, export your database credentials and verify connectivity:

```bash
export DB_PORT=5432
pg_isready -h db-primary.internal -p $DB_PORT
```

## Migration Steps

1. Stop the worker queues to prevent new write conflicts.
2. Run the migration script using the deployment CLI.
3. Check table constraints and row indices.
4. Restart background workers and monitor replication lag.

Always test on staging first.

Keep writes disabled until replica lag drops under two seconds. If an index creation stalls, cancel the query immediately. If replica lag exceeds thirty seconds during an active migration window, halt further DDL operations until all secondary replica nodes synchronize with the primary instance. Rolling back takes roughly ten minutes and requires administrative rights.
