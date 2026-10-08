from __future__ import annotations


class EpCubeError(Exception):
    pass


class EpCubeConnectionError(EpCubeError):
    pass


class EpCubeTimeoutError(EpCubeConnectionError):
    pass


class EpCubeAPIError(EpCubeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        api_status: int | None = None,
        path: str | None = None,
    ) -> None:
        self.http_status = http_status
        self.api_status = api_status
        self.path = path
        detail = []
        if path:
            detail.append(path)
        if http_status is not None:
            detail.append(f"HTTP {http_status}")
        if api_status is not None and api_status != http_status:
            detail.append(f"API status {api_status}")
        suffix = f" ({', '.join(detail)})" if detail else ""
        super().__init__(f"{message}{suffix}")


class EpCubeAuthError(EpCubeAPIError):
    pass


class EpCubeForbiddenError(EpCubeAuthError):
    pass


class EpCubeRateLimitError(EpCubeAPIError):
    pass


class EpCubeServerError(EpCubeAPIError):
    pass


class EpCubeNotFoundError(EpCubeAPIError):
    pass


class EpCubeResponseError(EpCubeError):
    def __init__(self, message: str, *, path: str | None = None) -> None:
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


class EpCubeCaptchaError(EpCubeError):
    pass


class EpCubeLoginError(EpCubeError):
    pass
