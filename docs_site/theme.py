"""Theme tokens and styles for the RADUI documentation app."""

CUSTOM_CSS = """
:root, [data-theme], html, body {
  --gx-font: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
  --gx-font-mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace !important;
  --gx-bg: #f5f4ef !important;
  --gx-surface: #ffffff !important;
  --gx-surface-alt: #f0efe9 !important;
  --gx-text: #19221e !important;
  --gx-text-muted: #69736c !important;
  --gx-border: #e5e4dc !important;
  --gx-border-strong: #d4d5ca !important;
  --gx-primary: #206b52 !important;
  --gx-primary-hover: #174d3b !important;
  --gx-primary-subtle: #e7f1eb !important;
  color-scheme: light !important;
}
html { scroll-behavior: smooth; scroll-padding-top: 84px; }
body {
  background: #f5f4ef !important;
  background-image: radial-gradient(ellipse at 50% -25%, rgba(184, 207, 185, .42), transparent 62%),
    linear-gradient(90deg, rgba(32,107,82,.025) 1px, transparent 1px),
    linear-gradient(rgba(32,107,82,.025) 1px, transparent 1px) !important;
  background-size: auto, 52px 52px, 52px 52px !important;
  color: #19221e !important;
  font-family: var(--gx-font) !important;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
}
#docs-shell { max-width: 1320px !important; padding: 0 36px !important; }
.gx-shell:has(#docs-shell) { width: min(1400px, calc(100% - 36px)) !important; max-width: none !important; margin: 24px auto 64px !important; }
#docs-header {
  position: sticky; top: 0; z-index: 30; padding: 18px 0 14px;
  background: rgba(245,244,239,.9); backdrop-filter: blur(18px);
  border-bottom: 1px solid rgba(212,213,202,.72); margin-bottom: 28px;
}
#docs-header .gx-heading { margin: 0; font-size: 1.2rem !important; letter-spacing: -.055em !important; color: #19221e !important; }
#docs-header .gx-link { padding: 7px 10px; border-radius: 8px; color: #536158 !important; font-size: .88rem; text-decoration: none; transition: color .18s ease, background .18s ease; }
#docs-header .gx-link:hover { color: #174d3b !important; background: #e7f1eb; text-decoration: none; }
#docs-layout { align-items: start; grid-template-columns: 224px minmax(0,1fr) !important; gap: 62px !important; }
#docs-sidebar { position: sticky; top: 102px; padding: 4px 0 20px; max-height: calc(100vh - 116px); overflow: auto; }
#docs-sidebar .gx-heading { color: #879087 !important; font-size: .7rem !important; font-weight: 700 !important; letter-spacing: .12em !important; text-transform: uppercase; margin: 16px 0 6px; }
#docs-sidebar .gx-accordion { border: 0 !important; gap: 15px; overflow: visible !important; background: transparent !important; }
#docs-sidebar .gx-accordion-item { border: 0 !important; background: transparent !important; }
#docs-sidebar .gx-accordion-header { padding: 2px 0 7px !important; background: transparent !important; color: #26332b !important; font-size: .82rem !important; font-weight: 700 !important; }
#docs-sidebar .gx-accordion-content { border: 0 !important; padding: 0 !important; background: transparent !important; }
#docs-sidebar .gx-column { gap: 2px !important; }
#docs-sidebar .gx-link { color: #69736c !important; padding: 5px 9px !important; border-radius: 6px; font-size: .84rem !important; font-weight: 450 !important; text-decoration: none; transition: color .18s ease, background .18s ease, transform .18s ease; }
#docs-sidebar .gx-link:hover { color: #174d3b !important; background: #e7f1eb; padding-left: 13px !important; text-shadow: none !important; }
#docs-sidebar > .gx-card { margin-top: 22px; padding: 14px !important; background: rgba(255,255,255,.62) !important; box-shadow: none !important; border-radius: 12px !important; }
#docs-sidebar > .gx-card .gx-text { font-size: .8rem; }
#docs-content { min-width: 0; padding: 3px 0 54px; animation: docs-enter .55s cubic-bezier(.2,.75,.25,1) both; }
@keyframes docs-enter { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes docs-reveal { from { opacity: .55; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
@supports (animation-timeline: view()) {
  #docs-content .gx-grid .gx-card {
    animation: docs-reveal .65s ease both;
    animation-timeline: view();
    animation-range: entry 0% cover 18%;
  }
}
.gx-heading { color: #19221e !important; letter-spacing: -.04em !important; line-height: 1.16 !important; }
#docs-content > .gx-column > .gx-heading:first-child { font-size: clamp(2.1rem, 4vw, 3.35rem) !important; max-width: 850px; margin: 0; }
#docs-content .gx-column:first-child > .gx-heading { font-size: clamp(2.35rem, 4.5vw, 3.8rem) !important; max-width: 780px; }
.gx-text { color: #536158 !important; line-height: 1.72 !important; }
.gx-text[class*="lead"] { max-width: 690px; color: #536158 !important; font-size: 1.12rem !important; }
.gx-card {
  display: flex !important; flex-direction: column !important; gap: 14px !important;
  position: relative; isolation: isolate;
  background: rgba(255,255,255,.88) !important; border: 1px solid #e5e4dc !important;
  border-radius: 16px !important; padding: 22px !important; box-shadow: 0 6px 22px rgba(36,48,39,.035) !important;
  transition: transform .24s cubic-bezier(.2,.75,.25,1), box-shadow .24s ease, border-color .24s ease !important;
}
.gx-card::after, .gx-metric::after, .gx-code-block::after {
  content: ""; position: absolute; inset: 0; z-index: 0; border-radius: inherit; pointer-events: none;
  opacity: 0; background: radial-gradient(340px circle at var(--gx-pointer-x, 50%) var(--gx-pointer-y, 50%), rgba(74,145,101,.13), transparent 72%);
  transition: opacity .22s ease;
}
.gx-card > *, .gx-metric > *, .gx-code-block > * { position: relative; z-index: 1; }
.gx-card:hover, .gx-metric:hover, .gx-code-block:hover { --gx-pointer-x: 50%; --gx-pointer-y: 50%; }
.gx-card:hover::after, .gx-metric:hover::after, .gx-code-block:hover::after { opacity: 1; }
.gx-card:hover { transform: translateY(-4px); border-color: #b9d1c1 !important; box-shadow: 0 18px 40px rgba(36,48,39,.11) !important; }
.gx-metric { position: relative; isolation: isolate; background: #f8f8f4 !important; border: 1px solid #e8e9e2 !important; border-radius: 12px !important; padding: 17px !important; transition: transform .2s ease, border-color .2s ease !important; }
.gx-metric:hover { transform: translateY(-2px); border-color: #b9d1c1 !important; }
.gx-metric-value { color: #206b52 !important; font-family: var(--gx-font-mono) !important; font-size: 1.8rem !important; font-weight: 700 !important; }
.gx-badge { border-radius: 999px !important; padding: 4px 10px !important; font-size: .72rem !important; letter-spacing: .02em; }
.gx-badge-primary { color: #206b52 !important; background: #e7f1eb !important; border: 1px solid #d0e4d6 !important; }
.gx-badge-success { color: #276a4a !important; background: #e8f3e8 !important; border: 1px solid #d0e5d1 !important; }
.gx-badge-neutral { color: #606a62 !important; background: #f0efe9 !important; border: 1px solid #e1e0d8 !important; }
.gx-btn, .gx-button { border-radius: 9px !important; transition: transform .18s ease, box-shadow .18s ease, background .18s ease !important; }
.gx-btn:hover, .gx-button:hover { transform: translateY(-2px); }
.gx-btn:active, .gx-button:active { transform: translateY(0) scale(.96) !important; box-shadow: 0 1px 4px rgba(25,34,30,.18) !important; }
.gx-button.is-selected { outline: 2px solid rgba(32,107,82,.26) !important; outline-offset: 2px; }
.gx-button-primary, .gx-btn-primary { background: #206b52 !important; box-shadow: 0 4px 12px rgba(32,107,82,.15) !important; }
.gx-button-primary:hover, .gx-btn-primary:hover { background: #174d3b !important; box-shadow: 0 7px 18px rgba(32,107,82,.23) !important; }
.gx-link { display: inline-block; color: #206b52 !important; text-decoration-color: rgba(32,107,82,.25); text-underline-offset: 3px; transition: color .18s ease, transform .18s ease, background .18s ease; }
.gx-link:hover { color: #174d3b !important; transform: translateY(-1px); }
.gx-link:active { transform: translateY(0) scale(.98); }
.gx-code-block { position: relative; isolation: isolate; background: #1e2823 !important; color: #e6eee8 !important; border: 1px solid #303e35 !important; border-radius: 13px !important; box-shadow: 0 12px 30px rgba(25,34,30,.1) !important; font-size: .86rem !important; transition: border-color .2s ease, box-shadow .2s ease !important; }
.gx-code-block:hover { border-color: #579477 !important; box-shadow: 0 16px 38px rgba(25,34,30,.16) !important; }
.gx-callout { border-left: 3px solid #4b9674 !important; border-radius: 8px 12px 12px 8px !important; background: #edf4ed !important; }
.gx-accordion { border-color: #e5e4dc !important; border-radius: 12px !important; background: rgba(255,255,255,.65) !important; }
.gx-accordion-item { border-color: #e5e4dc !important; }
.gx-accordion-header { background: #fff !important; transition: background .18s ease, color .18s ease; }
.gx-accordion-header:hover { background: #f6f8f4 !important; color: #206b52 !important; }
.gx-accordion-content { background: #fff !important; border-color: #e5e4dc !important; }
.gx-input, .gx-select, .gx-textarea { border-radius: 9px !important; border-color: #d9dcd4 !important; background: #fff !important; }
.gx-input:focus, .gx-select:focus, .gx-textarea:focus { border-color: #579477 !important; box-shadow: 0 0 0 3px rgba(32,107,82,.12) !important; outline: none !important; }
.gx-tabs-header { border-color: #e5e4dc !important; }
.gx-tab-btn { transition: color .18s ease, border-color .18s ease, background .18s ease; }
.gx-tab-btn:hover { color: #206b52 !important; }
:focus-visible { outline: 3px solid rgba(32,107,82,.55) !important; outline-offset: 3px; }
::selection { background: #cfe3d4; color: #19221e; }
@media (max-width: 960px) {
  #docs-shell { padding: 0 22px !important; }
  #docs-layout { grid-template-columns: 1fr !important; gap: 20px !important; }
  #docs-sidebar { position: relative; top: auto; max-height: none; padding-bottom: 0; }
  #docs-sidebar > .gx-card { display: none; }
}
@media (max-width: 640px) {
  #docs-shell { padding: 0 16px !important; }
  #docs-header { position: relative; margin-bottom: 20px; }
  #docs-header > .gx-row { align-items: flex-start !important; flex-direction: column; gap: 10px !important; }
  #docs-header > .gx-row:last-child { flex-direction: row; flex-wrap: wrap; }
  #docs-content > .gx-column > .gx-heading:first-child { font-size: 2.15rem !important; }
  .gx-card { padding: 17px !important; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
}
"""
