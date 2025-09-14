import json
import logging
from typing import Any


class JsonFormatter(logging.Formatter):
    """Logging formatter that outputs JSON."""

    def format(self, record: logging.LogRecord) -> str:  # pragma: no cover - trivial
        log_record: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_record["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def configure_logging() -> None:
    """Configure root logger to use JSON formatting."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
