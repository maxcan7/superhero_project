from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy import SmallInteger
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


class UserRole(StrEnum):
    contributor = "contributor"
    moderator = "moderator"
    admin = "admin"


class ArticleType(StrEnum):
    profile = "profile"
    event = "event"
    org = "org"
    location = "location"
    tech = "tech"
    lore = "lore"


class ArticleStatus(StrEnum):
    draft = "draft"
    pending = "pending"
    published = "published"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    github_username: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), default=UserRole.contributor, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    articles: Mapped[list["Article"]] = relationship(back_populates="author")
    comments: Mapped[list["Comment"]] = relationship(back_populates="author")
    votes: Mapped[list["Vote"]] = relationship(back_populates="user")
    edits: Mapped[list["ArticleHistory"]] = relationship(back_populates="editor")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    article_type: Mapped[ArticleType] = mapped_column(
        SAEnum(ArticleType, name="article_type"), nullable=False
    )
    designation: Mapped[str | None] = mapped_column(String(20))
    schema_version: Mapped[int] = mapped_column(nullable=False, default=1)
    # "metadata" shadows DeclarativeBase.metadata, so we use metadata_ in Python
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, name="article_status"),
        default=ArticleStatus.draft,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column()

    author: Mapped["User"] = relationship(back_populates="articles")
    tags: Mapped[list["ArticleTag"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    votes: Mapped[list["Vote"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )
    history: Mapped[list["ArticleHistory"]] = relationship(
        back_populates="article", cascade="all, delete-orphan"
    )


class ArticleTag(Base):
    __tablename__ = "article_tags"

    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    tag: Mapped[str] = mapped_column(String(100), primary_key=True)

    article: Mapped["Article"] = relationship(back_populates="tags")


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("article_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    value: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    article: Mapped["Article"] = relationship(back_populates="votes")
    user: Mapped["User"] = relationship(back_populates="votes")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    article: Mapped["Article"] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship(back_populates="comments")


class ArticleHistory(Base):
    __tablename__ = "article_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("articles.id"), nullable=False)
    editor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    metadata_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )

    article: Mapped["Article"] = relationship(back_populates="history")
    editor: Mapped["User"] = relationship(back_populates="edits")
