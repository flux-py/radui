from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Type

from radui.components.nodes import (
    Accordion,
    AccordionItem,
    ActionCard,
    Avatar,
    AvatarGroup,
    Badge,
    Breadcrumb,
    BreadcrumbItem,
    Button,
    Callout,
    Card,
    ChatInput,
    ChatMessage,
    ChatView,
    Checkbox,
    CodeBlock,
    Column,
    Component,
    Container,
    DataGrid,
    DatePicker,
    Diagram,
    Divider,
    Drawer,
    DropdownMenu,
    DropdownMenuItem,
    DynamicCard,
    EmptyState,
    ErrorBoundary,
    FileUpload,
    Form,
    GenerativeSlot,
    Grid,
    Heading,
    Input,
    JobPanel,
    Kbd,
    Link,
    MetricCard,
    Modal,
    Pagination,
    Plot,
    Popover,
    ProgressBar,
    ProgressCircle,
    RadioGroup,
    Row,
    Select,
    Skeleton,
    Slider,
    Spacer,
    SplitPanel,
    Stack,
    StepTimeline,
    StreamingText,
    Switch,
    TabItem,
    Table,
    Tabs,
    Tag,
    Text,
    Textarea,
    ThemeToggle,
    TimePicker,
    Toast,
    ToastContainer,
    Tooltip,
    TreeView,
    VirtualList,
)


RenderFunction = Callable[[Component, "ComponentRegistry", object | None, str | None], str]


class UnregisteredComponentError(ValueError, TypeError):
    """Raised when an unregistered component kind is used in a RADUI UI tree."""


class DuplicateComponentRegistrationError(ValueError):
    """Raised when registering a component kind that is already registered with a differing model."""


@dataclass(frozen=True)
class ComponentDefinition:
    kind: str
    model: Type[Component]
    renderer: RenderFunction


class ComponentRegistry:
    """Allowlisted component model and renderer registry."""

    def __init__(self) -> None:
        self._definitions: dict[str, ComponentDefinition] = {}

    def register(
        self,
        kind: str,
        model: Type[Component],
        renderer: RenderFunction,
    ) -> None:
        if kind in self._definitions:
            if self._definitions[kind].model != model:
                raise DuplicateComponentRegistrationError(
                    f"Component kind '{kind}' already registered with a different model: {self._definitions[kind].model.__name__}"
                )
            raise DuplicateComponentRegistrationError(f"component kind already registered: {kind}")
        if model.model_fields.get("kind") is None:
            raise TypeError(f"{model.__name__} must declare a kind field")
        self._definitions[kind] = ComponentDefinition(kind, model, renderer)

    def get(self, kind: str) -> ComponentDefinition:
        try:
            return self._definitions[kind]
        except KeyError as exc:
            raise UnregisteredComponentError(
                f"unregistered component kind: '{kind}'. "
                f"Register it via app.registry.register('{kind}', Model, renderer) before using it in UI trees."
            ) from exc

    def validate(self, component: Component) -> None:
        if not isinstance(component, Component):
            raise TypeError(f"expected Component instance, got {type(component).__name__}")
        definition = self.get(component.kind)
        if not isinstance(component, definition.model):
            raise TypeError(
                f"component kind {component.kind!r} must use {definition.model.__name__}"
            )
        children = getattr(component, "children", ())
        if isinstance(children, (list, tuple)):
            for child in children:
                self.validate(child)
        for attr in ("first", "second"):
            if hasattr(component, attr):
                val = getattr(component, attr)
                if isinstance(val, Component):
                    self.validate(val)

    def deserialize(self, data: dict[str, Any]) -> Component:
        """Losslessly deserializes component data dictionaries into registered Component models."""
        if not isinstance(data, dict):
            raise TypeError(f"expected dict for component deserialization, got {type(data).__name__}")
        kind = data.get("kind")
        if not kind or not isinstance(kind, str):
            raise ValueError(f"component data missing valid 'kind': {data}")

        definition = self.get(kind)
        cleaned = dict(data)
        if "children" in cleaned and isinstance(cleaned["children"], (list, tuple)):
            cleaned["children"] = tuple(
                self.deserialize(c) if isinstance(c, dict) else c
                for c in cleaned["children"]
            )
        for attr in ("first", "second"):
            if attr in cleaned and isinstance(cleaned[attr], dict):
                cleaned[attr] = self.deserialize(cleaned[attr])

        return definition.model.model_validate(cleaned)

    def render(
        self,
        component: Component,
        state_context: object | None = None,
        csrf_token: str | None = None,
    ) -> str:
        definition = self.get(component.kind)
        if state_context is not None and component.id is not None:
            with state_context.track_component(component.id):
                return definition.renderer(component, self, state_context, csrf_token)
        return definition.renderer(component, self, state_context, csrf_token)

    @classmethod
    def builtins(cls) -> "ComponentRegistry":
        from radui.renderers.html import (
            render_accordion,
            render_accordion_item,
            render_action_card,
            render_avatar,
            render_avatar_group,
            render_badge,
            render_breadcrumb,
            render_breadcrumb_item,
            render_button,
            render_callout,
            render_card,
            render_chat_input,
            render_chat_message,
            render_chat_view,
            render_checkbox,
            render_code_block,
            render_column,
            render_container,
            render_data_grid,
            render_date_picker,
            render_diagram,
            render_divider,
            render_drawer,
            render_dropdown_menu,
            render_dropdown_menu_item,
            render_dynamic_card,
            render_empty_state,
            render_error_boundary,
            render_file_upload,
            render_form,
            render_generative_slot,
            render_grid,
            render_heading,
            render_input,
            render_job_panel,
            render_kbd,
            render_link,
            render_metric_card,
            render_modal,
            render_pagination,
            render_plot,
            render_popover,
            render_progress_bar,
            render_progress_circle,
            render_radio_group,
            render_row,
            render_select,
            render_skeleton,
            render_slider,
            render_spacer,
            render_split_panel,
            render_stack,
            render_step_timeline,
            render_streaming_text,
            render_switch,
            render_tab_item,
            render_table,
            render_tabs,
            render_tag,
            render_text,
            render_textarea,
            render_theme_toggle,
            render_time_picker,
            render_toast,
            render_toast_container,
            render_tooltip,
            render_tree_view,
            render_virtual_list,
        )

        registry = cls()
        registry.register("text", Text, render_text)
        registry.register("heading", Heading, render_heading)
        registry.register("link", Link, render_link)
        registry.register("divider", Divider, render_divider)
        registry.register("spacer", Spacer, render_spacer)
        registry.register("badge", Badge, render_badge)
        registry.register("callout", Callout, render_callout)
        registry.register("column", Column, render_column)
        registry.register("row", Row, render_row)
        registry.register("card", Card, render_card)
        registry.register("grid", Grid, render_grid)
        registry.register("tab_item", TabItem, render_tab_item)
        registry.register("tabs", Tabs, render_tabs)
        registry.register("modal", Modal, render_modal)
        registry.register("input", Input, render_input)
        registry.register("textarea", Textarea, render_textarea)
        registry.register("select", Select, render_select)
        registry.register("switch", Switch, render_switch)
        registry.register("radio_group", RadioGroup, render_radio_group)
        registry.register("checkbox", Checkbox, render_checkbox)
        registry.register("button", Button, render_button)
        registry.register("form", Form, render_form)
        registry.register("job_panel", JobPanel, render_job_panel)
        registry.register("metric_card", MetricCard, render_metric_card)
        registry.register("table", Table, render_table)
        registry.register("plot", Plot, render_plot)
        registry.register("chat_message", ChatMessage, render_chat_message)
        registry.register("chat_view", ChatView, render_chat_view)
        registry.register("chat_input", ChatInput, render_chat_input)
        registry.register("streaming_text", StreamingText, render_streaming_text)
        registry.register("action_card", ActionCard, render_action_card)
        registry.register("step_timeline", StepTimeline, render_step_timeline)
        registry.register("dynamic_card", DynamicCard, render_dynamic_card)
        registry.register("diagram", Diagram, render_diagram)
        registry.register("code_block", CodeBlock, render_code_block)
        registry.register("tree_view", TreeView, render_tree_view)
        registry.register("data_grid", DataGrid, render_data_grid)
        registry.register("generative_slot", GenerativeSlot, render_generative_slot)
        registry.register("skeleton", Skeleton, render_skeleton)
        registry.register("empty_state", EmptyState, render_empty_state)
        registry.register("file_upload", FileUpload, render_file_upload)
        registry.register("virtual_list", VirtualList, render_virtual_list)
        registry.register("theme_toggle", ThemeToggle, render_theme_toggle)
        registry.register("error_boundary", ErrorBoundary, render_error_boundary)
        registry.register("toast", Toast, render_toast)
        registry.register("toast_container", ToastContainer, render_toast_container)
        registry.register("tooltip", Tooltip, render_tooltip)
        registry.register("popover", Popover, render_popover)
        registry.register("accordion_item", AccordionItem, render_accordion_item)
        registry.register("accordion", Accordion, render_accordion)
        registry.register("drawer", Drawer, render_drawer)
        registry.register("breadcrumb_item", BreadcrumbItem, render_breadcrumb_item)
        registry.register("breadcrumb", Breadcrumb, render_breadcrumb)
        registry.register("pagination", Pagination, render_pagination)
        registry.register("progress_bar", ProgressBar, render_progress_bar)
        registry.register("progress_circle", ProgressCircle, render_progress_circle)
        registry.register("avatar", Avatar, render_avatar)
        registry.register("avatar_group", AvatarGroup, render_avatar_group)
        registry.register("date_picker", DatePicker, render_date_picker)
        registry.register("time_picker", TimePicker, render_time_picker)
        registry.register("slider", Slider, render_slider)
        registry.register("split_panel", SplitPanel, render_split_panel)
        registry.register("dropdown_menu_item", DropdownMenuItem, render_dropdown_menu_item)
        registry.register("dropdown_menu", DropdownMenu, render_dropdown_menu)
        registry.register("kbd", Kbd, render_kbd)
        registry.register("container", Container, render_container)
        registry.register("stack", Stack, render_stack)
        registry.register("tag", Tag, render_tag)
        return registry
