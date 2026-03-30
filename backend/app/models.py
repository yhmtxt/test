import uuid
from enum import StrEnum

from sqlmodel import SQLModel, Field, Relationship


class Role(StrEnum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class UserBase(SQLModel):
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)
    name: str = Field(nullable=False, min_length=1, max_length=255)
    role: Role = Field(nullable=False)

    classroom_id: uuid.UUID = Field(
        foreign_key="classroom.id", nullable=True, ondelete="CASCADE"
    )
    group_id: uuid.UUID | None = Field(
        foreign_key="group.id", nullable=True, default=None
    )


class User(UserBase, table=True):
    hashed_password: str = Field(nullable=False)

    classroom: "Classroom" = Relationship(back_populates="users")
    group: "Group | None" = Relationship(back_populates="users")


class UserPublic(UserBase): ...


class ClassroomBase(SQLModel):
    name: str = Field(nullable=False, min_length=1, max_length=255)


class Classroom(ClassroomBase, table=True):
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)

    users: list[User] = Relationship(back_populates="classroom", cascade_delete=True)


class ClassroomCreate(ClassroomBase):
    student_names: list[str]


class Group(SQLModel, table=True):
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)
    name: str = Field(nullable=False, min_length=1, max_length=255)
    code: str = Field(nullable=True, default="")

    users: list[User] = Relationship(back_populates="group")
