"""SQLAlchemy declarative base and common utilities."""

from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass
