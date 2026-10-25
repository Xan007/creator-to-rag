# API pública de consultas

La API pública se inicia con `crag-query-api` (`src.api.public:app`) y usa
credenciales Bearer por usuario. Expone `/health`, `/libraries`, `/query` y
`/libraries/{library_id}/sources`. Las rutas de administración descritas abajo
pertenecen exclusivamente a `crag-api`, ejecutado en tu PC.

Configuración, límites y publicación: [guía de despliegue](deployment.md).

# HTTP API

FastAPI service providing background ingest workflows, content management, and grounded query synthesis.

## Running the API Service

```bash
# Start with Uvicorn
.venv\Scripts\python.exe -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

The interactive OpenAPI (Swagger UI) documentation and schema specifications are served automatically at:
- `http://127.0.0.1:8000/docs`
- ReDoc alternative view: `http://127.0.0.1:8000/redoc`

## Authentication and Multi-Tenancy

- **API Key:** When `CRAG_API_KEY` is configured in `.env`, requests must provide `Authorization: Bearer <API_KEY>` or `X-API-Key: <API_KEY>`.
- **Tenant Context:** Requests specify operating identity via `X-User-Id: <UUID>` or `X-Username: <STRING>`. If omitted, the server defaults to `CRAG_USER` or the provisioned default user.
