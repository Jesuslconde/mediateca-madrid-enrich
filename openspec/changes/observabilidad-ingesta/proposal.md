# Proposal

## Why

Una ingesta de 67.215 fichas puede durar días y fallar por sesión, reCAPTCHA o errores del OPAC. Sin estado, métricas y cobertura no se puede saber qué se ha procesado, qué falta, qué falla ni cuánto tarda.

## What Changes

- Exponer el estado de los trabajos de ingesta y la cobertura del catálogo desde API y CLI.
- Añadir métricas: procesados, errores, captchas, renovaciones de sesión, pendientes y tiempo medio.
- Añadir logs estructurados con job, lote, TITN y resultado.
- Exponer la salud del worker y el último heartbeat.
- Añadir alertas básicas cuando un trabajo falla repetidamente o la cobertura se estanca.

## Capabilities

### New Capabilities

- `observabilidad-ingesta`: estado, métricas, cobertura, logs y salud del worker.

### Modified Capabilities

Ninguna.

## Impact

- `backend/src/mediateca/api/routers/ingest.py`: endpoints de estado y cobertura.
- `backend/src/mediateca/api/schemas.py`: respuestas de estado.
- `backend/src/mediateca/cli.py`: `mediateca ingest-status`.
- `backend/src/mediateca/core/logging.py`: logs estructurados.
- Tests de endpoints y consultas de cobertura.
