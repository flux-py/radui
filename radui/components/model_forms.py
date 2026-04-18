from __future__ import annotations

import re
from enum import Enum
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from radui.components.nodes import (
    Button,
    Checkbox,
    Component,
    Form,
    Input,
    Select,
    Textarea,
    button,
    checkbox,
    form,
    input as text_input,
    select,
    textarea,
)
from radui.state import state


def form_from_model(
    model_cls: type[BaseModel],
    command: str,
    *,
    submit_label: str = "Submit",
    exclude: set[str] | list[str] | None = None,
    field_labels: dict[str, str] | None = None,
    field_types: dict[str, str] | None = None,
    defaults: dict[str, Any] | None = None,
    optimistic: bool = False,
    id: str | None = None,
    **kwargs: Any,
) -> Form:
    """Generate a fully-typed RADUI Form from a Pydantic model class."""
    if not isinstance(model_cls, type) or not issubclass(model_cls, BaseModel):
        raise TypeError("model_cls must be a subclass of pydantic.BaseModel")

    excluded = set(exclude or ())
    labels = field_labels or {}
    types_override = field_types or {}
    default_vals = defaults or {}

    elements: list[Component] = []

    fields = getattr(model_cls, "model_fields", None)
    if fields is None:
        fields = getattr(model_cls, "__fields__", {})

    form_id = id or f"form_{re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', model_cls.__name__).lower()}"

    for name, field_info in fields.items():
        if name in excluded:
            continue

        label = labels.get(name, name.replace("_", " ").title())
        annotation = getattr(field_info, "annotation", None) or getattr(field_info, "type_", str)

        # Handle Optional / Union types
        origin = get_origin(annotation)
        if origin is not None:
            args = get_args(annotation)
            non_none = [a for a in args if a is not type(None)]
            if non_none:
                annotation = non_none[0]

        override = types_override.get(name)

        # Determine default value
        if name in default_vals:
            default_val = default_vals[name]
        else:
            pydantic_default = getattr(field_info, "default", None)
            if pydantic_default is not None and pydantic_default is not ...:
                default_val = pydantic_default
            elif annotation is bool:
                default_val = False
            elif annotation in (int, float):
                default_val = 0
            else:
                default_val = ""

        # Create StateRef bound to this field
        field_ref = state(name, default_val, scope="session")

        if override == "textarea" or (annotation is str and ("description" in name.lower() or "bio" in name.lower() or "notes" in name.lower())):
            elements.append(
                textarea(
                    label,
                    bind=field_ref,
                    placeholder=f"Enter {label.lower()}...",
                    id=f"field_{name}",
                )
            )
        elif annotation is bool:
            elements.append(
                checkbox(
                    label,
                    bind=field_ref,
                    id=f"field_{name}",
                )
            )
        elif isinstance(annotation, type) and issubclass(annotation, Enum):
            options = [(e.name, str(e.value)) for e in annotation]
            elements.append(
                select(
                    label,
                    bind=field_ref,
                    options=options,
                    id=f"field_{name}",
                )
            )
        elif annotation in (int, float):
            elements.append(
                text_input(
                    label,
                    bind=field_ref,
                    input_type="number",
                    placeholder=f"Enter {label.lower()}...",
                    id=f"field_{name}",
                )
            )
        elif "password" in name.lower():
            elements.append(
                text_input(
                    label,
                    bind=field_ref,
                    input_type="password",
                    placeholder=f"Enter {label.lower()}...",
                    id=f"field_{name}",
                )
            )
        else:
            elements.append(
                text_input(
                    label,
                    bind=field_ref,
                    input_type="text",
                    placeholder=f"Enter {label.lower()}...",
                    id=f"field_{name}",
                )
            )

    elements.append(button(submit_label, variant="primary", id=f"{command}-submit"))
    return form(command, *elements, id=form_id, optimistic=optimistic, **kwargs)
