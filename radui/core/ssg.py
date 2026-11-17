from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
import tracemalloc
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import urlsplit
from xml.sax.saxutils import escape as xml_escape

from radui.core.islands import Island
from radui.renderers.html import BASE_CSS, STATIC_JS
from radui.state.runtime import StateRuntime

_DYNAMIC_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_SAFE_PARAM_VALUE_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class RedirectRule:
    source: str
    destination: str
    status_code: int = 301


@dataclass(frozen=True)
class SSGConfig:
    """Configuration for deterministic Static Site Generation."""

    output_dir: Path
    base_url: str = ""
    environment: str = "production"
    clean: bool = True
    fingerprint_assets: bool = True
    inline_css: bool = False
    inline_js: bool = False
    build_timestamp: str | None = None
    assets_dir: Path | None = None

    def normalized_base_url(self) -> str:
        raw = self.base_url.strip().rstrip("/")
        if not raw:
            return ""
        validate_http_url(raw, label="base_url")
        return raw


@dataclass
class SSGBuildResult:
    """Machine-readable result of an SSG build."""

    output_dir: Path
    routes: list[dict[str, Any]] = field(default_factory=list)
    assets: dict[str, str] = field(default_factory=dict)
    islands: list[dict[str, Any]] = field(default_factory=list)
    redirects: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manifest_path: Path | None = None
    build_time_ms: float = 0.0
    asset_time_ms: float = 0.0
    total_html_bytes: int = 0
    total_css_bytes: int = 0
    total_output_bytes: int = 0
    peak_memory_bytes: int = 0


def validate_http_url(url: str, *, label: str = "URL") -> str:
    """Validate an absolute http:// or https:// URL without control chars."""
    if not isinstance(url, str) or not url or any(ord(c) < 32 for c in url):
        raise ValueError(f"Malformed {label}: {url!r}")
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError(f"Unsafe or unsupported scheme in {label}: {url!r}")
    return url


def validate_canonical_url(url: str) -> str:
    """Validate canonical URLs: either root-relative (/...) or http(s)://..."""
    if not isinstance(url, str) or not url or any(ord(c) < 32 for c in url):
        raise ValueError(f"Malformed canonical URL: {url!r}")
    if url.startswith("/"):
        if url.startswith("//") or ".." in url.split("/"):
            raise ValueError(f"Unsafe canonical URL path: {url!r}")
        return url
    return validate_http_url(url, label="canonical_url")


def validate_redirect_rule(
    source: str,
    destination: str,
    status_code: int = 301,
    *,
    allow_external: bool = False,
) -> RedirectRule:
    """Validate redirect source/destination to prevent open redirects or unsafe schemes."""
    if not isinstance(source, str) or not source.startswith("/") or source.startswith("//") or ".." in source.split("/"):
        raise ValueError(f"Invalid redirect source path: {source!r}")
    if not isinstance(destination, str) or not destination or any(ord(c) < 32 for c in destination):
        raise ValueError(f"Malformed redirect destination: {destination!r}")
    if destination.startswith("/"):
        if destination.startswith("//") or ".." in destination.split("/"):
            raise ValueError(f"Unsafe redirect destination path: {destination!r}")
    else:
        if not allow_external:
            raise ValueError(
                f"External redirect destination {destination!r} is disabled; pass allow_external=True to permit"
            )
        validate_http_url(destination, label="redirect destination")
    if status_code not in {301, 302, 303, 307, 308}:
        raise ValueError(f"Invalid redirect status_code: {status_code}")
    return RedirectRule(source=source, destination=destination, status_code=status_code)


def _validate_safe_route_param(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Dynamic route parameter {name!r} must be a non-empty string")
    if ".." in value or "/" in value or "\\" in value or "\x00" in value:
        raise ValueError(f"Unsafe path traversal characters in route parameter {name!r}: {value!r}")
    if not _SAFE_PARAM_VALUE_RE.fullmatch(value):
        raise ValueError(f"Invalid characters in route parameter {name!r}: {value!r}")
    return value


def _route_to_relative_html_path(route_path: str) -> Path:
    if route_path == "/":
        return Path("index.html")
    if route_path == "/404":
        return Path("404.html")
    clean = route_path.strip("/")
    if not clean or ".." in clean.split("/"):
        raise ValueError(f"Unsafe static route path: {route_path!r}")
    return Path(clean) / "index.html"


def _collect_islands(node: Any) -> list[Island]:
    found: list[Island] = []

    def walk(curr: Any) -> None:
        if isinstance(curr, Island):
            found.append(curr)
        for child in getattr(curr, "children", ()):
            walk(child)
        for attr in ("first", "second", "fallback"):
            sub = getattr(curr, attr, None)
            if sub is not None:
                walk(sub)

    walk(node)
    return found


def _expand_dynamic_route(
    pattern: str,
    param_names: list[str],
    ssg_paths: Callable[[], Iterable[Mapping[str, str]]] | Iterable[Mapping[str, str]] | None,
) -> list[tuple[str, dict[str, str]]]:
    if ssg_paths is None:
        raise ValueError(
            f"Dynamic route {pattern!r} requires explicit ssg_paths for deterministic SSG"
        )
    raw_items = ssg_paths() if callable(ssg_paths) else ssg_paths
    expanded: list[tuple[str, dict[str, str]]] = []
    seen_paths: set[str] = set()
    for item in raw_items:
        if not isinstance(item, Mapping):
            raise TypeError(f"ssg_paths entries for {pattern!r} must be mappings")
        params: dict[str, str] = {}
        concrete = pattern
        for pname in param_names:
            if pname not in item:
                raise ValueError(f"Missing parameter {pname!r} in ssg_paths entry for {pattern!r}")
            safe_val = _validate_safe_route_param(pname, item[pname])
            params[pname] = safe_val
            concrete = concrete.replace(f"{{{pname}}}", safe_val)
        if concrete in seen_paths:
            raise ValueError(f"Duplicate expanded route {concrete!r} in ssg_paths for {pattern!r}")
        seen_paths.add(concrete)
        expanded.append((concrete, params))
    expanded.sort(key=lambda entry: entry[0])
    return expanded


def _process_assets(
    assets_dir: Path | None,
    staging_dir: Path,
    *,
    fingerprint: bool,
    inline_css: bool,
    inline_js: bool,
) -> tuple[dict[str, str], int, str | None, str | None]:
    asset_map: dict[str, str] = {}
    used_targets: dict[str, str] = {}
    total_css_bytes = 0
    shared_css_url: str | None = None
    shared_js_url: str | None = None

    if assets_dir is not None and assets_dir.is_dir():
        resolved_root = assets_dir.resolve()
        files = sorted(
            (p for p in resolved_root.rglob("*") if p.is_file()),
            key=lambda p: p.relative_to(resolved_root).as_posix(),
        )
        for src in files:
            if src.is_symlink() and not src.resolve().is_relative_to(resolved_root):
                raise ValueError(f"Unsafe symlink escaping assets directory: {src}")
            rel = src.relative_to(resolved_root)
            rel_posix = rel.as_posix()
            data = src.read_bytes()
            digest = hashlib.sha256(data).hexdigest()[:12]

            if fingerprint:
                hashed_name = f"{rel.stem}.{digest}{rel.suffix}"
                target_rel = rel.with_name(hashed_name)
            else:
                target_rel = rel

            out_rel_posix = f"assets/{target_rel.as_posix()}"
            if out_rel_posix in used_targets:
                raise ValueError(
                    f"Asset output collision for {out_rel_posix!r} between {used_targets[out_rel_posix]} and {src}"
                )
            used_targets[out_rel_posix] = str(src)

            dest = (staging_dir / out_rel_posix).resolve()
            if not dest.is_relative_to(staging_dir.resolve()):
                raise ValueError(f"Unsafe asset output path: {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            asset_map[rel_posix] = f"/{out_rel_posix}"
            if rel.suffix.lower() == ".css":
                total_css_bytes += len(data)

    if not inline_css:
        css_bytes = BASE_CSS.encode("utf-8")
        css_digest = hashlib.sha256(css_bytes).hexdigest()[:12]
        css_rel = f"assets/radui.{css_digest}.css" if fingerprint else "assets/radui.css"
        if css_rel in used_targets:
            raise ValueError(f"Asset output collision for shared stylesheet {css_rel!r}")
        css_dest = (staging_dir / css_rel).resolve()
        css_dest.parent.mkdir(parents=True, exist_ok=True)
        css_dest.write_bytes(css_bytes)
        shared_css_url = f"/{css_rel}"
        asset_map["radui.css"] = shared_css_url
        total_css_bytes += len(css_bytes)

    if not inline_js:
        js_bytes = STATIC_JS.encode("utf-8")
        js_digest = hashlib.sha256(js_bytes).hexdigest()[:12]
        js_rel = f"assets/radui.static.{js_digest}.js" if fingerprint else "assets/radui.static.js"
        if js_rel in used_targets:
            raise ValueError(f"Asset output collision for shared script {js_rel!r}")
        js_dest = (staging_dir / js_rel).resolve()
        js_dest.parent.mkdir(parents=True, exist_ok=True)
        js_dest.write_bytes(js_bytes)
        shared_js_url = f"/{js_rel}"
        asset_map["radui.static.js"] = shared_js_url

    return dict(sorted(asset_map.items())), total_css_bytes, shared_css_url, shared_js_url


def _prune_stale_managed_files(
    output_dir: Path,
    new_routes: list[dict[str, Any]],
    new_assets: dict[str, str],
) -> None:
    """In --no-clean mode, remove previously built routes/assets absent from the new build."""
    manifest_file = output_dir / "build_manifest.json"
    if not manifest_file.is_file():
        return
    try:
        prev = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception:
        return

    new_route_outputs = {r["output"] for r in new_routes}
    new_asset_outputs = {v.lstrip("/") for v in new_assets.values()}
    output_resolved = output_dir.resolve()

    stale_rel_paths: list[str] = []
    for old_r in prev.get("routes", []):
        out_rel = old_r.get("output")
        if isinstance(out_rel, str) and out_rel not in new_route_outputs:
            stale_rel_paths.append(out_rel)
    for old_asset_url in prev.get("assets", {}).values():
        if isinstance(old_asset_url, str):
            rel = old_asset_url.lstrip("/")
            if rel not in new_asset_outputs:
                stale_rel_paths.append(rel)

    for rel_str in stale_rel_paths:
        target = (output_dir / rel_str).resolve()
        if target.is_relative_to(output_resolved) and target.is_file():
            target.unlink()
            parent = target.parent
            while parent != output_resolved and parent.exists():
                try:
                    parent.rmdir()
                    parent = parent.parent
                except OSError:
                    break


def _promote_staging(
    staging_dir: Path,
    output_dir: Path,
    *,
    clean: bool,
    new_routes: list[dict[str, Any]],
    new_assets: dict[str, str],
) -> None:
    """Promote staging_dir into output_dir without destroying the previous valid build on failure."""
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if clean:
        backup_dir: Path | None = None
        if output_dir.exists():
            backup_dir = output_dir.parent / f".radui-ssg-backup-{os.getpid()}-{int(time.perf_counter_ns())}"
            output_dir.replace(backup_dir)
        try:
            staging_dir.replace(output_dir)
        except Exception:
            if backup_dir is not None and backup_dir.exists() and not output_dir.exists():
                backup_dir.replace(output_dir)
            raise
        if backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
    else:
        if output_dir.exists():
            _prune_stale_managed_files(output_dir, new_routes, new_assets)
            shutil.copytree(staging_dir, output_dir, dirs_exist_ok=True)
            shutil.rmtree(staging_dir, ignore_errors=True)
        else:
            staging_dir.replace(output_dir)


def build_static_site(app: Any, config: SSGConfig) -> SSGBuildResult:
    """Build a deterministic static site from a RadUI App into config.output_dir."""
    tracemalloc.start()
    t0 = time.perf_counter()

    base_url = config.normalized_base_url()
    output_dir = Path(config.output_dir)
    staging_dir = output_dir.parent / f".radui-ssg-stage-{os.getpid()}-{int(time.perf_counter_ns())}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_resolved = staging_dir.resolve()

    result = SSGBuildResult(output_dir=output_dir)

    try:
        # 1. Process static assets & shared BASE_CSS / STATIC_JS deterministically
        t_asset_start = time.perf_counter()
        result.assets, result.total_css_bytes, shared_css_url, shared_js_url = _process_assets(
            config.assets_dir,
            staging_dir,
            fingerprint=config.fingerprint_assets,
            inline_css=config.inline_css,
            inline_js=config.inline_js,
        )
        stylesheet_href = f"{base_url}{shared_css_url}" if (shared_css_url and base_url) else shared_css_url
        script_src = f"{base_url}{shared_js_url}" if (shared_js_url and base_url) else shared_js_url
        result.asset_time_ms = (time.perf_counter() - t_asset_start) * 1000.0

        # 2. Discover & sort explicit static / dynamic routes
        custom_css = app.theme.to_css() if app.theme else ""
        direction = app.theme.direction if app.theme else "ltr"
        ssg_runtime = StateRuntime(f"{app.metadata.id}-ssg")

        route_records: list[dict[str, Any]] = []
        island_records: list[dict[str, Any]] = []
        sitemap_urls: list[str] = []

        for pattern in sorted(app._pages.keys()):
            page_def = app._pages[pattern]
            if not getattr(page_def, "ssg", True):
                result.warnings.append(f"Skipped non-SSG route: {pattern}")
                continue

            param_names = _DYNAMIC_PARAM_RE.findall(pattern)
            if param_names:
                targets = _expand_dynamic_route(pattern, param_names, getattr(page_def, "ssg_paths", None))
            else:
                targets = [(pattern, {})]

            for concrete_path, path_params in targets:
                rel_html = _route_to_relative_html_path(concrete_path)
                out_file = (staging_dir / rel_html).resolve()
                if not out_file.is_relative_to(staging_resolved):
                    raise ValueError(f"Unsafe output path for route {concrete_path!r}: {out_file}")

                state_ctx = ssg_runtime.context(session_id="ssg-build", view_id=concrete_path)
                with state_ctx.activate():
                    sig = _inspect_handler_params(page_def.handler)
                    root = page_def.handler(**path_params) if sig else page_def.handler()

                    for layout_prefix, layout_fn in sorted(getattr(app, "_layouts", []), key=lambda x: len(x[0])):
                        if concrete_path == layout_prefix or concrete_path.startswith(f"{layout_prefix.rstrip('/')}/"):
                            root = layout_fn(outlet=root)

                    app.registry.validate(root)
                    app._validate_commands(root)

                    canonical = getattr(page_def, "canonical_url", None)
                    if canonical is not None:
                        validate_canonical_url(canonical)
                    elif base_url:
                        canonical = f"{base_url}{concrete_path}" if concrete_path != "/" else f"{base_url}/"

                    doc_html = app.renderer.render_document(
                        page_def.title,
                        root,
                        state_context=state_ctx,
                        custom_css=custom_css,
                        view_id=concrete_path,
                        direction=direction,
                        static_export=True,
                        description=getattr(page_def, "description", None),
                        canonical_url=canonical,
                        og_tags=getattr(page_def, "og_metadata", None),
                        twitter_tags=getattr(page_def, "twitter_metadata", None),
                        meta_tags=getattr(page_def, "meta", None),
                        stylesheet_href=stylesheet_href,
                        script_src=script_src,
                    )

                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(doc_html, encoding="utf-8")
                html_bytes = len(doc_html.encode("utf-8"))
                result.total_html_bytes += html_bytes
                html_hash = hashlib.sha256(doc_html.encode("utf-8")).hexdigest()

                islands_in_page = _collect_islands(root)
                page_island_ids: list[str] = []
                for isl in sorted(islands_in_page, key=lambda x: x.id or x.name):
                    requires_runtime = isl.hydration in {"fetch", "sse"}
                    if requires_runtime:
                        result.warnings.append(
                            f"Route {concrete_path!r} contains runtime-dependent island {isl.id!r} (hydration={isl.hydration!r})"
                        )
                    page_island_ids.append(isl.id or isl.name)
                    island_records.append({
                        "route": concrete_path,
                        "island_id": isl.id or isl.name,
                        "name": isl.name,
                        "hydration": isl.hydration,
                        "trigger": isl.trigger,
                        "requires_runtime_server": requires_runtime,
                    })

                route_records.append({
                    "path": concrete_path,
                    "output": rel_html.as_posix(),
                    "sha256": html_hash,
                    "bytes": html_bytes,
                    "islands": page_island_ids,
                })
                if concrete_path != "/404":
                    loc = f"{base_url}{concrete_path}" if base_url else concrete_path
                    sitemap_urls.append(loc)

        # 3. Redirects manifest
        redirects = [
            {"source": r.source, "destination": r.destination, "status_code": r.status_code}
            for r in sorted(getattr(app, "_redirects", []), key=lambda x: x.source)
        ]
        result.redirects = redirects
        (staging_dir / "redirects.json").write_text(
            json.dumps(redirects, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # 4. Sitemap.xml and robots.txt
        sitemap_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        ]
        for loc in sorted(sitemap_urls):
            sitemap_lines.append(f"  <url><loc>{xml_escape(loc)}</loc></url>")
        sitemap_lines.append("</urlset>")
        (staging_dir / "sitemap.xml").write_text("\n".join(sitemap_lines) + "\n", encoding="utf-8")

        robots_lines = ["User-agent: *", "Allow: /"]
        if base_url:
            robots_lines.append(f"Sitemap: {base_url}/sitemap.xml")
        (staging_dir / "robots.txt").write_text("\n".join(robots_lines) + "\n", encoding="utf-8")

        # 5. Islands manifest
        result.islands = sorted(island_records, key=lambda r: (r["route"], r["island_id"]))
        (staging_dir / "islands_manifest.json").write_text(
            json.dumps(result.islands, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # 6. Machine-readable deterministic build manifest
        result.routes = sorted(route_records, key=lambda r: r["path"])
        manifest: dict[str, Any] = {
            "app_id": app.metadata.id,
            "app_name": app.metadata.name,
            "environment": config.environment,
            "base_url": base_url,
            "inline_css": config.inline_css,
            "inline_js": config.inline_js,
            "routes": result.routes,
            "assets": result.assets,
            "islands": result.islands,
            "redirects": result.redirects,
            "warnings": sorted(set(result.warnings)),
        }
        if config.build_timestamp is not None:
            manifest["build_timestamp"] = config.build_timestamp

        (staging_dir / "build_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        result.total_output_bytes = sum(
            p.stat().st_size for p in staging_dir.rglob("*") if p.is_file()
        )

        # 7. Safely promote staging_dir -> output_dir
        _promote_staging(
            staging_dir,
            output_dir,
            clean=config.clean,
            new_routes=result.routes,
            new_assets=result.assets,
        )

        result.manifest_path = output_dir / "build_manifest.json"
        result.build_time_ms = (time.perf_counter() - t0) * 1000.0
        _, peak_mem = tracemalloc.get_traced_memory()
        result.peak_memory_bytes = peak_mem
        return result
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    finally:
        tracemalloc.stop()


def _inspect_handler_params(handler: Callable[..., Any]) -> bool:
    import inspect
    return len(inspect.signature(handler).parameters) > 0
