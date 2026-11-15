"""RadUI documentation app entry point.

Page content, theme, navigation, shared state, and handlers live in focused
modules and are registered here for the RadUI CLI and static exporter.
"""

from docs_site.core import app
import docs_site.layout as _layout
import docs_site.pages as _pages
import docs_site.commands as _commands

if __name__ == "__main__":
    app.run(port=3000)
