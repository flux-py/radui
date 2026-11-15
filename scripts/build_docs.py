"""Build and export the RADUI documentation website for GitHub Pages deployment."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
import subprocess
import sys

def build():
    root = Path(__file__).resolve().parent.parent
    dist = root / "dist_docs"
    
    # 1. Export static pages using radui CLI
    print("--> Exporting static pages via radui CLI...")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if "PYTHONPATH" in env else "")
    cmd = [sys.executable, "-m", "radui", "export", "docs_site/app.py", "--static", "--output", str(dist)]
    res = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)

    # 2. Mirror each route as a directory with index.html for clean URLs
    for html_file in dist.glob("*.html"):
        if html_file.name in ("index.html", "404.html"):
            continue
        folder = dist / html_file.stem
        folder.mkdir(exist_ok=True)
        shutil.copy2(html_file, folder / "index.html")
        print(f"--> Created folder mirror: {folder}/index.html")

    # 3. Create 404.html with smart router fallback
    redirect_code = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>RADUI Documentation</title>
  <script>
    var path = window.location.pathname;
    var repo = '/radui';
    var clean = path.startsWith(repo) ? path.slice(repo.length) : path;
    clean = clean.replace(/^\\/+|\\/+$/g, '');
    if (!clean) {
      window.location.replace(repo + '/');
    } else {
      var target = clean.endsWith('.html') ? clean : clean + '.html';
      window.location.replace(repo + '/' + target);
    }
  </script>
</head>
<body style="font-family:sans-serif;padding:40px;text-align:center;">
  <h2>Redirecting to RADUI Documentation...</h2>
</body>
</html>"""
    (dist / "404.html").write_text(redirect_code, encoding="utf-8")
    (dist / ".nojekyll").touch()
    print("--> Successfully built documentation in:", dist)

if __name__ == "__main__":
    build()
