"""Theme tokens, dual-theme definitions, dynamic micro-interactions, and visual styles for RADUI documentation."""

CUSTOM_CSS = """
/* =========================================================================
   1. DUAL THEMES (LIGHT EDITORIAL & DARK OBSIDIAN)
   ========================================================================= */

/* Light Theme (Default Editorial Paper & Deep Jade) */
:root, [data-theme="light"], html:not([data-theme="dark"]) {
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
  --gx-header-bg: rgba(245, 244, 239, 0.92) !important;
  --gx-header-border: rgba(212, 213, 202, 0.72) !important;
  --gx-card-bg: rgba(255, 255, 255, 0.90) !important;
  --gx-card-border: #e5e4dc !important;
  --gx-grid-line: rgba(32, 107, 82, 0.025) !important;
  --gx-spotlight: rgba(74, 145, 101, 0.12) !important;
  --gx-code-bg: #1e2823 !important;
  --gx-code-text: #e6eee8 !important;
  --gx-callout-bg: #edf4ed !important;
  --gx-badge-bg: #e7f1eb !important;
  --gx-badge-text: #206b52 !important;
  color-scheme: light !important;
}

/* Dark Theme (Deep Obsidian & Luminous Mint/Emerald) */
[data-theme="dark"], html[data-theme="dark"], body[data-theme="dark"] {
  --gx-font: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
  --gx-font-mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace !important;
  --gx-bg: #090e0b !important;
  --gx-surface: #101713 !important;
  --gx-surface-alt: #16201a !important;
  --gx-text: #f0fdf4 !important;
  --gx-text-muted: #8ca395 !important;
  --gx-border: #1d2b22 !important;
  --gx-border-strong: #2c4234 !important;
  --gx-primary: #10b981 !important;
  --gx-primary-hover: #34d399 !important;
  --gx-primary-subtle: rgba(16, 185, 129, 0.14) !important;
  --gx-header-bg: rgba(9, 14, 11, 0.90) !important;
  --gx-header-border: rgba(29, 43, 34, 0.85) !important;
  --gx-card-bg: rgba(16, 23, 19, 0.86) !important;
  --gx-card-border: #1d2b22 !important;
  --gx-grid-line: rgba(16, 185, 129, 0.045) !important;
  --gx-spotlight: rgba(52, 211, 153, 0.14) !important;
  --gx-code-bg: #080d0a !important;
  --gx-code-text: #a7f3d0 !important;
  --gx-callout-bg: rgba(16, 185, 129, 0.10) !important;
  --gx-badge-bg: rgba(16, 185, 129, 0.16) !important;
  --gx-badge-text: #34d399 !important;
  color-scheme: dark !important;
}

/* =========================================================================
   2. GLOBAL FOUNDATIONS & BACKGROUNDS
   ========================================================================= */
html {
  scroll-behavior: smooth;
  scroll-padding-top: 84px;
}

body {
  background-color: var(--gx-bg) !important;
  background-image:
    radial-gradient(ellipse at 50% -20%, var(--gx-primary-subtle), transparent 62%),
    linear-gradient(90deg, var(--gx-grid-line) 1px, transparent 1px),
    linear-gradient(var(--gx-grid-line) 1px, transparent 1px) !important;
  background-size: auto, 52px 52px, 52px 52px !important;
  color: var(--gx-text) !important;
  font-family: var(--gx-font) !important;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
  transition: background-color 0.25s ease, color 0.25s ease;
}

#docs-shell {
  max-width: 1320px !important;
  padding: 0 36px !important;
}

.gx-shell:has(#docs-shell) {
  width: min(1400px, calc(100% - 36px)) !important;
  max-width: none !important;
  margin: 24px auto 64px !important;
}

/* =========================================================================
   3. HEADER & LOGO BRAND LOCKUP
   ========================================================================= */
#docs-header {
  position: sticky; top: 0; z-index: 30; padding: 14px 0 12px;
  background: var(--gx-header-bg); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--gx-header-border); margin-bottom: 28px;
  transition: background-color 0.25s ease, border-color 0.25s ease;
}

#docs-logo-link {
  display: inline-flex !important;
  align-items: center !important;
  gap: 10px !important;
  text-decoration: none !important;
  cursor: pointer;
  transition: transform 0.2s cubic-bezier(0.2, 0.75, 0.25, 1);
}
#docs-logo-link:hover {
  transform: translateY(-1px);
  text-decoration: none !important;
}

#docs-brand-logo {
  display: inline-flex !important;
  align-items: center !important;
  gap: 9px !important;
  margin: 0 !important;
  font-size: 1.25rem !important;
  font-weight: 800 !important;
  letter-spacing: -.045em !important;
  color: var(--gx-text) !important;
}
#docs-brand-logo::before {
  content: "";
  display: inline-block;
  width: 26px;
  height: 26px;
  background: url("assets/radui-mark.svg") no-repeat center / contain;
  vertical-align: middle;
  flex-shrink: 0;
  transition: transform 0.35s cubic-bezier(0.2, 0.75, 0.25, 1), filter 0.35s ease;
}
#docs-logo-link:hover #docs-brand-logo::before {
  transform: rotate(10deg) scale(1.14);
  filter: drop-shadow(0 0 8px rgba(52, 211, 153, 0.65));
}

#docs-header .gx-link {
  padding: 7px 12px; border-radius: 8px; color: var(--gx-text-muted) !important;
  font-size: .88rem; font-weight: 500; text-decoration: none;
  transition: color .18s ease, background-color .18s ease, transform .18s ease;
}
#docs-header .gx-link:hover {
  color: var(--gx-primary) !important; background-color: var(--gx-primary-subtle);
  transform: translateY(-1px); text-decoration: none;
}

/* Native Theme Toggle Pill */
.gx-theme-toggle {
  display: inline-flex !important;
  align-items: center !important;
  gap: 7px !important;
  padding: 6px 13px !important;
  font-size: 0.82rem !important;
  font-weight: 600 !important;
  border-radius: 8px !important;
  border: 1px solid var(--gx-border) !important;
  background: var(--gx-surface) !important;
  color: var(--gx-text) !important;
  cursor: pointer !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
  transition: all 0.2s cubic-bezier(0.2, 0.75, 0.25, 1) !important;
}
.gx-theme-toggle:hover {
  border-color: var(--gx-primary) !important;
  background: var(--gx-primary-subtle) !important;
  color: var(--gx-primary) !important;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px var(--gx-spotlight) !important;
}
.gx-theme-toggle:active {
  transform: scale(0.96) !important;
}

/* =========================================================================
   4. SIDEBAR NAVIGATION
   ========================================================================= */
#docs-layout {
  align-items: start;
  grid-template-columns: 224px minmax(0,1fr) !important;
  gap: 62px !important;
}
#docs-sidebar {
  position: sticky; top: 102px; padding: 4px 0 20px;
  max-height: calc(100vh - 116px); overflow: auto;
}
#docs-sidebar .gx-heading {
  color: var(--gx-text-muted) !important; font-size: .7rem !important;
  font-weight: 700 !important; letter-spacing: .12em !important;
  text-transform: uppercase; margin: 16px 0 6px;
}
#docs-sidebar .gx-accordion {
  border: 0 !important; gap: 15px; overflow: visible !important;
  background: transparent !important;
}
#docs-sidebar .gx-accordion-item {
  border: 0 !important; background: transparent !important;
}
#docs-sidebar .gx-accordion-header {
  padding: 4px 0 8px !important; background: transparent !important;
  color: var(--gx-text) !important; font-size: .83rem !important; font-weight: 700 !important;
  transition: color 0.18s ease;
}
#docs-sidebar .gx-accordion-header:hover {
  color: var(--gx-primary) !important;
}
#docs-sidebar .gx-accordion-content {
  border: 0 !important; padding: 0 !important; background: transparent !important;
}
#docs-sidebar .gx-column { gap: 2px !important; }
#docs-sidebar .gx-link {
  color: var(--gx-text-muted) !important; padding: 6px 10px !important;
  border-radius: 6px; font-size: .84rem !important; font-weight: 450 !important;
  text-decoration: none; transition: color .18s ease, background-color .18s ease, transform .18s ease;
}
#docs-sidebar .gx-link:hover {
  color: var(--gx-primary) !important; background-color: var(--gx-primary-subtle);
  padding-left: 14px !important; text-shadow: none !important;
}
#docs-sidebar > .gx-card {
  margin-top: 22px; padding: 14px !important;
  background: var(--gx-surface) !important; box-shadow: none !important;
  border: 1px solid var(--gx-border) !important; border-radius: 12px !important;
}
#docs-sidebar > .gx-card .gx-text { font-size: .8rem; }

/* =========================================================================
   5. CONTENT & DYNAMIC MICRO-INTERACTIONS
   ========================================================================= */
#docs-content {
  min-width: 0; padding: 3px 0 54px;
  animation: docs-enter .5s cubic-bezier(.2,.75,.25,1) both;
}
@keyframes docs-enter {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.gx-heading {
  color: var(--gx-text) !important;
  letter-spacing: -.038em !important;
  line-height: 1.18 !important;
  transition: color 0.25s ease;
}
#docs-content > .gx-column > .gx-heading:first-child {
  font-size: clamp(2.1rem, 4vw, 3.35rem) !important;
  max-width: 850px; margin: 0;
}
.gx-text {
  color: var(--gx-text-muted) !important;
  line-height: 1.72 !important;
  transition: color 0.25s ease;
}
.gx-text[class*="lead"] {
  max-width: 690px;
  font-size: 1.12rem !important;
}

/* Interactive Cards with Pointer Spotlight Sheen */
.gx-card {
  display: flex !important; flex-direction: column !important; gap: 14px !important;
  position: relative; isolation: isolate;
  background: var(--gx-card-bg) !important; border: 1px solid var(--gx-card-border) !important;
  border-radius: 16px !important; padding: 22px !important;
  box-shadow: 0 6px 22px rgba(0,0,0,.04) !important;
  transition: transform .24s cubic-bezier(.2,.75,.25,1), box-shadow .24s ease, border-color .24s ease, background-color .24s ease !important;
}
.gx-card::after, .gx-metric::after, .gx-code-block::after {
  content: ""; position: absolute; inset: 0; z-index: 0; border-radius: inherit; pointer-events: none;
  opacity: 0;
  background: radial-gradient(360px circle at var(--gx-pointer-x, 50%) var(--gx-pointer-y, 50%), var(--gx-spotlight), transparent 72%);
  transition: opacity .22s ease;
}
.gx-card > *, .gx-metric > *, .gx-code-block > * { position: relative; z-index: 1; }
.gx-card:hover, .gx-metric:hover, .gx-code-block:hover { --gx-pointer-x: 50%; --gx-pointer-y: 50%; }
.gx-card:hover::after, .gx-metric:hover::after, .gx-code-block:hover::after { opacity: 1; }
.gx-card:hover {
  transform: translateY(-3px);
  border-color: var(--gx-primary) !important;
  box-shadow: 0 16px 38px rgba(0,0,0,.09) !important;
}

.gx-metric {
  position: relative; isolation: isolate;
  background: var(--gx-surface-alt) !important; border: 1px solid var(--gx-border) !important;
  border-radius: 12px !important; padding: 17px !important;
  transition: transform .2s ease, border-color .2s ease, background-color .2s ease !important;
}
.gx-metric:hover {
  transform: translateY(-2px);
  border-color: var(--gx-primary) !important;
}
.gx-metric-value {
  color: var(--gx-primary) !important;
  font-family: var(--gx-font-mono) !important;
  font-size: 1.8rem !important;
  font-weight: 700 !important;
}

/* Badges */
.gx-badge {
  border-radius: 999px !important; padding: 4px 10px !important;
  font-size: .72rem !important; letter-spacing: .02em; font-weight: 600;
  transition: background-color 0.2s ease, color 0.2s ease;
}
.gx-badge-primary {
  color: var(--gx-badge-text) !important;
  background: var(--gx-badge-bg) !important;
  border: 1px solid var(--gx-primary) !important;
}
.gx-badge-success {
  color: #10b981 !important;
  background: rgba(16, 185, 129, 0.12) !important;
  border: 1px solid rgba(16, 185, 129, 0.3) !important;
}
.gx-badge-neutral {
  color: var(--gx-text-muted) !important;
  background: var(--gx-surface-alt) !important;
  border: 1px solid var(--gx-border) !important;
}

/* Buttons with Tactile Elevation */
.gx-btn, .gx-button {
  border-radius: 9px !important;
  font-weight: 600 !important;
  transition: transform .18s cubic-bezier(.2,.75,.25,1), box-shadow .18s ease, background-color .18s ease !important;
}
.gx-btn:hover, .gx-button:hover {
  transform: translateY(-2px);
}
.gx-btn:active, .gx-button:active {
  transform: translateY(0) scale(.97) !important;
  box-shadow: 0 1px 4px rgba(0,0,0,.15) !important;
}
.gx-button.is-selected {
  outline: 2px solid var(--gx-primary) !important;
  outline-offset: 2px;
}
.gx-button-primary, .gx-btn-primary {
  background: var(--gx-primary) !important;
  color: #ffffff !important;
  box-shadow: 0 4px 14px var(--gx-spotlight) !important;
}
.gx-button-primary:hover, .gx-btn-primary:hover {
  background: var(--gx-primary-hover) !important;
  box-shadow: 0 6px 18px rgba(16, 185, 129, 0.28) !important;
}

/* Links */
.gx-link {
  display: inline-block; color: var(--gx-primary) !important;
  text-decoration-color: rgba(32,107,82,.25); text-underline-offset: 3px;
  transition: color .18s ease, transform .18s ease;
}
.gx-link:hover {
  color: var(--gx-primary-hover) !important;
  transform: translateY(-1px);
}

/* Code Blocks & Callouts */
.gx-code-block {
  position: relative; isolation: isolate;
  background: var(--gx-code-bg) !important; color: var(--gx-code-text) !important;
  border: 1px solid var(--gx-border) !important; border-radius: 13px !important;
  box-shadow: 0 12px 30px rgba(0,0,0,.12) !important; font-size: .86rem !important;
  transition: border-color .2s ease, box-shadow .2s ease, background-color .2s ease !important;
}
.gx-code-block:hover {
  border-color: var(--gx-primary) !important;
  box-shadow: 0 16px 36px rgba(0,0,0,.18) !important;
}
.gx-callout {
  border-left: 3px solid var(--gx-primary) !important;
  border-radius: 8px 12px 12px 8px !important;
  background: var(--gx-callout-bg) !important;
  color: var(--gx-text) !important;
  transition: background-color 0.25s ease, border-color 0.25s ease;
}

/* Accordions */
.gx-accordion {
  border-color: var(--gx-border) !important; border-radius: 12px !important;
  background: var(--gx-surface) !important;
}
.gx-accordion-item { border-color: var(--gx-border) !important; }
.gx-accordion-header {
  background: var(--gx-surface) !important; color: var(--gx-text) !important;
  transition: background-color .18s ease, color .18s ease;
}
.gx-accordion-header:hover {
  background: var(--gx-primary-subtle) !important;
  color: var(--gx-primary) !important;
}
.gx-accordion-content {
  background: var(--gx-surface) !important; color: var(--gx-text) !important;
  border-color: var(--gx-border) !important;
}

/* Inputs & Form Elements */
.gx-input, .gx-select, .gx-textarea {
  border-radius: 9px !important;
  border-color: var(--gx-border) !important;
  background: var(--gx-surface) !important;
  color: var(--gx-text) !important;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
.gx-input:focus, .gx-select:focus, .gx-textarea:focus {
  border-color: var(--gx-primary) !important;
  box-shadow: 0 0 0 3px var(--gx-spotlight) !important;
  outline: none !important;
}

:focus-visible {
  outline: 2px solid var(--gx-primary) !important;
  outline-offset: 2px;
}
::selection {
  background: rgba(16, 185, 129, 0.25);
  color: inherit;
}

/* =========================================================================
   6. RESPONSIVE BREAKPOINTS
   ========================================================================= */
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
  *, *::before, *::after {
    scroll-behavior: auto !important;
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
}
"""
