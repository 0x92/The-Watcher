from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response model for health endpoint."""

    status: str = "ok"


def health() -> tuple[dict, int]:
    """Return application health status."""
    return HealthResponse().model_dump(), 200


__all__ = ["HealthResponse", "health"]
