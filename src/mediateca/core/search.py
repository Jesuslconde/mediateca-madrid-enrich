from __future__ import annotations

from functools import lru_cache

import meilisearch

from mediateca.core.config import settings


@lru_cache(maxsize=1)
def get_meili_client() -> meilisearch.Client:
    return meilisearch.Client(settings.meilisearch_url, settings.meilisearch_key)


def get_index():
    return get_meili_client().index(settings.meilisearch_index)
