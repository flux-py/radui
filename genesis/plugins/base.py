"""RADUI Plugin and Extensibility Architecture."""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Any, Protocol

_LOGGER = logging.getLogger("radui.plugins")


class Plugin:
    """Base class for third-party RADUI plugins and extensions.
    
    Security Notice:
    Plugins run in-process within the host Python interpreter and share application memory.
    They are not isolated in an operating system sandbox or WebAssembly sandbox.
    """

    name: str = "plugin"
    version: str = "1.0.0"
    min_RADUI_version: str = "0.9.0"
    description: str = ""
    dependencies: list[str] = []

    def on_load(self, app: Any) -> None:
        """Invoked when the plugin is loaded into an active RADUI App."""
        pass

    def on_unload(self, app: Any) -> None:
        """Invoked when the plugin is unregistered or cleaned up."""
        pass

    def register_components(self, registry: Any) -> None:
        """Invoked to register custom component models and renderers."""
        pass


class PluginManager:
    """Discovers, validates, and manages RADUI plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        """Manually register a plugin instance."""
        if plugin.name in self._plugins:
            _LOGGER.warning("Overriding registered plugin: %s", plugin.name)
        self._plugins[plugin.name] = plugin

    def unregister(self, name: str, app: Any | None = None) -> Plugin | None:
        """Unregister a plugin and trigger cleanup hooks."""
        plugin = self._plugins.pop(name, None)
        if plugin is not None and app is not None:
            try:
                plugin.on_unload(app)
            except Exception as exc:
                _LOGGER.warning("Error during plugin unload for %s: %s", name, exc)
        return plugin

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def all_plugins(self) -> list[Plugin]:
        return list(self._plugins.values())

    def validate_dependencies(self) -> list[str]:
        """Validate that all declared dependencies of registered plugins are satisfied."""
        missing = []
        registered_names = set(self._plugins.keys())
        for plugin in self._plugins.values():
            for dep in plugin.dependencies:
                if dep not in registered_names:
                    missing.append(f"Plugin '{plugin.name}' requires '{dep}' which is not registered.")
        return missing

    def discover(self, group: str = "radui.plugins") -> int:
        """Discover installed plugins via setuptools / packaging entry points."""
        count = 0
        try:
            entry_points = importlib.metadata.entry_points()
            matches = entry_points.select(group=group) if hasattr(entry_points, "select") else entry_points.get(group, [])
            for ep in matches:
                try:
                    plugin_cls = ep.load()
                    plugin_instance = plugin_cls() if isinstance(plugin_cls, type) else plugin_cls
                    if isinstance(plugin_instance, Plugin):
                        self.register(plugin_instance)
                        count += 1
                except Exception as exc:
                    _LOGGER.warning("Failed to load plugin entry point %s: %s", ep.name, exc)
        except Exception:
            pass
        return count

    def apply_to_app(self, app: Any) -> None:
        """Apply all registered plugins to an App instance and its registry."""
        for plugin in self._plugins.values():
            try:
                plugin.register_components(app.registry)
                plugin.on_load(app)
            except Exception as exc:
                _LOGGER.exception("Error applying plugin %s: %s", plugin.name, exc)
