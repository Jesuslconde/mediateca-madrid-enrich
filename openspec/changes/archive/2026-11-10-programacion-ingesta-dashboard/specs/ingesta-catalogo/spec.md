# Spec Delta

## MODIFIED Requirements

### Requirement: Actualización incremental

El sistema SHALL soportar descubrimientos incrementales reutilizando el `cursor_doc` y `cursor_titn` del último descubrimiento completado, y SHALL programar un barrido completo periódico como red de seguridad.

#### Scenario: Novedades de vídeos

- **WHEN** se ejecuta la recolección incremental
- **THEN** solo se procesan los registros nuevos o modificados del periodo configurado
- **AND** el resto del catálogo permanece intacto

#### Scenario: Sin descubrimiento previo

- **WHEN** se solicita un descubrimiento incremental y no hay un descubrimiento completado
- **THEN** se ejecuta un descubrimiento completo
- **AND** queda registrado como modo `full`

#### Scenario: Barrido completo de seguridad

- **WHEN** se cumple el intervalo de barrido completo
- **THEN** se ejecuta un descubrimiento completo aunque exista un cursor incremental
- **AND** se actualizan las marcas de última visualización y las ausencias

## ADDED Requirements

### Requirement: Enriquecimiento de registros nuevos

El enriquecimiento programado MUST poder limitarse a las ediciones descubiertas desde un instante `since` y SHALL conservar el resto de pendientes para ejecuciones manuales.

#### Scenario: Solo nuevos

- **WHEN** un enriquecimiento recibe un `since`
- **THEN** selecciona solo ediciones con `discovery_seen_at` mayor o igual que `since` y sin `detail_fetched_at`
- **AND** no procesa stubs anteriores

#### Scenario: Enriquecimiento manual completo

- **WHEN** el operador lanza "Enriquecer pendientes" desde el dashboard
- **THEN** se seleccionan todos los stubs pendientes, sin filtro `since`
- **AND** se respeta el límite de lote configurado
