import uuid
from typing import Optional
from pydantic.alias_generators import to_snake
from sqlalchemy.orm import declared_attr
from sqlmodel import SQLModel, Field, Relationship, CheckConstraint


@declared_attr.directive
def __tablename__(cls) -> str:
    return to_snake(cls.__name__)


SQLModel.__tablename__ = __tablename__


class Group(SQLModel, table=True):
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)
    name: str = Field(nullable=False, min_length=1, max_length=255)
    code: str = Field(nullable=True, default="")
    leader_id: uuid.UUID | None = Field(
        foreign_key="student_info.id", nullable=True, default=None, unique=True
    )
    leader: Optional["StudentInfo"] = Relationship(back_populates="leaded_group", sa_relationship_kwargs={"foreign_keys": "Group.leader_id"})

    students: list["StudentInfo"] = Relationship(back_populates="group", sa_relationship_kwargs={"foreign_keys": "StudentInfo.group_id"})


class UserBase(SQLModel):
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)
    name: str = Field(nullable=False, min_length=1, max_length=255)


class User(UserBase, table=True):
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)
    name: str = Field(nullable=False, min_length=1, max_length=255)
    hashed_password: str = Field(nullable=False)

    student_info_id: uuid.UUID | None = Field(
        foreign_key="student_info.id",
        unique=True,
        nullable=True,
        ondelete="CASCADE",
        default=None,
    )
    teacher_info_id: uuid.UUID | None = Field(
        foreign_key="teacher_info.id",
        unique=True,
        nullable=True,
        ondelete="CASCADE",
        default=None,
    )
    admin_info_id: uuid.UUID | None = Field(
        foreign_key="admin_info.id",
        unique=True,
        nullable=True,
        ondelete="CASCADE",
        default=None,
    )

    student_info: Optional["StudentInfo"] = Relationship(back_populates="user")
    teacher_info: Optional["TeacherInfo"] = Relationship(back_populates="user")
    admin_info: Optional["AdminInfo"] = Relationship(back_populates="user")

    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(student_info_id, teacher_info_id, admin_info_id) = 1",
            name="one_extra_info",
        ),
    )


class StudentInfo(SQLModel, table=True):
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)

    group_id: uuid.UUID | None = Field(
        foreign_key="group.id", nullable=True, default=None
    )
    group: Group | None = Relationship(back_populates="students", sa_relationship_kwargs={"foreign_keys": "StudentInfo.group_id"})
    leaded_group: Group | None = Relationship(back_populates="leader", sa_relationship_kwargs={"foreign_keys": "Group.leader_id"})

    user: User = Relationship(back_populates="student_info", cascade_delete=True)


class TeacherInfo(SQLModel, table=True): 
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)

    user: User = Relationship(back_populates="teacher_info", cascade_delete=True)


class AdminInfo(SQLModel, table=True):
    id: uuid.UUID = Field(primary_key=True, default_factory=uuid.uuid4)

    user: User = Relationship(back_populates="admin_info", cascade_delete=True)


class UserPublic(UserBase): ...
