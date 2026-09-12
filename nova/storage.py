"""Private evidence storage, shared by the API and worker across instances."""

import re
from functools import lru_cache

from nova.providers import ProviderUnavailable


@lru_cache
def cloud_client():
    from google.cloud import storage

    return storage.Client()


def blob(settings, key):
    if not re.fullmatch(r"[a-f0-9-]{36}", key):
        raise ProviderUnavailable("Invalid evidence storage key.")
    return cloud_client().bucket(settings.storage_bucket).blob("documents/" + key)


def write_document(settings, key, content, content_type):
    if settings.storage_bucket:
        try:
            blob(settings, key).upload_from_string(
                content, content_type=content_type, if_generation_match=0, timeout=60
            )
        except Exception:
            raise ProviderUnavailable("Evidence storage upload failed.") from None
    else:
        (settings.storage_path / key).write_bytes(content)


def read_document(settings, key):
    if settings.storage_bucket:
        try:
            return blob(settings, key).download_as_bytes(timeout=60)
        except Exception:
            raise ProviderUnavailable("Evidence storage download failed.") from None
    return (settings.storage_path / key).read_bytes()
