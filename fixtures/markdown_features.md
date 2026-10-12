# Integration Guide

This guide demonstrates how to configure API endpoints and authenticate client requests.

For comprehensive API definitions, consult the [Official Documentation](https://api.example.com/v1/reference).

## Supported Endpoints

| Method | Endpoint | Description | Status Code |
|---|---|---|---|
| `GET` | `/v1/users` | List active users | 200 OK |
| `POST` | `/v1/tokens` | Generate authentication token | 201 Created |
| `DELETE` | `/v1/sessions` | Invalidate current session | 204 No Content |

## Python Client Implementation

The following snippet demonstrates client initialization:

```python
# Function names that happen to contain prose keywords should never trigger lint rules
def delve_into_logs(client_id: str):
    """Leverage cached credentials and unlock connection."""
    endpoint = "https://api.example.com/v1/metrics"
    return {"status": "connected", "endpoint": endpoint}
```

Run tests using `pytest tests/test_client.py` before submitting pull requests.
