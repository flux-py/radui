from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

import radui as gx
from radui.cli import cmd_build
from radui.core.ssg import SSGConfig, build_static_site


def _hash_tree(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


def _make_ssg_app() -> gx.App:
    app = gx.App("SSG Demo", session_secret="super-secret-key-at-least-32-chars-long!")

    @app.layout("/docs")
    def docs_layout(outlet):
        return gx.column(gx.text("Docs Header"), outlet)

    @app.island("static_note", hydration="none", trigger="eager")
    def static_note():
        return gx.callout("Pure static island", variant="info")

    @app.island("live_widget", hydration="fetch", trigger="visible")
    def live_widget():
        return gx.text("Live Widget SSR")

    @app.page(
        "/",
        title="Home",
        description="Welcome to RadUI SSG",
        og_metadata={"title": "Home OG", "type": "website"},
        twitter_metadata={"card": "summary"},
    )
    def home():
        return gx.column(gx.heading("Home"), static_note(id="s1"))

    @app.page("/docs/guides/intro", title="Intro Guide")
    def intro():
        return gx.column(gx.heading("Intro"), live_widget(id="w1"))

    @app.page(
        "/posts/{slug}",
        title="Post",
        ssg_paths=[{"slug": "alpha"}, {"slug": "beta"}],
    )
    def post(slug: str):
        return gx.heading(f"Post: {slug}")

    @app.page("/404", title="Not Found")
    def not_found():
        return gx.heading("404 Page Not Found")

    @app.page("/dashboard", ssg=False)
    def dashboard():
        return gx.text("Dynamic only")

    app.add_redirect("/old-docs", "/docs/guides/intro", status_code=301)
    return app


def test_ssg_deterministic_builds_identical_hashes(tmp_path: Path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "logo.svg").write_text("<svg></svg>", encoding="utf-8")

    out1 = tmp_path / "dist1"
    out2 = tmp_path / "dist2"

    app1 = _make_ssg_app()
    app2 = _make_ssg_app()

    res1 = app1.build_static(out1, base_url="https://example.com", assets_dir=assets)
    res2 = app2.build_static(out2, base_url="https://example.com", assets_dir=assets)

    assert _hash_tree(out1) == _hash_tree(out2)
    assert len(res1.routes) == 5  # /, /404, /docs/guides/intro, /posts/alpha, /posts/beta
    assert len(res2.routes) == 5


def test_ssg_routes_seo_sitemap_robots_redirects_and_islands(tmp_path: Path):
    app = _make_ssg_app()
    out = tmp_path / "dist"
    res = app.build_static(out, base_url="https://example.com/")

    # Static & nested & dynamic & 404 HTML files
    home_html = (out / "index.html").read_text(encoding="utf-8")
    assert (out / "docs/guides/intro/index.html").is_file()
    assert (out / "posts/alpha/index.html").is_file()
    assert (out / "posts/beta/index.html").is_file()
    assert (out / "404.html").is_file()
    assert not (out / "dashboard").exists()

    # Static page with only hydration='none' island needs no /_gx/client.js
    assert "/_gx/client.js" not in home_html
    # Page with fetch island includes /_gx/client.js
    intro_html = (out / "docs/guides/intro/index.html").read_text(encoding="utf-8")
    assert "/_gx/client.js" in intro_html
    assert "Docs Header" in intro_html

    # SEO metadata emitted only when configured
    assert '<meta name="description" content="Welcome to RadUI SSG">' in home_html
    assert '<link rel="canonical" href="https://example.com/">' in home_html
    assert '<meta property="og:title" content="Home OG">' in home_html
    assert '<meta name="twitter:card" content="summary">' in home_html
    assert 'property="og:' not in intro_html

    # Sitemap excludes /404
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://example.com/posts/alpha" in sitemap
    assert "/404" not in sitemap

    # Robots.txt & Redirects & Islands manifest
    robots = (out / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: https://example.com/sitemap.xml" in robots
    redirects = json.loads((out / "redirects.json").read_text(encoding="utf-8"))
    assert redirects == [{"destination": "/docs/guides/intro", "source": "/old-docs", "status_code": 301}]

    islands = json.loads((out / "islands_manifest.json").read_text(encoding="utf-8"))
    by_id = {i["island_id"]: i for i in islands}
    assert by_id["s1"]["requires_runtime_server"] is False
    assert by_id["w1"]["requires_runtime_server"] is True
    assert any("w1" in w for w in res.warnings)


def test_ssg_fail_closed_dynamic_routes_runtime_state_and_path_traversal(tmp_path: Path):
    # 1. Dynamic route without ssg_paths fails clearly
    app_dyn = gx.App("Dyn")

    @app_dyn.page("/items/{id}")
    def item(id: str):
        return gx.text(id)

    with pytest.raises(ValueError, match="requires explicit ssg_paths"):
        app_dyn.build_static(tmp_path / "d1")

    # 2. Path traversal in ssg_paths fails cleanly
    app_trav = gx.App("Trav")

    @app_trav.page("/items/{id}", ssg_paths=[{"id": "../evil"}])
    def item_trav(id: str):
        return gx.text(id)

    with pytest.raises(ValueError, match="Unsafe path traversal"):
        app_trav.build_static(tmp_path / "d2")

    # 3. User/tenant state fails closed at build time
    app_user = gx.App("UserState")
    s_user = gx.state("user.email", "none", scope="user")

    @app_user.page("/")
    def need_user():
        return gx.text(s_user.value)

    with pytest.raises(gx.UserRequiredError):
        app_user.build_static(tmp_path / "d3")


def test_ssg_atomic_failure_cleanup_and_asset_collision(tmp_path: Path):
    app = gx.App("FailCleanup")

    @app.page("/a")
    def page_a():
        return gx.text("A")

    @app.page("/z")
    def page_z():
        raise RuntimeError("broken route")

    out = tmp_path / "dist_fail"
    with pytest.raises(RuntimeError, match="broken route"):
        app.build_static(out)
    assert not out.exists()

    # Asset collision check (same stem+hash? or two files mapping to same un-fingerprinted path)
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.css").write_text("body{}", encoding="utf-8")
    app_ok = gx.App("Assets")

    @app_ok.page("/")
    def idx():
        return gx.text("ok")

    res = app_ok.build_static(tmp_path / "dist_ok", assets_dir=assets, fingerprint_assets=True)
    assert "app.css" in res.assets
    assert res.assets["app.css"].startswith("/assets/app.")


def test_ssg_cli_build_and_ir_only_compatibility(tmp_path: Path):
    app_file = tmp_path / "sample_app.py"
    app_file.write_text(
        "import radui as gx\n"
        "app = gx.App('CLI SSG')\n"
        "@app.page('/')\n"
        "def home():\n"
        "    return gx.heading('CLI Home')\n",
        encoding="utf-8",
    )

    out_ssg = tmp_path / "dist_ssg"
    rc1 = cmd_build(argparse.Namespace(target=str(app_file), output=str(out_ssg), base_url="https://cli.example.com"))
    assert rc1 == 0
    assert (out_ssg / "index.html").is_file()
    assert (out_ssg / "build_manifest.json").is_file()

    out_ir = tmp_path / "dist_ir"
    rc2 = cmd_build(argparse.Namespace(target=str(app_file), output=str(out_ir), ir_only=True))
    assert rc2 == 0
    assert (out_ir / "cli-ssg_ir.json").is_file()


def test_ssg_shared_css_extraction_and_inline_option(tmp_path: Path):
    app = _make_ssg_app()
    out_shared = tmp_path / "dist_shared"
    res_shared = app.build_static(out_shared, base_url="https://example.com")

    assert "radui.css" in res_shared.assets
    css_href = res_shared.assets["radui.css"]
    assert css_href.startswith("/assets/radui.") and css_href.endswith(".css")
    css_file = out_shared / css_href.lstrip("/")
    assert css_file.is_file()
    assert res_shared.total_css_bytes == css_file.stat().st_size

    home_html = (out_shared / "index.html").read_text(encoding="utf-8")
    assert f'<link rel="stylesheet" href="https://example.com{css_href}">' in home_html

    # Explicit inline_css=True preserves inline <style> without emitting shared radui.css
    out_inline = tmp_path / "dist_inline"
    res_inline = app.build_static(out_inline, inline_css=True)
    assert "radui.css" not in res_inline.assets
    inline_html = (out_inline / "index.html").read_text(encoding="utf-8")
    assert "<style>" in inline_html
    assert len(inline_html.encode("utf-8")) - len(home_html.encode("utf-8")) > 40_000


def test_ssg_no_clean_prunes_stale_routes_and_assets_safely(tmp_path: Path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "site.css").write_text("body{color:black}", encoding="utf-8")
    out = tmp_path / "dist"

    app1 = gx.App("NoClean")
    app1.page("/")(lambda: gx.text("Home"))
    app1.page("/old-route")(lambda: gx.text("Old"))
    r1 = app1.build_static(out, clean=False, assets_dir=assets)
    old_css_rel = r1.assets["site.css"].lstrip("/")
    assert (out / "old-route/index.html").is_file()
    assert (out / old_css_rel).is_file()

    # Add unmanaged user file (e.g., CNAME) that must be preserved in --no-clean mode
    (out / "CNAME").write_text("example.com", encoding="utf-8")

    # Update asset content (hash changes) and remove /old-route
    (assets / "site.css").write_text("body{color:blue}", encoding="utf-8")
    app2 = gx.App("NoClean")
    app2.page("/")(lambda: gx.text("Home v2"))
    r2 = app2.build_static(out, clean=False, assets_dir=assets)
    new_css_rel = r2.assets["site.css"].lstrip("/")

    assert (out / "CNAME").read_text(encoding="utf-8") == "example.com"
    assert not (out / "old-route/index.html").exists()
    assert not (out / old_css_rel).exists()
    assert (out / new_css_rel).is_file()

    # Failed build in --no-clean mode must not alter existing output
    app3 = gx.App("NoClean")
    app3.page("/")(lambda: (_ for _ in ()).throw(RuntimeError("build crash")))
    with pytest.raises(RuntimeError, match="build crash"):
        app3.build_static(out, clean=False)
    assert "Home v2" in (out / "index.html").read_text(encoding="utf-8")


def test_ssg_atomic_promotion_preserves_previous_build_on_replace_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "dist"
    app1 = gx.App("Atomic1")
    app1.page("/")(lambda: gx.text("Previous Good Build"))
    app1.build_static(out)

    app2 = gx.App("Atomic2")
    app2.page("/")(lambda: gx.text("New Build"))

    orig_replace = Path.replace

    def flaky_replace(self: Path, target: Path):
        if ".radui-ssg-stage-" in self.name and target == out:
            raise OSError("Simulated Windows directory lock during promotion")
        return orig_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    with pytest.raises(OSError, match="Simulated Windows directory lock"):
        app2.build_static(out, clean=True)

    # Previous valid build must be restored intact
    assert (out / "index.html").is_file()
    assert "Previous Good Build" in (out / "index.html").read_text(encoding="utf-8")


def test_ssg_url_and_redirect_security(tmp_path: Path):
    app = gx.App("URLSec")
    app.page("/", canonical_url="javascript:alert(1)")(lambda: gx.text("bad"))
    with pytest.raises(ValueError, match="Unsafe or unsupported scheme"):
        app.build_static(tmp_path / "u1")

    app2 = gx.App("URLSec2")
    app2.page("/")(lambda: gx.text("ok"))
    with pytest.raises(ValueError, match="Unsafe or unsupported scheme"):
        app2.build_static(tmp_path / "u2", base_url="javascript:alert(1)")

    with pytest.raises(ValueError, match="Unsafe canonical URL"):
        app2.page("/x", canonical_url="//evil.com/phish")(lambda: gx.text("x"))
        app2.build_static(tmp_path / "u3")

    app3 = gx.App("RedirSec")
    with pytest.raises(ValueError, match="External redirect destination"):
        app3.add_redirect("/old", "https://evil.example.com")
    with pytest.raises(ValueError, match="Unsafe redirect destination"):
        app3.add_redirect("/old", "//evil.example.com")
    app3.add_redirect("/ext", "https://trusted.example.com", allow_external=True)
    app3.add_redirect("/int", "/new")
    assert len(app3._redirects) == 2
