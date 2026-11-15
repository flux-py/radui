from __future__ import annotations

import re
from typing import Annotated, Any, Literal, TypeAlias
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, field_validator, model_validator
from radui.state.refs import StateRef


_COMMAND_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class Component(BaseModel):
    """Base type for immutable, serializable RADUI UI nodes."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    kind: str
    id: str | None = Field(default=None, min_length=1, max_length=128)
    motion: Any = Field(default=None)
    hover: Any = Field(default=None)
    tap: Any = Field(default=None)
    motion_id: str | None = Field(default=None)

    @field_validator("id")
    @classmethod
    def validate_component_id(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}", value):
            raise ValueError("component id must start with a letter and contain only letters, numbers, '.', '_', ':' or '-'")
        return value


class Text(Component):
    kind: Literal["text"] = "text"
    value: str | None = None
    binding_key: str | None = None
    binding_scope: str | None = None
    display_format: str = "{value}"
    state_ref: Any = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_content_source(self) -> "Text":
        if self.state_ref is not None and not isinstance(self.state_ref, StateRef):
            raise ValueError("state_ref must be a RADUI StateRef")
        if (self.value is None) == (self.state_ref is None):
            raise ValueError("Text requires exactly one of value or state binding")
        if self.state_ref is not None and (
            self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope
        ):
            raise ValueError("Text binding metadata does not match its StateRef")
        return self


class Heading(Component):
    kind: Literal["heading"] = "heading"
    value: str
    level: Literal[1, 2, 3, 4, 5, 6] = 1


class Link(Component):
    kind: Literal["link"] = "link"
    label: str
    href: str

    @field_validator("href")
    @classmethod
    def validate_href(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("href cannot be empty")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("control characters are not allowed in URLs")
        parsed = urlsplit(value)
        if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError("only http and https URL schemes are allowed")
        if value.startswith("//"):
            raise ValueError("protocol-relative URLs are not allowed")
        if parsed.scheme and not parsed.hostname:
            raise ValueError("absolute http(s) URLs must include a hostname")
        return value


class Divider(Component):
    kind: Literal["divider"] = "divider"


class Spacer(Component):
    kind: Literal["spacer"] = "spacer"
    size: int = Field(default=16, ge=0, le=128)


class Badge(Component):
    kind: Literal["badge"] = "badge"
    label: str
    variant: Literal["neutral", "primary", "success", "warning", "danger", "info"] = "neutral"


class Callout(Component):
    kind: Literal["callout"] = "callout"
    title: str = ""
    message: str = ""
    variant: Literal["info", "success", "warning", "danger"] = "info"
    binding_key: str | None = None
    binding_scope: str | None = None


class Column(Component):
    kind: Literal["column"] = "column"
    children: tuple[Element, ...] = ()
    gap: int = Field(default=16, ge=0, le=64)
    stagger_children: float = Field(default=0.0, ge=0.0)


class Row(Component):
    kind: Literal["row"] = "row"
    children: tuple[Element, ...] = ()
    gap: int = Field(default=12, ge=0, le=64)
    justify: str | None = None
    align: str | None = None
    wrap: bool = False


class Card(Component):
    kind: Literal["card"] = "card"
    children: tuple[Element, ...] = ()
    flippable: bool = False
    code: str | None = None


class Grid(Component):
    kind: Literal["grid"] = "grid"
    children: tuple[Element, ...] = ()
    columns: int | dict[str, int] = Field(default=2)
    gap: int = Field(default=16, ge=0, le=64)
    stagger_children: float = Field(default=0.0, ge=0.0)


class TabItem(Component):
    kind: Literal["tab_item"] = "tab_item"
    label: str
    children: tuple[Element, ...] = ()


class Tabs(Component):
    kind: Literal["tabs"] = "tabs"
    children: tuple[TabItem, ...] = ()
    active_index: int = Field(default=0, ge=0)


class Modal(Component):
    kind: Literal["modal"] = "modal"
    title: str
    trigger_label: str = "Open"
    children: tuple[Element, ...] = ()


class Input(Component):
    kind: Literal["input"] = "input"
    label: str
    name: str
    input_type: Literal["text", "email", "number", "search", "password"] = "text"
    placeholder: str = ""
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "Input":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("input state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("input name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("input binding metadata does not match its StateRef")
        if self.state_ref.scope not in {"view", "session", "user"}:
            raise ValueError("app-scoped state must not be used as an editable form field")
        if self.input_type == "number" and self.state_ref.type_key not in {"<class 'int'>", "<class 'float'>"}:
            raise ValueError("number inputs require an int or float StateRef")
        if self.input_type != "number" and self.state_ref.type_key != "<class 'str'>":
            raise ValueError("textual inputs require a str StateRef")
        return self


class Textarea(Component):
    kind: Literal["textarea"] = "textarea"
    label: str
    name: str
    rows: int = Field(default=4, ge=1, le=50)
    placeholder: str = ""
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "Textarea":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("textarea state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("textarea name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("textarea binding metadata does not match its StateRef")
        if self.state_ref.scope not in {"view", "session", "user"}:
            raise ValueError("app-scoped state must not be used as an editable form field")
        if self.state_ref.type_key != "<class 'str'>":
            raise ValueError("textarea requires a str StateRef")
        return self


class Select(Component):
    kind: Literal["select"] = "select"
    label: str
    name: str
    options: tuple[tuple[str, str], ...] = ()
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "Select":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("select state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("select name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("select binding metadata does not match its StateRef")
        if self.state_ref.scope not in {"view", "session", "user"}:
            raise ValueError("app-scoped state must not be used as an editable form field")
        return self


class Switch(Component):
    kind: Literal["switch"] = "switch"
    label: str
    name: str
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "Switch":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("switch state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("switch name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("switch binding metadata does not match its StateRef")
        if self.state_ref.scope == "app":
            raise ValueError("app-scoped state must not be used as an editable form field")
        if self.state_ref.type_key not in {"<class 'bool'>", "bool"}:
            raise ValueError("Switch requires a bool StateRef")
        return self


class RadioGroup(Component):
    kind: Literal["radio_group"] = "radio_group"
    label: str
    name: str
    options: tuple[tuple[str, str], ...] = ()
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "RadioGroup":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("radio_group state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("radio_group name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("radio_group binding metadata does not match its StateRef")
        if self.state_ref.scope == "app":
            raise ValueError("app-scoped state must not be used as an editable form field")
        return self


class Checkbox(Component):
    kind: Literal["checkbox"] = "checkbox"
    label: str
    name: str
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "Checkbox":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("checkbox state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("checkbox name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("checkbox binding metadata does not match its StateRef")
        if self.state_ref.scope == "app":
            raise ValueError("app-scoped state must not be used as an editable form field")
        if self.state_ref.type_key not in {"<class 'bool'>", "bool"}:
            raise ValueError("Checkbox requires a bool StateRef")
        return self


class Button(Component):
    kind: Literal["button"] = "button"
    label: str
    variant: Literal["primary", "secondary", "danger", "outline", "subtle"] = "primary"
    command: str = ""
    disabled: bool = False
    size: Literal["sm", "md", "lg"] = "md"
    optimistic: bool = False


class Form(Component):
    kind: Literal["form"] = "form"
    command: str
    children: tuple[Element, ...] = ()
    optimistic: bool = False

    @field_validator("command")
    @classmethod
    def validate_command(cls, value: str) -> str:
        if not _COMMAND_RE.fullmatch(value):
            raise ValueError("invalid command identifier")
        return value


class JobPanel(Component):
    kind: Literal["job_panel"] = "job_panel"
    job_name: str
    label: str = "Background task"
    # Runtime handle is intentionally excluded from the serialized application IR.
    job_handle: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_job_handle(self) -> "JobPanel":
        if getattr(self.job_handle, "name", None) != self.job_name:
            raise ValueError("JobPanel handle does not match job_name")
        if not callable(getattr(self.job_handle, "latest_snapshot", None)):
            raise ValueError("JobPanel requires a registered RADUI job")
        return self


class MetricCard(Component):
    kind: Literal["metric_card"] = "metric_card"
    title: str
    value: str
    change: str = ""
    trend: Literal["up", "down", "neutral"] = "neutral"
    subtitle: str = ""
    animate_number: bool | Any = False


class Table(Component):
    kind: Literal["table"] = "table"
    columns: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    caption: str = ""
    striped: bool = True


class Plot(Component):
    kind: Literal["plot"] = "plot"
    chart_type: Literal["bar", "line", "donut", "scatter"] = "bar"
    title: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    height: int = Field(default=240, ge=80, le=1200)


class ChatMessage(Component):
    kind: Literal["chat_message"] = "chat_message"
    role: Literal["user", "assistant", "system", "tool"] = "user"
    content: str
    timestamp: str = ""
    citations: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()


class ChatView(Component):
    kind: Literal["chat_view"] = "chat_view"
    title: str = "AI Assistant"
    children: tuple[ChatMessage, ...] = ()


class ChatInput(Component):
    kind: Literal["chat_input"] = "chat_input"
    placeholder: str = "Ask a question..."
    command: str = "chat.send"
    label: str = "Send"


class StreamingText(Component):
    kind: Literal["streaming_text"] = "streaming_text"
    value: str | None = None
    binding_key: str | None = None
    binding_scope: str | None = None
    cursor: bool = True
    state_ref: Any = Field(default=None, exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_content_source(self) -> "StreamingText":
        if self.state_ref is not None and not isinstance(self.state_ref, StateRef):
            raise ValueError("state_ref must be a RADUI StateRef")
        if (self.value is None) == (self.state_ref is None):
            raise ValueError("StreamingText requires exactly one of value or state binding")
        return self


class ActionCard(Component):
    kind: Literal["action_card"] = "action_card"
    title: str
    description: str = ""
    approve_command: str
    reject_command: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "approved", "rejected"] = "pending"
    optimistic: bool = False


class StepTimeline(Component):
    kind: Literal["step_timeline"] = "step_timeline"
    title: str = "Execution Steps"
    steps: tuple[tuple[str, str, str], ...] = ()  # (title, status, detail)


class DynamicCard(Component):
    kind: Literal["dynamic_card"] = "dynamic_card"
    title: str = ""
    spec: dict[str, Any] = Field(default_factory=dict)


class DiagramNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    label: str
    x: float = 0.0
    y: float = 0.0
    width: float = 160.0
    height: float = 60.0
    kind: Literal["default", "rounded", "pill", "database", "diamond", "step", "cloud"] = "default"
    status: Literal["normal", "active", "success", "warning", "danger", "muted"] = "normal"
    icon: str = ""
    description: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class DiagramEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    source: str
    target: str
    label: str = ""
    style: Literal["solid", "dashed", "dotted"] = "solid"
    directional: bool = True
    animated: bool = False
    color: str = ""


class Diagram(Component):
    kind: Literal["diagram"] = "diagram"
    nodes: tuple[DiagramNode, ...] = ()
    edges: tuple[DiagramEdge, ...] = ()
    height: int = 440
    width: str | int = "100%"
    on_node_click: str = ""
    selected_id: str = ""
    layout: Literal["manual", "vertical", "horizontal"] = "manual"


class CodeBlock(Component):
    kind: Literal["code_block"] = "code_block"
    code: str
    language: str = "python"
    show_line_numbers: bool = True
    copyable: bool = True
    title: str = ""


class TreeNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    label: str
    icon: str = ""
    expanded: bool = False
    selected: bool = False
    children: tuple[TreeNode, ...] = ()
    data: dict[str, Any] = Field(default_factory=dict)


class TreeView(Component):
    kind: Literal["tree_view"] = "tree_view"
    root_nodes: tuple[TreeNode, ...] = ()
    on_select_command: str = ""


class DataGrid(Component):
    kind: Literal["data_grid"] = "data_grid"
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[Any, ...], ...] = ()
    searchable: bool = True
    sortable: bool = True
    page_size: int = 10
    empty_message: str = "No data available"


class GenerativeSlot(Component):
    kind: Literal["generative_slot"] = "generative_slot"
    name: str
    children: tuple[Element, ...] = ()
    fallback: str = ""
    streaming: bool = False
    scope: str = "slot"


class Skeleton(Component):
    kind: Literal["skeleton"] = "skeleton"
    shape: Literal["text", "rect", "circle"] = "rect"
    width: str = "100%"
    height: str = "24px"
    animated: bool = True


class EmptyState(Component):
    kind: Literal["empty_state"] = "empty_state"
    title: str = "No data"
    description: str = ""
    icon: str = ""


class FileUpload(Component):
    kind: Literal["file_upload"] = "file_upload"
    command: str = "file.upload"
    accept: str = "*/*"
    max_size_mb: int = 10
    multiple: bool = False
    label: str = "Drag & drop files here, or browse"


class VirtualList(Component):
    kind: Literal["virtual_list"] = "virtual_list"
    items: tuple[str, ...] = ()
    item_height: int = 40
    viewport_height: int = 320


class ThemeToggle(Component):
    kind: Literal["theme_toggle"] = "theme_toggle"
    label: str = "Toggle Theme"


class ErrorBoundary(Component):
    kind: Literal["error_boundary"] = "error_boundary"
    fallback_message: str = "This component encountered an error and could not be displayed."
    children: tuple[Any, ...] = ()


class Toast(Component):
    kind: Literal["toast"] = "toast"
    message: str
    title: str = ""
    variant: Literal["info", "success", "warning", "danger"] = "info"
    duration_ms: int = Field(default=4000, ge=500, le=30000)
    dismissible: bool = True


class ToastContainer(Component):
    kind: Literal["toast_container"] = "toast_container"
    position: Literal["top-right", "top-left", "bottom-right", "bottom-left", "top-center", "bottom-center"] = "top-right"
    children: tuple[Toast, ...] = ()


class Tooltip(Component):
    kind: Literal["tooltip"] = "tooltip"
    content: str
    position: Literal["top", "bottom", "left", "right"] = "top"
    children: tuple[Element, ...] = ()


class Popover(Component):
    kind: Literal["popover"] = "popover"
    trigger_label: str = "Open"
    title: str = ""
    placement: Literal["top", "bottom", "left", "right"] = "bottom"
    children: tuple[Element, ...] = ()


class AccordionItem(Component):
    kind: Literal["accordion_item"] = "accordion_item"
    title: str
    open: bool = False
    children: tuple[Element, ...] = ()


class Accordion(Component):
    kind: Literal["accordion"] = "accordion"
    children: tuple[AccordionItem, ...] = ()
    allow_multiple: bool = False


class Drawer(Component):
    kind: Literal["drawer"] = "drawer"
    title: str
    trigger_label: str = "Open Drawer"
    placement: Literal["left", "right", "top", "bottom"] = "right"
    children: tuple[Element, ...] = ()


class BreadcrumbItem(Component):
    kind: Literal["breadcrumb_item"] = "breadcrumb_item"
    label: str
    href: str | None = None
    active: bool = False


class Breadcrumb(Component):
    kind: Literal["breadcrumb"] = "breadcrumb"
    items: tuple[BreadcrumbItem, ...] = ()
    separator: str = "/"


class Pagination(Component):
    kind: Literal["pagination"] = "pagination"
    current_page: int = Field(default=1, ge=1)
    total_pages: int = Field(default=1, ge=1)
    command: str = "page.change"


class ProgressBar(Component):
    kind: Literal["progress_bar"] = "progress_bar"
    value: float = Field(default=0.0, ge=0.0)
    max_value: float = Field(default=100.0, gt=0.0)
    variant: Literal["primary", "success", "warning", "danger", "info"] = "primary"
    striped: bool = False
    animated: bool = False
    label: str | None = None


class ProgressCircle(Component):
    kind: Literal["progress_circle"] = "progress_circle"
    value: float = Field(default=0.0, ge=0.0, le=100.0)
    size: int = Field(default=64, ge=24, le=256)
    stroke_width: int = Field(default=6, ge=2, le=32)
    variant: Literal["primary", "success", "warning", "danger", "info"] = "primary"
    label: str | None = None


class Avatar(Component):
    kind: Literal["avatar"] = "avatar"
    name: str = ""
    src: str | None = None
    size: Literal["sm", "md", "lg", "xl"] = "md"
    status: Literal["online", "offline", "busy", "away"] | None = None


class AvatarGroup(Component):
    kind: Literal["avatar_group"] = "avatar_group"
    children: tuple[Avatar, ...] = ()
    max_visible: int = Field(default=4, ge=1)


class DatePicker(Component):
    kind: Literal["date_picker"] = "date_picker"
    label: str
    name: str
    min_date: str | None = None
    max_date: str | None = None
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "DatePicker":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("date_picker state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("date_picker name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("date_picker binding metadata does not match its StateRef")
        if self.state_ref.scope not in {"view", "session", "user"}:
            raise ValueError("app-scoped state must not be used as an editable form field")
        return self


class TimePicker(Component):
    kind: Literal["time_picker"] = "time_picker"
    label: str
    name: str
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "TimePicker":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("time_picker state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("time_picker name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("time_picker binding metadata does not match its StateRef")
        if self.state_ref.scope not in {"view", "session", "user"}:
            raise ValueError("app-scoped state must not be used as an editable form field")
        return self


class Slider(Component):
    kind: Literal["slider"] = "slider"
    label: str
    name: str
    min_value: float = 0.0
    max_value: float = 100.0
    step: float = 1.0
    binding_key: str
    binding_scope: str
    state_ref: Any = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_binding(self) -> "Slider":
        if not isinstance(self.state_ref, StateRef):
            raise ValueError("slider state_ref must be a RADUI StateRef")
        if self.name != self.binding_key:
            raise ValueError("slider name must match its bound state key")
        if self.binding_key != self.state_ref.key or self.binding_scope != self.state_ref.scope:
            raise ValueError("slider binding metadata does not match its StateRef")
        if self.state_ref.scope not in {"view", "session", "user"}:
            raise ValueError("app-scoped state must not be used as an editable form field")
        return self


class SplitPanel(Component):
    kind: Literal["split_panel"] = "split_panel"
    direction: Literal["horizontal", "vertical"] = "horizontal"
    initial_ratio: float = Field(default=0.5, ge=0.1, le=0.9)
    first: Element
    second: Element


class DropdownMenuItem(Component):
    kind: Literal["dropdown_menu_item"] = "dropdown_menu_item"
    label: str
    command: str | None = None
    href: str | None = None
    icon: str | None = None
    danger: bool = False


class DropdownMenu(Component):
    kind: Literal["dropdown_menu"] = "dropdown_menu"
    trigger_label: str = "Actions"
    items: tuple[DropdownMenuItem, ...] = ()


class Kbd(Component):
    kind: Literal["kbd"] = "kbd"
    keys: tuple[str, ...] = ()


class Container(Component):
    kind: Literal["container"] = "container"
    children: tuple[Element, ...] = ()
    max_width: str = "1200px"
    centered: bool = True


class Stack(Component):
    kind: Literal["stack"] = "stack"
    children: tuple[Element, ...] = ()
    direction: Literal["vertical", "horizontal"] = "vertical"
    gap: int = Field(default=16, ge=0, le=64)
    align: Literal["start", "center", "end", "stretch"] = "stretch"


class Tag(Component):
    kind: Literal["tag"] = "tag"
    label: str
    variant: Literal["neutral", "primary", "success", "warning", "danger", "info"] = "neutral"
    removable: bool = False
    remove_command: str | None = None


Element: TypeAlias = SerializeAsAny[Component]

for model in (
    Column,
    Row,
    Card,
    Grid,
    TabItem,
    Tabs,
    Modal,
    Form,
    ChatView,
    GenerativeSlot,
    ErrorBoundary,
    Tooltip,
    Popover,
    AccordionItem,
    Accordion,
    Drawer,
    SplitPanel,
    Container,
    Stack,
):
    model.model_rebuild()

ToastContainer.model_rebuild()
Breadcrumb.model_rebuild()
AvatarGroup.model_rebuild()
DropdownMenu.model_rebuild()
TreeNode.model_rebuild()


def _binding_parts(ref: Any) -> tuple[str, str]:
    if not isinstance(ref, StateRef):
        raise TypeError("bind must be a RADUI StateRef")
    return str(ref.key), str(ref.scope)


def _generated_id(prefix: str, key: str) -> str:
    return f"{prefix}-{key}"


# --- Public Factory Functions ---


def text(
    value: str | Any = None,
    *,
    bind: Any | None = None,
    id: str | None = None,
    format: str = "{value}",
    variant: str = "default",
    **kwargs: Any,
) -> Text:
    if bind is not None:
        if value is not None:
            raise TypeError("provide either a text value or bind=, not both")
        value = bind
    if isinstance(value, str):
        return Text(value=value, id=id)
    if value is None:
        raise TypeError("text requires a string value or bind=StateRef")
    key, scope = _binding_parts(value)
    return Text(
        value=None,
        binding_key=key,
        binding_scope=scope,
        display_format=format,
        state_ref=value,
        id=id or _generated_id("gx-text", key),
    )


def heading(value: str, *, level: int = 1, id: str | None = None) -> Heading:
    return Heading(value=value, level=level, id=id)


def link(label: str, href: str = "", *, url: str = "", id: str | None = None, **kwargs: Any) -> Link:
    return Link(label=label, href=url or href, id=id)


def divider(*, id: str | None = None) -> Divider:
    return Divider(id=id)


def spacer(size: int = 16, *, id: str | None = None) -> Spacer:
    return Spacer(size=size, id=id)


def badge(
    label: str,
    *,
    variant: Literal["neutral", "primary", "success", "warning", "danger", "info"] = "neutral",
    id: str | None = None,
) -> Badge:
    return Badge(label=label, variant=variant, id=id)


def callout(
    message: str | Any = "",
    *,
    bind: Any | None = None,
    title: str = "",
    variant: Literal["info", "success", "warning", "danger"] = "info",
    id: str | None = None,
) -> Callout:
    ref = bind if bind is not None else (message if not isinstance(message, str) else None)
    if ref is not None:
        key, scope = _binding_parts(ref)
        initial_msg = str(getattr(ref, "value", message if isinstance(message, str) else ""))
        return Callout(
            message=initial_msg,
            title=title,
            variant=variant,
            binding_key=key,
            binding_scope=scope,
            id=id or _generated_id("gx-callout", key),
        )
    return Callout(message=str(message), title=title, variant=variant, id=id)


def column(*children: Element, gap: int = 16, id: str | None = None, **kwargs: Any) -> Column:
    return Column(
        children=tuple(children),
        gap=gap,
        id=id,
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
        stagger_children=kwargs.get("stagger_children", 0.0),
    )


def row(*children: Element, gap: int = 12, id: str | None = None, **kwargs: Any) -> Row:
    return Row(
        children=tuple(children),
        gap=gap,
        id=id,
        justify=kwargs.get("justify"),
        align=kwargs.get("align"),
        wrap=bool(kwargs.get("wrap", False)),
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
    )


def card(*children: Element, id: str | None = None, flippable: bool = False, code: str | None = None, **kwargs: Any) -> Card:
    return Card(
        children=tuple(children),
        id=id,
        flippable=flippable,
        code=code,
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
    )


def grid(*children: Element, columns: int = 2, gap: int = 16, id: str | None = None, **kwargs: Any) -> Grid:
    return Grid(
        children=tuple(children),
        columns=columns,
        gap=gap,
        id=id,
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
        stagger_children=kwargs.get("stagger_children", 0.0),
    )


def tab_item(label: str, *children: Element, id: str | None = None, tab_id: str | None = None) -> TabItem:
    return TabItem(label=label, children=tuple(children), id=tab_id or id)


def tabs(*items: Any, active_index: int = 0, id: str | None = None) -> Tabs:
    flat: list[TabItem] = []
    for it in items:
        if isinstance(it, (list, tuple)):
            for sub in it:
                if isinstance(sub, TabItem):
                    flat.append(sub)
        elif isinstance(it, TabItem):
            flat.append(it)
    return Tabs(children=tuple(flat), active_index=active_index, id=id)


def modal(title: str, *children: Element, trigger_label: str = "Open", id: str | None = None) -> Modal:
    return Modal(title=title, trigger_label=trigger_label, children=tuple(children), id=id)


def _resolve_binding(name_or_label: str, bind: Any, state_ref: Any, default_val: Any = "") -> tuple[str, str, str, Any]:
    ref = bind if bind is not None else state_ref
    if ref is not None:
        key, scope = _binding_parts(ref)
        label = name_or_label
        return label, key, scope, ref
    # Ephemeral fallback for unbound/presentation components
    from radui.state import state
    clean_key = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name_or_label.lower()).strip("_") or "field"
    ref = state(f"form.{clean_key}", default_val, scope="session")
    key, scope = _binding_parts(ref)
    return name_or_label, key, scope, ref


def input(
    name_or_label: str | None = None,
    *,
    name: str | None = None,
    label: str | None = None,
    bind: Any = None,
    state_ref: Any = None,
    input_type: Literal["text", "email", "number", "search", "password"] = "text",
    placeholder: str = "",
    id: str | None = None,
) -> Input:
    raw_name = name or (name_or_label if label else None)
    raw_label = label or (name_or_label if not name else name) or ""
    binding_source = raw_name if (bind is None and state_ref is None and raw_name) else raw_label
    disp_label, key, scope, ref = _resolve_binding(binding_source, bind, state_ref)
    final_label = raw_label if raw_label else disp_label
    return Input(
        label=final_label,
        name=key,
        input_type=input_type,
        placeholder=placeholder,
        binding_key=key,
        binding_scope=scope,
        state_ref=ref,
        id=id or _generated_id("gx-input", key),
    )


def textarea(
    name_or_label: str | None = None,
    *,
    name: str | None = None,
    label: str | None = None,
    bind: Any = None,
    state_ref: Any = None,
    rows: int = 4,
    placeholder: str = "",
    id: str | None = None,
) -> Textarea:
    raw_name = name or (name_or_label if label else None)
    raw_label = label or (name_or_label if not name else name) or ""
    binding_source = raw_name if (bind is None and state_ref is None and raw_name) else raw_label
    disp_label, key, scope, ref = _resolve_binding(binding_source, bind, state_ref)
    final_label = raw_label if raw_label else disp_label
    return Textarea(
        label=final_label,
        name=key,
        rows=rows,
        placeholder=placeholder,
        binding_key=key,
        binding_scope=scope,
        state_ref=ref,
        id=id or _generated_id("gx-textarea", key),
    )


def select(
    name_or_label: str | None = None,
    *,
    name: str | None = None,
    label: str | None = None,
    bind: Any = None,
    state_ref: Any = None,
    options: list[tuple[str, str]] | tuple[tuple[str, str], ...] | list[str] | tuple[str, ...] = (),
    id: str | None = None,
) -> Select:
    raw_name = name or (name_or_label if label else None)
    raw_label = label or (name_or_label if not name else name) or ""
    binding_source = raw_name if (bind is None and state_ref is None and raw_name) else raw_label
    disp_label, key, scope, ref = _resolve_binding(binding_source, bind, state_ref)
    final_label = raw_label if raw_label else disp_label
    normalized_options: list[tuple[str, str]] = []
    for opt in options:
        if isinstance(opt, (tuple, list)) and len(opt) == 2:
            normalized_options.append((str(opt[0]), str(opt[1])))
        else:
            normalized_options.append((str(opt), str(opt)))
    return Select(
        label=final_label,
        name=key,
        options=tuple(normalized_options),
        binding_key=key,
        binding_scope=scope,
        state_ref=ref,
        id=id or _generated_id("gx-select", key),
    )


def switch(
    name_or_label: str,
    *,
    label: str | None = None,
    bind: Any = None,
    state_ref: Any = None,
    default: bool = False,
    id: str | None = None,
) -> Switch:
    disp_label, key, scope, ref = _resolve_binding(label or name_or_label, bind, state_ref, default_val=default)
    return Switch(
        label=disp_label,
        name=key,
        binding_key=key,
        binding_scope=scope,
        state_ref=ref,
        id=id or _generated_id("gx-switch", key),
    )


def radio_group(
    name_or_label: str,
    *,
    label: str | None = None,
    bind: Any = None,
    state_ref: Any = None,
    options: list[tuple[str, str]] | tuple[tuple[str, str], ...] | list[str] | tuple[str, ...],
    default: str = "",
    id: str | None = None,
) -> RadioGroup:
    disp_label, key, scope, ref = _resolve_binding(label or name_or_label, bind, state_ref, default_val=default)
    normalized_options: list[tuple[str, str]] = []
    for opt in options:
        if isinstance(opt, (tuple, list)) and len(opt) == 2:
            normalized_options.append((str(opt[0]), str(opt[1])))
        else:
            normalized_options.append((str(opt), str(opt)))
    return RadioGroup(
        label=disp_label,
        name=key,
        options=tuple(normalized_options),
        binding_key=key,
        binding_scope=scope,
        state_ref=ref,
        id=id or _generated_id("gx-radiogroup", key),
    )


def checkbox(label: str, *, bind: Any, id: str | None = None) -> Checkbox:
    key, scope = _binding_parts(bind)
    return Checkbox(
        label=label,
        name=key,
        binding_key=key,
        binding_scope=scope,
        state_ref=bind,
        id=id or _generated_id("gx-checkbox", key),
    )


def button(
    label: str,
    *,
    variant: Literal["primary", "secondary", "danger", "outline", "subtle"] = "primary",
    command: str = "",
    disabled: bool = False,
    size: Literal["sm", "md", "lg"] = "md",
    optimistic: bool = False,
    id: str | None = None,
    **kwargs: Any,
) -> Button:
    return Button(
        label=label,
        variant=variant,
        command=command,
        disabled=disabled,
        size=size,
        optimistic=optimistic,
        id=id,
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
    )


def form(
    *children_or_command: Any,
    command: str | None = None,
    id: str | None = None,
    optimistic: bool = False,
    **kwargs: Any,
) -> Form:
    actual_children = list(children_or_command)
    cmd = command
    if actual_children and isinstance(actual_children[0], str) and not cmd:
        cmd = actual_children.pop(0)
    elif not cmd:
        cmd = kwargs.pop("command", "")
    return Form(
        command=str(cmd),
        children=tuple(actual_children),
        id=id or _generated_id("gx-form", str(cmd)),
        optimistic=optimistic,
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
    )


def job_panel(job: Any, *, label: str = "Background task", id: str | None = None) -> JobPanel:
    name = getattr(job, "name", None)
    if not isinstance(name, str) or not callable(getattr(job, "latest_snapshot", None)):
        raise TypeError("job_panel requires a registered RADUI JobDefinition")
    return JobPanel(
        job_name=name,
        label=label,
        job_handle=job,
        id=id or _generated_id("gx-job", name),
    )


def metric_card(
    title: str,
    value: Any,
    *,
    change: str = "",
    delta: str = "",
    trend: Literal["up", "down", "neutral"] = "neutral",
    delta_type: str = "",
    subtitle: str = "",
    icon: str = "",
    id: str | None = None,
    animate_number: bool | Any = False,
    **kwargs: Any,
) -> MetricCard:
    final_change = delta or change
    final_trend = trend
    if delta_type:
        if delta_type in {"positive", "up"}:
            final_trend = "up"
        elif delta_type in {"negative", "down"}:
            final_trend = "down"
        else:
            final_trend = "neutral"
    final_title = f"{icon} {title}".strip() if icon else title

    resolved_val: str
    if hasattr(value, "value"):
        resolved_val = str(value.value)
    elif hasattr(value, "default"):
        resolved_val = str(value.default)
    elif callable(value):
        try:
            resolved_val = str(value())
        except Exception:
            resolved_val = str(value)
    else:
        resolved_val = str(value)

    return MetricCard(
        title=final_title,
        value=resolved_val,
        change=final_change,
        trend=final_trend,
        subtitle=subtitle,
        id=id or _generated_id("gx-metric", re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")),
        animate_number=animate_number,
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
    )


def table(
    columns: list[str] | tuple[str, ...] | None = None,
    rows: list[list[Any] | tuple[Any, ...]] | tuple[tuple[Any, ...], ...] = (),
    *,
    headers: list[str] | tuple[str, ...] | None = None,
    caption: str = "",
    striped: bool = True,
    id: str | None = None,
) -> Table:
    cols = headers if headers is not None else (columns or ())
    return Table(
        columns=tuple(cols),
        rows=tuple(tuple(r) for r in rows),
        caption=caption,
        striped=striped,
        id=id,
    )


def plot(
    chart_type: Literal["bar", "line", "donut", "scatter"] = "bar",
    *,
    type: Literal["bar", "line", "donut", "scatter"] | None = None,
    title: str = "",
    data: dict[str, Any] | list[Any],
    x_key: str = "x",
    y_key: str = "y",
    color: str = "#2563eb",
    height: int = 240,
    id: str | None = None,
) -> Plot:
    actual_type = type if type is not None else chart_type
    plot_data = data if isinstance(data, dict) else {"items": data, "x_key": x_key, "y_key": y_key, "color": color}
    return Plot(chart_type=actual_type, title=title, data=plot_data, height=height, id=id)


def chat_message(
    content: str,
    *,
    role: Literal["user", "assistant", "system", "tool"] = "user",
    timestamp: str = "",
    citations: list[str] | tuple[str, ...] = (),
    steps: list[str] | tuple[str, ...] = (),
    id: str | None = None,
) -> ChatMessage:
    return ChatMessage(
        content=content,
        role=role,
        timestamp=timestamp,
        citations=tuple(citations),
        steps=tuple(steps),
        id=id,
    )


def chat_view(
    *messages: Any,
    title: str = "AI Assistant",
    id: str | None = None,
) -> ChatView:
    flat_messages: list[ChatMessage] = []
    for m in messages:
        if isinstance(m, (list, tuple)):
            for sub_m in m:
                if isinstance(sub_m, ChatMessage):
                    flat_messages.append(sub_m)
        elif isinstance(m, ChatMessage):
            flat_messages.append(m)
    return ChatView(title=title, children=tuple(flat_messages), id=id)


def chat_input(
    name: str = "message",
    *,
    placeholder: str = "Ask a question...",
    command: str = "chat.send",
    label: str = "Send",
    submit_label: str = "",
    id: str | None = None,
) -> ChatInput:
    final_label = submit_label or label
    return ChatInput(placeholder=placeholder, command=command, label=final_label, id=id)


def streaming_text(
    value: str | Any = None,
    *,
    bind: Any | None = None,
    cursor: bool = True,
    is_streaming: bool | None = None,
    id: str | None = None,
) -> StreamingText:
    actual_cursor = is_streaming if is_streaming is not None else cursor
    if bind is not None:
        if value is not None:
            raise TypeError("provide either a text value or bind=, not both")
        value = bind
    if isinstance(value, str):
        return StreamingText(value=value, cursor=actual_cursor, id=id)
    if value is None:
        raise TypeError("streaming_text requires a string value or bind=StateRef")
    key, scope = _binding_parts(value)
    return StreamingText(
        value=None,
        binding_key=key,
        binding_scope=scope,
        cursor=actual_cursor,
        state_ref=value,
        id=id or _generated_id("gx-stream", key),
    )


def action_card(
    title: str,
    *,
    description: str = "",
    approve_command: str,
    reject_command: str = "",
    confirm_label: str = "",
    cancel_label: str = "",
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    status: Literal["pending", "approved", "rejected"] = "pending",
    optimistic: bool = False,
    id: str | None = None,
    **kwargs: Any,
) -> ActionCard:
    payload = data or metadata or {}
    return ActionCard(
        title=title,
        description=description,
        approve_command=approve_command,
        reject_command=reject_command,
        data=payload,
        status=status,
        optimistic=optimistic,
        id=id,
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
    )


def step_timeline(
    steps: list[Any] | tuple[Any, ...],
    *,
    title: str = "Execution Steps",
    id: str | None = None,
) -> StepTimeline:
    normalized_steps: list[tuple[str, str, str]] = []
    for s in steps:
        if isinstance(s, dict):
            normalized_steps.append((
                str(s.get("title", "")),
                str(s.get("status", "running")),
                str(s.get("details", s.get("detail", ""))),
            ))
        elif isinstance(s, (tuple, list)) and len(s) == 3:
            normalized_steps.append((str(s[0]), str(s[1]), str(s[2])))
    return StepTimeline(title=title, steps=tuple(normalized_steps), id=id)


def dynamic_card(
    spec_or_title: Any,
    block_type: str = "",
    *,
    payload: dict[str, Any] | None = None,
    title: str = "",
    id: str | None = None,
) -> DynamicCard:
    if isinstance(spec_or_title, dict):
        return DynamicCard(title=title, spec=spec_or_title, id=id)
    spec = payload or {"block_type": block_type, "title": str(spec_or_title)}
    return DynamicCard(title=str(spec_or_title), spec=spec, id=id)


def diagram_node(
    id: str,
    label: str,
    *,
    x: float = 0.0,
    y: float = 0.0,
    width: float = 160.0,
    height: float = 60.0,
    kind: Literal["default", "rounded", "pill", "database", "diamond", "step", "cloud"] = "default",
    status: Literal["normal", "active", "success", "warning", "danger", "muted"] = "normal",
    icon: str = "",
    description: str = "",
    data: dict[str, Any] | None = None,
) -> DiagramNode:
    return DiagramNode(
        id=id,
        label=label,
        x=x,
        y=y,
        width=width,
        height=height,
        kind=kind,
        status=status,
        icon=icon,
        description=description,
        data=data or {},
    )


def diagram_edge(
    source: str,
    target: str,
    *,
    label: str = "",
    style: Literal["solid", "dashed", "dotted"] = "solid",
    directional: bool = True,
    animated: bool = False,
    color: str = "",
) -> DiagramEdge:
    return DiagramEdge(
        source=source,
        target=target,
        label=label,
        style=style,
        directional=directional,
        animated=animated,
        color=color,
    )


def diagram(
    nodes: list[DiagramNode] | tuple[DiagramNode, ...],
    edges: list[DiagramEdge] | tuple[DiagramEdge, ...] = (),
    *,
    height: int = 440,
    width: str | int = "100%",
    on_node_click: str = "",
    selected_id: str = "",
    layout: Literal["manual", "vertical", "horizontal"] = "manual",
    id: str | None = None,
    **kwargs: Any,
) -> Diagram:
    return Diagram(
        nodes=tuple(nodes),
        edges=tuple(edges),
        height=height,
        width=width,
        on_node_click=on_node_click,
        selected_id=selected_id,
        layout=layout,
        id=id,
    )


def code_block(
    code: str,
    language: str = "python",
    *,
    show_line_numbers: bool = True,
    copyable: bool = True,
    title: str = "",
    id: str | None = None,
    **kwargs: Any,
) -> CodeBlock:
    return CodeBlock(
        code=code,
        language=language,
        show_line_numbers=show_line_numbers,
        copyable=copyable,
        title=title,
        id=id,
    )


def tree_node(
    id: str,
    label: str,
    *,
    icon: str = "",
    expanded: bool = False,
    selected: bool = False,
    children: list[TreeNode] | tuple[TreeNode, ...] = (),
    data: dict[str, Any] | None = None,
) -> TreeNode:
    return TreeNode(
        id=id,
        label=label,
        icon=icon,
        expanded=expanded,
        selected=selected,
        children=tuple(children),
        data=data or {},
    )


def tree_view(
    root_nodes: list[TreeNode] | tuple[TreeNode, ...] | None = None,
    *,
    nodes: list[TreeNode] | tuple[TreeNode, ...] | None = None,
    on_select_command: str = "",
    id: str | None = None,
    **kwargs: Any,
) -> TreeView:
    effective_nodes = root_nodes if root_nodes is not None else (nodes or ())
    return TreeView(
        root_nodes=tuple(effective_nodes),
        on_select_command=on_select_command,
        id=id,
    )


def data_grid(
    headers: list[str] | tuple[str, ...],
    rows: list[Any] | tuple[Any, ...],
    *,
    searchable: bool = True,
    sortable: bool = True,
    page_size: int = 10,
    empty_message: str = "No data available",
    id: str | None = None,
    **kwargs: Any,
) -> DataGrid:
    normalized_rows = tuple(tuple(row) if isinstance(row, (list, tuple)) else (row,) for row in rows)
    return DataGrid(
        headers=tuple(headers),
        rows=normalized_rows,
        searchable=searchable,
        sortable=sortable,
        page_size=page_size,
        empty_message=empty_message,
        id=id,
    )


def generative_slot(
    name: str,
    *children: Element,
    fallback: str = "",
    streaming: bool = False,
    scope: str = "slot",
    id: str | None = None,
    **kwargs: Any,
) -> GenerativeSlot:
    return GenerativeSlot(
        name=name,
        children=tuple(children),
        fallback=fallback,
        streaming=streaming,
        scope=scope,
        id=id,
        motion=kwargs.get("motion"),
        hover=kwargs.get("hover"),
        tap=kwargs.get("tap"),
        motion_id=kwargs.get("motion_id"),
    )


def skeleton(
    shape: Literal["text", "rect", "circle"] = "rect",
    width: str = "100%",
    height: str = "24px",
    animated: bool = True,
    id: str | None = None,
    **kwargs: Any,
) -> Skeleton:
    return Skeleton(shape=shape, width=width, height=height, animated=animated, id=id, **kwargs)


def empty_state(
    title: str = "No data",
    description: str = "",
    icon: str = "",
    id: str | None = None,
    **kwargs: Any,
) -> EmptyState:
    return EmptyState(title=title, description=description, icon=icon, id=id, **kwargs)


def file_upload(
    command: str = "file.upload",
    accept: str = "*/*",
    max_size_mb: int = 10,
    multiple: bool = False,
    label: str = "Drag & drop files here, or browse",
    id: str | None = None,
    **kwargs: Any,
) -> FileUpload:
    return FileUpload(
        command=command,
        accept=accept,
        max_size_mb=max_size_mb,
        multiple=multiple,
        label=label,
        id=id,
        **kwargs,
    )


def virtual_list(
    items: list[str] | tuple[str, ...] = (),
    item_height: int = 40,
    viewport_height: int = 320,
    id: str | None = None,
    **kwargs: Any,
) -> VirtualList:
    return VirtualList(
        items=tuple(items),
        item_height=item_height,
        viewport_height=viewport_height,
        id=id,
        **kwargs,
    )


def theme_toggle(label: str = "Toggle Theme", id: str | None = "theme-toggle", **kwargs: Any) -> ThemeToggle:
    return ThemeToggle(label=label, id=id, **kwargs)


def error_boundary(
    *children: Any,
    fallback_message: str = "This component encountered an error and could not be displayed.",
    id: str | None = None,
    **kwargs: Any,
) -> ErrorBoundary:
    return ErrorBoundary(
        children=tuple(children),
        fallback_message=fallback_message,
        id=id,
        **kwargs,
    )


def toast(
    message: str,
    title: str = "",
    variant: Literal["info", "success", "warning", "danger"] = "info",
    duration_ms: int = 4000,
    dismissible: bool = True,
    id: str | None = None,
    **kwargs: Any,
) -> Toast:
    return Toast(
        message=message,
        title=title,
        variant=variant,
        duration_ms=duration_ms,
        dismissible=dismissible,
        id=id,
        **kwargs,
    )


def toast_container(
    *toasts: Toast,
    position: Literal["top-right", "top-left", "bottom-right", "bottom-left", "top-center", "bottom-center"] = "top-right",
    id: str | None = "toast-container",
    **kwargs: Any,
) -> ToastContainer:
    return ToastContainer(position=position, children=toasts, id=id, **kwargs)


def tooltip(
    content: str,
    *children: Element,
    position: Literal["top", "bottom", "left", "right"] = "top",
    id: str | None = None,
    **kwargs: Any,
) -> Tooltip:
    return Tooltip(content=content, children=children, position=position, id=id, **kwargs)


def popover(
    title: str,
    *children: Element,
    trigger_label: str = "Open",
    placement: Literal["top", "bottom", "left", "right"] = "bottom",
    id: str | None = None,
    **kwargs: Any,
) -> Popover:
    return Popover(
        title=title,
        children=children,
        trigger_label=trigger_label,
        placement=placement,
        id=id,
        **kwargs,
    )


def accordion_item(
    title: str,
    *children: Element,
    open: bool = False,
    id: str | None = None,
    **kwargs: Any,
) -> AccordionItem:
    return AccordionItem(title=title, children=children, open=open, id=id, **kwargs)


def accordion(
    *items: AccordionItem,
    allow_multiple: bool = False,
    id: str | None = None,
    **kwargs: Any,
) -> Accordion:
    return Accordion(children=items, allow_multiple=allow_multiple, id=id, **kwargs)


def drawer(
    title: str,
    *children: Element,
    trigger_label: str = "Open Drawer",
    placement: Literal["left", "right", "top", "bottom"] = "right",
    id: str | None = None,
    **kwargs: Any,
) -> Drawer:
    return Drawer(
        title=title,
        children=children,
        trigger_label=trigger_label,
        placement=placement,
        id=id,
        **kwargs,
    )


def breadcrumb_item(
    label: str,
    href: str | None = None,
    active: bool = False,
    id: str | None = None,
    **kwargs: Any,
) -> BreadcrumbItem:
    return BreadcrumbItem(label=label, href=href, active=active, id=id, **kwargs)


def breadcrumb(
    *items: BreadcrumbItem,
    separator: str = "/",
    id: str | None = None,
    **kwargs: Any,
) -> Breadcrumb:
    return Breadcrumb(items=items, separator=separator, id=id, **kwargs)


def pagination(
    current_page: int = 1,
    total_pages: int = 1,
    command: str = "page.change",
    id: str | None = None,
    **kwargs: Any,
) -> Pagination:
    return Pagination(
        current_page=current_page,
        total_pages=total_pages,
        command=command,
        id=id,
        **kwargs,
    )


def progress_bar(
    value: float = 0.0,
    max_value: float = 100.0,
    variant: Literal["primary", "success", "warning", "danger", "info"] = "primary",
    label: str | None = None,
    striped: bool = False,
    animated: bool = False,
    id: str | None = None,
    **kwargs: Any,
) -> ProgressBar:
    return ProgressBar(
        value=value,
        max_value=max_value,
        variant=variant,
        label=label,
        striped=striped,
        animated=animated,
        id=id,
        **kwargs,
    )


def progress_circle(
    value: float = 0.0,
    size: int = 64,
    stroke_width: int = 6,
    variant: Literal["primary", "success", "warning", "danger", "info"] = "primary",
    label: str | None = None,
    id: str | None = None,
    **kwargs: Any,
) -> ProgressCircle:
    return ProgressCircle(
        value=value,
        size=size,
        stroke_width=stroke_width,
        variant=variant,
        label=label,
        id=id,
        **kwargs,
    )


def avatar(
    name: str = "",
    src: str | None = None,
    size: Literal["sm", "md", "lg", "xl"] = "md",
    status: Literal["online", "offline", "busy", "away"] | None = None,
    id: str | None = None,
    **kwargs: Any,
) -> Avatar:
    return Avatar(name=name, src=src, size=size, status=status, id=id, **kwargs)


def avatar_group(
    *avatars: Avatar,
    max_visible: int = 4,
    id: str | None = None,
    **kwargs: Any,
) -> AvatarGroup:
    return AvatarGroup(children=avatars, max_visible=max_visible, id=id, **kwargs)


def date_picker(
    label: str,
    bind: Any,
    min_date: str | None = None,
    max_date: str | None = None,
    id: str | None = None,
    **kwargs: Any,
) -> DatePicker:
    key, scope = _binding_parts(bind)
    return DatePicker(
        label=label,
        name=key,
        min_date=min_date,
        max_date=max_date,
        binding_key=key,
        binding_scope=scope,
        state_ref=bind,
        id=id or _generated_id("gx-datepicker", key),
        **kwargs,
    )


def time_picker(
    label: str,
    bind: Any,
    id: str | None = None,
    **kwargs: Any,
) -> TimePicker:
    key, scope = _binding_parts(bind)
    return TimePicker(
        label=label,
        name=key,
        binding_key=key,
        binding_scope=scope,
        state_ref=bind,
        id=id or _generated_id("gx-timepicker", key),
        **kwargs,
    )


def slider(
    label: str,
    bind: Any,
    min_value: float = 0.0,
    max_value: float = 100.0,
    step: float = 1.0,
    id: str | None = None,
    **kwargs: Any,
) -> Slider:
    key, scope = _binding_parts(bind)
    return Slider(
        label=label,
        name=key,
        min_value=min_value,
        max_value=max_value,
        step=step,
        binding_key=key,
        binding_scope=scope,
        state_ref=bind,
        id=id or _generated_id("gx-slider", key),
        **kwargs,
    )


def split_panel(
    first: Element,
    second: Element,
    direction: Literal["horizontal", "vertical"] = "horizontal",
    initial_ratio: float = 0.5,
    id: str | None = None,
    **kwargs: Any,
) -> SplitPanel:
    return SplitPanel(
        first=first,
        second=second,
        direction=direction,
        initial_ratio=initial_ratio,
        id=id,
        **kwargs,
    )


def dropdown_menu_item(
    label: str,
    command: str | None = None,
    href: str | None = None,
    icon: str | None = None,
    danger: bool = False,
    id: str | None = None,
    **kwargs: Any,
) -> DropdownMenuItem:
    return DropdownMenuItem(
        label=label,
        command=command,
        href=href,
        icon=icon,
        danger=danger,
        id=id,
        **kwargs,
    )


def dropdown_menu(
    trigger_label: str = "Actions",
    items: list[DropdownMenuItem] | tuple[DropdownMenuItem, ...] = (),
    id: str | None = None,
    **kwargs: Any,
) -> DropdownMenu:
    return DropdownMenu(
        trigger_label=trigger_label,
        items=tuple(items),
        id=id,
        **kwargs,
    )


def kbd(*keys: str, id: str | None = None, **kwargs: Any) -> Kbd:
    return Kbd(keys=keys, id=id, **kwargs)


def container(
    *children: Element,
    max_width: str = "1200px",
    centered: bool = True,
    id: str | None = None,
    **kwargs: Any,
) -> Container:
    return Container(
        children=children,
        max_width=max_width,
        centered=centered,
        id=id,
        **kwargs,
    )


def stack(
    *children: Element,
    direction: Literal["vertical", "horizontal"] = "vertical",
    gap: int = 16,
    align: Literal["start", "center", "end", "stretch"] = "stretch",
    id: str | None = None,
    **kwargs: Any,
) -> Stack:
    return Stack(
        children=children,
        direction=direction,
        gap=gap,
        align=align,
        id=id,
        **kwargs,
    )


def tag(
    label: str,
    variant: Literal["neutral", "primary", "success", "warning", "danger", "info"] = "neutral",
    removable: bool = False,
    remove_command: str | None = None,
    id: str | None = None,
    **kwargs: Any,
) -> Tag:
    return Tag(
        label=label,
        variant=variant,
        removable=removable,
        remove_command=remove_command,
        id=id,
        **kwargs,
    )
