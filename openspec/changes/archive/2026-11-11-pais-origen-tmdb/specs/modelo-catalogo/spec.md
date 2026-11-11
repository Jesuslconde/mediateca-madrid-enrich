# Spec Delta

## ADDED Requirements

### Requirement: Campos de enriquecimiento TMDB en la edición

Cada edición MUST poder almacenar `paises_origen` como lista de códigos ISO 3166-1 alfa-2 en mayúsculas, `tmdb_id` como identificador numérico opcional y `tmdb_enriched_at` como fecha opcional de sincronización. La lista SHALL admitir el valor vacío cuando no haya países conocidos.

#### Scenario: Edición emparejada en TMDB

- **WHEN** una edición se empareja con una película de TMDB
- **THEN** la edición guarda su `tmdb_id`, la lista `paises_origen` y `tmdb_enriched_at`

#### Scenario: Edición sin emparejar

- **WHEN** una edición no se empareja con TMDB
- **THEN** la edición conserva `paises_origen` como lista vacía
- **AND** `tmdb_id` y `tmdb_enriched_at` permanecen vacíos

### Requirement: Independencia del país del OPAC

El campo `pais` procedente del OPAC MUST conservarse como dato independiente de `paises_origen`. La actualización de los campos TMDB SHALL NOT sobrescribir, vaciar ni reinterpretar `pais`.

#### Scenario: Edición con país del OPAC y países de TMDB

- **WHEN** una edición tiene `pais` del OPAC y además se enriquece con TMDB
- **THEN** se conservan ambos datos
- **AND** `pais` mantiene el valor original del MARC

#### Scenario: Edición sin país en el OPAC

- **WHEN** una edición no tiene `pais` del OPAC
- **THEN** `paises_origen` puede contener los países obtenidos de TMDB
- **AND** no se inventa un `pais` del OPAC
