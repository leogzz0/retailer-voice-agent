from nopalia_api import schemas


class ToolError(Exception):
    """An error the agent can relay: `code` for logs/tests, `message_es` for the conversation."""

    def __init__(
        self, status_code: int, code: str, message_es: str, fields: list[str] | None = None
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.body = schemas.ErrorBody(code=code, message_es=message_es, fields=fields)
