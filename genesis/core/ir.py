from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from radui.components.nodes import Element


class AppMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=160)


class RouteSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=2048)
    title: str = Field(min_length=1, max_length=160)
    root: Element


class CommandSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)


class JobSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=128)


class ApplicationIR(BaseModel):
    """Versioned, serializable representation of an application's UI and work contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: Literal["radui.application"] = "radui.application"
    version: str = "0.4"
    app: AppMetadata
    routes: tuple[RouteSpec, ...]
    commands: tuple[CommandSpec, ...] = ()
    jobs: tuple[JobSpec, ...] = ()
