"""Driver interface — common contract for browser backends."""


class Driver:
    """Base class for all browser drivers. All methods raise on failure."""

    def navigate(self, url: str) -> dict:
        raise NotImplementedError

    def evaluate(self, js: str):
        raise NotImplementedError

    def screenshot(self) -> bytes:
        raise NotImplementedError

    def send_keys(self, text: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
