SERVICE_ID = "scanner"


def scanner_url(*args, **kwargs) -> str:
    from .core import scanner_url as _scanner_url

    return _scanner_url(*args, **kwargs)


def service_manifest() -> dict:
    from .core import service_manifest as _service_manifest

    return _service_manifest()


def urirun_service() -> dict:
    from .core import urirun_service as _urirun_service

    return _urirun_service()


__all__ = ["SERVICE_ID", "scanner_url", "service_manifest", "urirun_service"]
