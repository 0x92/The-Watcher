from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Dict, Optional

from flask import abort
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash


@dataclass
class User(UserMixin):
    id: int
    email: str
    role: str
    password_hash: str


USERS: Dict[str, User] = {
    "admin@example.com": User(
        id=1,
        email="admin@example.com",
        role="admin",
        password_hash=generate_password_hash("adminpass"),
    ),
    "analyst@example.com": User(
        id=2,
        email="analyst@example.com",
        role="analyst",
        password_hash=generate_password_hash("analystpass"),
    ),
    "viewer@example.com": User(
        id=3,
        email="viewer@example.com",
        role="viewer",
        password_hash=generate_password_hash("viewerpass"),
    ),
}


def get_user_by_email(email: str) -> Optional[User]:
    return USERS.get(email)


def get_user_by_id(user_id: str) -> Optional[User]:
    for user in USERS.values():
        if str(user.id) == str(user_id):
            return user
    return None


def role_required(role: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


__all__ = [
    "User",
    "USERS",
    "get_user_by_email",
    "get_user_by_id",
    "role_required",
]
