# RADUI documentation site

The documentation app is split into focused modules:

- `app.py` is the CLI and static export entry point.
- `core.py` owns the shared RADUI app and reactive state.
- `theme.py` contains the RADUI theme and site styles.
- `layout.py` defines the persistent header, sidebar, and footer.
- `pages/intro.py` contains the overview and quickstart.
- `pages/systems.py` contains architecture, components, state, and transport guides.
- `pages/advanced.py` contains jobs, AI, CLI, and architecture decision references.
- `commands.py` contains handlers for live examples.
- `data.py` holds the component, CLI, and architecture decision catalogs.

Run locally with `python -m radui dev docs_site/app.py --port 3000 --open`.
Export static pages with `python -m radui export docs_site/app.py --static --output ./dist_docs`.
