from typing import Any

from pydantic import BaseModel


class Parameter(BaseModel):
    name: str
    type: str
    is_required: bool


class API(BaseModel):
    type: str
    name: str
    description: str | None = None
    parameters: list[Parameter] | None = None
    return_type: str | None = None


class InitResponse(BaseModel):
    robot_id: str
    robot_name: str
    apis: list[API]


class CommandRequest(BaseModel):
    id: str
    name: str
    parameter: list[Any]


class CommandResponse(BaseModel):
    id: str
    success: bool
    return_data: Any
