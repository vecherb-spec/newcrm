from enum import StrEnum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, UUIDTimestampMixin


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    SALES = "SALES"
    ENGINEER = "ENGINEER"
    OPERATIONS = "OPERATIONS"
    WAREHOUSE = "WAREHOUSE"
    FINANCE = "FINANCE"


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.ADMIN)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
