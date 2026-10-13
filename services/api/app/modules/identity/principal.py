import uuid
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Principal:
    """The authenticated employee for the current request."""

    user_id: uuid.UUID
    subject: str
    email: str | None
    name: str | None
    roles: frozenset[str]
    auth_method: Literal["session", "bearer"]

    def has_role(self, role: str) -> bool:
        return role in self.roles
