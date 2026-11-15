from __future__ import annotations

from html import escape
import json
import math
import secrets
from urllib.parse import quote

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
    DiagramEdge,
    DiagramNode,
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
    TreeNode,
    TreeView,
    VirtualList,
)
from radui.core.registry import ComponentRegistry


BASE_CSS = """
:root {
  --gx-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --gx-font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  --gx-bg: #f8fafc;
  --gx-surface: #ffffff;
  --gx-surface-alt: #f1f5f9;
  --gx-text: #0f172a;
  --gx-text-muted: #64748b;
  --gx-border: #e2e8f0;
  --gx-border-strong: #cbd5e1;
  --gx-primary: #2563eb;
  --gx-primary-hover: #1d4ed8;
  --gx-primary-subtle: #eff6ff;
  --gx-success: #16a34a;
  --gx-success-subtle: #f0fdf4;
  --gx-warning: #d97706;
  --gx-warning-subtle: #fffbeb;
  --gx-danger: #dc2626;
  --gx-danger-subtle: #fef2f2;
  --gx-info: #0284c7;
  --gx-info-subtle: #f0f9ff;
  --gx-radius: 10px;
  --gx-shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
  --gx-shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1);
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --gx-bg: #090d16;
    --gx-surface: #111827;
    --gx-surface-alt: #1f2937;
    --gx-text: #f8fafc;
    --gx-text-muted: #94a3b8;
    --gx-border: #1e293b;
    --gx-border-strong: #334155;
    --gx-primary: #3b82f6;
    --gx-primary-hover: #60a5fa;
    --gx-primary-subtle: #1e293b;
    --gx-success-subtle: #064e3b;
    --gx-warning-subtle: #78350f;
    --gx-danger-subtle: #7f1d1d;
    --gx-info-subtle: #0c4a6e;
    --gx-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.5);
  }
}

:root[data-theme="dark"] {
  --gx-bg: #090d16;
  --gx-surface: #111827;
  --gx-surface-alt: #1f2937;
  --gx-text: #f8fafc;
  --gx-text-muted: #94a3b8;
  --gx-border: #1e293b;
  --gx-border-strong: #334155;
  --gx-primary: #3b82f6;
  --gx-primary-hover: #60a5fa;
  --gx-primary-subtle: #1e293b;
  --gx-success-subtle: #064e3b;
  --gx-warning-subtle: #78350f;
  --gx-danger-subtle: #7f1d1d;
  --gx-info-subtle: #0c4a6e;
  --gx-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.5);
}

* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--gx-font);
  background-color: var(--gx-bg);
  color: var(--gx-text);
  line-height: 1.5;
  transition: background-color .2s ease, color .2s ease;
}

.gx-shell { width: min(1080px, calc(100% - 32px)); margin: 32px auto 80px auto; }
.gx-column { display: flex; flex-direction: column; }
.gx-row { display: flex; flex-wrap: wrap; align-items: center; }
.gx-grid { display: grid; width: 100%; }
.gx-spacer { width: 100%; flex-shrink: 0; }

.gx-card {
  padding: 24px;
  border: 1px solid var(--gx-border);
  border-radius: var(--gx-radius);
  background: var(--gx-surface);
  box-shadow: var(--gx-shadow);
  transition: transform .15s ease, box-shadow .15s ease;
}

.gx-text { line-height: 1.6; color: var(--gx-text); margin: 0; }
.gx-link { color: var(--gx-primary); text-decoration: none; font-weight: 500; }
.gx-link:hover { text-decoration: underline; color: var(--gx-primary-hover); }
.gx-divider { border: 0; border-top: 1px solid var(--gx-border); width: 100%; margin: 8px 0; }

.gx-badge {
  display: inline-flex; align-items: center; font-size: 0.75rem; font-weight: 600;
  padding: 3px 8px; border-radius: 9999px; text-transform: uppercase; letter-spacing: 0.05em;
}
.gx-badge-neutral { background: var(--gx-surface-alt); color: var(--gx-text-muted); }
.gx-badge-primary { background: var(--gx-primary-subtle); color: var(--gx-primary); }
.gx-badge-success { background: var(--gx-success-subtle); color: var(--gx-success); }
.gx-badge-warning { background: var(--gx-warning-subtle); color: var(--gx-warning); }
.gx-badge-danger { background: var(--gx-danger-subtle); color: var(--gx-danger); }
.gx-badge-info { background: var(--gx-info-subtle); color: var(--gx-info); }

.gx-callout {
  padding: 16px; border-radius: var(--gx-radius); border-left: 4px solid var(--gx-primary);
  background: var(--gx-surface); border: 1px solid var(--gx-border); border-left-width: 4px;
}
.gx-callout-info { border-left-color: var(--gx-info); background: var(--gx-info-subtle); }
.gx-callout-success { border-left-color: var(--gx-success); background: var(--gx-success-subtle); }
.gx-callout-warning { border-left-color: var(--gx-warning); background: var(--gx-warning-subtle); }
.gx-callout-danger { border-left-color: var(--gx-danger); background: var(--gx-danger-subtle); }
.gx-callout h4 { margin: 0 0 6px 0; font-size: 1rem; }
.gx-callout p { margin: 0; font-size: 0.92rem; }

.gx-form { display: flex; flex-direction: column; gap: 16px; }
.gx-field { display: flex; flex-direction: column; gap: 6px; }
.gx-field label, .gx-checkbox { font-size: .88rem; font-weight: 600; color: var(--gx-text); }
.gx-input, .gx-textarea, .gx-select {
  width: 100%; padding: 10px 14px; border: 1px solid var(--gx-border-strong);
  border-radius: var(--gx-radius); background: var(--gx-surface); color: var(--gx-text);
  font: inherit; font-size: .95rem; transition: border-color .15s ease, box-shadow .15s ease;
}
.gx-input:focus, .gx-textarea:focus, .gx-select:focus {
  outline: none; border-color: var(--gx-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}
.gx-checkbox { display: flex; gap: 10px; align-items: center; cursor: pointer; }
.gx-switch { display: inline-flex; align-items: center; gap: 10px; cursor: pointer; }
.gx-switch input { display: none; }
.gx-switch-slider {
  width: 40px; height: 22px; background-color: var(--gx-border-strong);
  border-radius: 9999px; position: relative; transition: .2s;
}
.gx-switch-slider::before {
  content: ""; position: absolute; height: 16px; width: 16px; left: 3px; bottom: 3px;
  background-color: white; border-radius: 50%; transition: .2s;
}
.gx-switch input:checked + .gx-switch-slider { background-color: var(--gx-primary); }
.gx-switch input:checked + .gx-switch-slider::before { transform: translateX(18px); }

.gx-button {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border: 0; border-radius: var(--gx-radius); padding: 10px 18px; font: inherit;
  font-weight: 600; cursor: pointer; transition: all .15s ease;
}
.gx-button-primary { background: var(--gx-primary); color: white; }
.gx-button-primary:hover { background: var(--gx-primary-hover); }
.gx-button-secondary { background: var(--gx-surface-alt); color: var(--gx-text); border: 1px solid var(--gx-border); }
.gx-button-secondary:hover { background: var(--gx-border); }
.gx-button-danger { background: var(--gx-danger); color: white; }
.gx-button-outline { background: transparent; color: var(--gx-primary); border: 1px solid var(--gx-primary); }
.gx-button:disabled { opacity: .6; cursor: wait; }

.gx-tabs-header { display: flex; border-bottom: 2px solid var(--gx-border); gap: 8px; margin-bottom: 16px; }
.gx-tab-btn {
  background: none; border: none; padding: 10px 16px; font-weight: 600; font-size: .95rem;
  color: var(--gx-text-muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px;
}
.gx-tab-btn.active { color: var(--gx-primary); border-bottom-color: var(--gx-primary); }
.gx-tab-pane { display: none; }
.gx-tab-pane.active { display: block; }

.gx-modal-backdrop {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5);
  display: none; align-items: center; justify-content: center; z-index: 1000;
}
.gx-modal-backdrop.open { display: flex; }
.gx-modal-box {
  background: var(--gx-surface); border-radius: var(--gx-radius); width: min(560px, 90%);
  padding: 24px; box-shadow: var(--gx-shadow-lg); border: 1px solid var(--gx-border);
}

.gx-metric {
  padding: 20px; background: var(--gx-surface); border-radius: var(--gx-radius);
  border: 1px solid var(--gx-border); box-shadow: var(--gx-shadow);
}
.gx-metric-title { font-size: .85rem; color: var(--gx-text-muted); text-transform: uppercase; font-weight: 600; }
.gx-metric-val { font-size: 2rem; font-weight: 700; color: var(--gx-text); margin: 6px 0; }
.gx-metric-foot { display: flex; align-items: center; gap: 8px; font-size: .85rem; }
.gx-trend-up { color: var(--gx-success); font-weight: 600; }
.gx-trend-down { color: var(--gx-danger); font-weight: 600; }
.gx-trend-neutral { color: var(--gx-text-muted); }

.gx-table-wrap { overflow-x: auto; border: 1px solid var(--gx-border); border-radius: var(--gx-radius); }
.gx-table { width: 100%; border-collapse: collapse; text-align: left; font-size: .92rem; }
.gx-table th { background: var(--gx-surface-alt); padding: 12px 16px; border-bottom: 1px solid var(--gx-border); font-weight: 600; }
.gx-table td { padding: 12px 16px; border-bottom: 1px solid var(--gx-border); }
.gx-table.striped tr:nth-child(even) td { background: var(--gx-surface-alt); }

.gx-plot-card { background: var(--gx-surface); border: 1px solid var(--gx-border); border-radius: var(--gx-radius); padding: 20px; }
.gx-plot-title { font-size: 1.05rem; font-weight: 600; margin-bottom: 12px; }

.gx-chat-box {
  border: 1px solid var(--gx-border); border-radius: var(--gx-radius);
  background: var(--gx-surface); display: flex; flex-direction: column; overflow: hidden;
}
.gx-chat-header { padding: 14px 18px; border-bottom: 1px solid var(--gx-border); font-weight: 600; background: var(--gx-surface-alt); }
.gx-chat-messages { padding: 18px; display: flex; flex-direction: column; gap: 14px; max-height: 480px; overflow-y: auto; }
.gx-chat-msg { display: flex; flex-direction: column; max-width: 82%; padding: 12px 16px; border-radius: 12px; font-size: .95rem; }
.gx-chat-user { align-self: flex-end; background: var(--gx-primary); color: white; border-bottom-right-radius: 2px; }
.gx-chat-assistant { align-self: flex-start; background: var(--gx-surface-alt); color: var(--gx-text); border-bottom-left-radius: 2px; border: 1px solid var(--gx-border); }
.gx-chat-citations { margin-top: 8px; font-size: 0.8rem; color: var(--gx-text-muted); border-top: 1px solid var(--gx-border); padding-top: 6px; }

.gx-stream-cursor::after { content: "▋"; animation: gx-blink 1s infinite; color: var(--gx-primary); }
@keyframes gx-blink { 0%, 50% { opacity: 1; } 50.1%, 100% { opacity: 0; } }

.gx-action-card { border: 2px solid var(--gx-primary); border-radius: var(--gx-radius); padding: 18px; background: var(--gx-primary-subtle); }
.gx-timeline { border-left: 2px solid var(--gx-border-strong); margin-left: 12px; padding-left: 18px; display: flex; flex-direction: column; gap: 14px; }
.gx-timeline-item { position: relative; }
.gx-timeline-dot { position: absolute; left: -25px; top: 3px; width: 12px; height: 12px; border-radius: 50%; background: var(--gx-primary); }

.gx-job-panel { border: 1px solid var(--gx-border); border-radius: var(--gx-radius); padding: 18px; background: var(--gx-surface); }
.gx-job-top { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.gx-job-status { font-size: .88rem; font-weight: 600; }
.gx-job-progress { width: 100%; height: 10px; margin: 12px 0; accent-color: var(--gx-primary); }
.gx-job-message { color: var(--gx-text-muted); font-size: .92rem; }
.gx-job-result { white-space: pre-wrap; overflow-wrap: anywhere; background: var(--gx-surface-alt); padding: 12px; border-radius: 8px; font-family: var(--gx-font-mono); font-size: .88rem; }
.gx-error { color: var(--gx-danger); min-height: 1.2em; font-size: .9rem; margin-top: 6px; }

/* Inspector floating badge and drawer */
#gx-inspect-badge {
  position: fixed; bottom: 16px; right: 16px; background: #0f172a; color: #38bdf8;
  font-family: var(--gx-font-mono); font-size: 11px; font-weight: 700; padding: 6px 12px;
  border-radius: 9999px; cursor: pointer; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 9999;
  display: flex; align-items: center; gap: 6px; border: 1px solid #334155;
}
#gx-inspect-drawer {
  position: fixed; bottom: 0; left: 0; width: 100%; height: 380px; background: #0f172a;
  color: #e2e8f0; font-family: var(--gx-font-mono); z-index: 9998; display: none;
  flex-direction: column; border-top: 2px solid #38bdf8; box-shadow: 0 -8px 24px rgba(0,0,0,0.4);
}
#gx-inspect-drawer.open { display: flex; }
.gx-insp-tabs { display: flex; background: #1e293b; border-bottom: 1px solid #334155; overflow-x: auto; }
.gx-insp-tab { padding: 8px 14px; cursor: pointer; font-size: 12px; font-weight: 600; color: #94a3b8; border: none; background: none; }
.gx-insp-tab.active { color: #38bdf8; border-bottom: 2px solid #38bdf8; }
.gx-insp-body { flex: 1; padding: 14px; overflow-y: auto; font-size: 12px; line-height: 1.6; }

/* Diagrams and Flowcharts */
.gx-diagram-container {
  width: 100%;
  border: 1px solid var(--gx-border);
  border-radius: var(--gx-radius);
  background-color: var(--gx-surface);
  background-image: radial-gradient(var(--gx-border-strong) 1px, transparent 1px);
  background-size: 20px 20px;
  overflow: auto;
  position: relative;
  box-shadow: var(--gx-shadow);
}
.gx-diagram-svg {
  display: block;
  width: 100%;
  height: 100%;
}
.gx-diagram-node {
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), filter 0.2s ease;
  user-select: none;
}
.gx-diagram-node:hover {
  filter: drop-shadow(0 6px 12px rgba(0,0,0,0.15));
}
.gx-diagram-node.clickable {
  cursor: pointer;
}
.gx-diagram-edge {
  fill: none;
  stroke: var(--gx-border-strong);
  stroke-width: 2;
  transition: stroke 0.2s ease;
}
.gx-diagram-edge:hover {
  stroke: var(--gx-primary);
  stroke-width: 2.5;
}
.gx-diagram-edge-animated {
  stroke-dasharray: 6 4;
  animation: gx-diagram-flow 1.2s linear infinite;
}
@keyframes gx-diagram-flow {
  from { stroke-dashoffset: 20; }
  to { stroke-dashoffset: 0; }
}

/* CodeBlock */
.gx-code-container {
  border: 1px solid var(--gx-border);
  border-radius: var(--gx-radius);
  background: var(--gx-surface);
  overflow: hidden;
  box-shadow: var(--gx-shadow);
  margin: 8px 0;
}
.gx-code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--gx-surface-alt);
  border-bottom: 1px solid var(--gx-border);
  font-size: 0.82rem;
  font-family: var(--gx-font-mono);
  color: var(--gx-text-muted);
}
.gx-code-copy-btn {
  background: transparent;
  border: 1px solid var(--gx-border);
  border-radius: 4px;
  padding: 3px 8px;
  font-size: 0.75rem;
  color: var(--gx-text);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: background 0.15s;
}
.gx-code-copy-btn:hover {
  background: var(--gx-border);
}
.gx-code-body {
  margin: 0;
  padding: 14px;
  font-family: var(--gx-font-mono);
  font-size: 0.88rem;
  line-height: 1.6;
  overflow-x: auto;
  white-space: pre;
}

/* TreeView */
.gx-tree-container {
  border: 1px solid var(--gx-border);
  border-radius: var(--gx-radius);
  background: var(--gx-surface);
  padding: 12px;
  box-shadow: var(--gx-shadow);
  font-family: var(--gx-font);
}
.gx-tree-list {
  list-style: none;
  margin: 0;
  padding-left: 0;
}
.gx-tree-item {
  margin: 2px 0;
}
.gx-tree-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.92rem;
  transition: background 0.12s ease;
}
.gx-tree-row:hover {
  background: var(--gx-surface-alt);
}
.gx-tree-row.selected {
  background: var(--gx-primary-subtle);
  color: var(--gx-primary);
  font-weight: 600;
}
.gx-tree-caret {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  cursor: pointer;
  color: var(--gx-text-muted);
  transition: transform 0.15s ease;
  user-select: none;
}
.gx-tree-caret.expanded {
  transform: rotate(90deg);
}
.gx-tree-nested {
  list-style: none;
  margin: 0;
  padding-left: 20px;
  display: none;
}
.gx-tree-nested.open {
  display: block;
}

/* DataGrid */
.gx-grid-card {
  border: 1px solid var(--gx-border);
  border-radius: var(--gx-radius);
  background: var(--gx-surface);
  overflow: hidden;
  box-shadow: var(--gx-shadow);
}
.gx-grid-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--gx-surface-alt);
  border-bottom: 1px solid var(--gx-border);
  gap: 12px;
}
.gx-grid-search-input {
  max-width: 280px;
  padding: 6px 12px;
  border: 1px solid var(--gx-border-strong);
  border-radius: 6px;
  background: var(--gx-surface);
  color: var(--gx-text);
  font-size: 0.88rem;
  outline: none;
}
.gx-grid-search-input:focus {
  border-color: var(--gx-primary);
}
.gx-grid-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--gx-surface-alt);
  border-top: 1px solid var(--gx-border);
  font-size: 0.85rem;
  color: var(--gx-text-muted);
}
.gx-grid-pagination {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gx-grid-page-btn {
  padding: 4px 10px;
  border: 1px solid var(--gx-border);
  border-radius: 4px;
  background: var(--gx-surface);
  color: var(--gx-text);
  cursor: pointer;
  font-size: 0.82rem;
}
.gx-grid-page-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* GenerativeSlot */
.gx-generative-slot {
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* Motion, Micro-interactions and Accessibility */
.gx-button {
  transition: transform 0.12s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.12s ease, background-color 0.12s ease;
  position: relative;
  overflow: hidden;
}
.gx-button:active {
  transform: scale(0.97);
}
.gx-card {
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s ease;
}

/* 3D Flip Card Architecture */
.gx-flip-scene {
  perspective: 1200px;
  width: 100%;
  margin-bottom: 8px;
}
.gx-flip-card {
  position: relative;
  width: 100%;
  min-height: 280px;
  transform-style: preserve-3d;
  transition: transform 0.65s cubic-bezier(0.23, 1, 0.32, 1), box-shadow 0.3s ease;
  border-radius: var(--gx-radius);
  cursor: pointer;
}
.gx-flip-card.is-flipped {
  transform: rotateY(180deg);
}
.gx-flip-front,
.gx-flip-back {
  width: 100%;
  height: 100%;
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
  border-radius: var(--gx-radius);
  box-sizing: border-box;
}
.gx-flip-front {
  position: relative;
  transform: rotateY(0deg);
  z-index: 2;
}
.gx-flip-back {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  transform: rotateY(180deg);
  background: var(--gx-surface);
  border: 1px solid var(--gx-primary);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.12);
  padding: 24px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  z-index: 1;
}
.gx-flip-badge-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.76rem;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--gx-surface-alt);
  color: var(--gx-text);
  border: 1px solid var(--gx-border);
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
}
.gx-flip-badge-pill:hover {
  background: var(--gx-primary);
  color: #ffffff;
  border-color: var(--gx-primary);
  transform: scale(1.04);
}
.gx-flip-back-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--gx-border);
  padding-bottom: 8px;
}
.gx-btn-copy-code {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 0.78rem;
  font-weight: 600;
  border: 1px solid var(--gx-border);
  background: var(--gx-surface-alt);
  color: var(--gx-text);
  cursor: pointer;
  transition: all 0.2s ease;
}
.gx-btn-copy-code:hover {
  background: var(--gx-primary);
  color: #ffffff;
  border-color: var(--gx-primary);
}

/* Continuous Reading Navigation */
.gx-continuous-chapter {
  margin-top: 48px;
  padding-top: 36px;
  border-top: 2px dashed var(--gx-border);
  position: relative;
  animation: gx-fade-in 0.4s ease forwards;
}
@keyframes gx-fade-in {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.gx-chapter-divider {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 32px;
  padding: 20px 24px;
  background: linear-gradient(135deg, var(--gx-surface-alt) 0%, var(--gx-surface) 100%);
  border-left: 4px solid var(--gx-primary);
  border-radius: var(--gx-radius);
  box-shadow: var(--gx-shadow);
}
.gx-chapter-tag {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--gx-primary);
}
.gx-chapter-divider-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin: 0;
  color: var(--gx-text);
}
.gx-chapter-divider-sub {
  font-size: 0.88rem;
  margin: 0;
  color: var(--gx-text-muted);
}
.gx-chapter-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  margin: 32px 0;
  background: var(--gx-surface-alt);
  border: 1px dashed var(--gx-primary);
  border-radius: var(--gx-radius);
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--gx-text);
}
.gx-reading-pill {
  position: fixed;
  bottom: 24px;
  right: 28px;
  background: var(--gx-surface);
  color: var(--gx-text);
  border: 1px solid var(--gx-border);
  border-radius: 999px;
  padding: 8px 18px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 0.82rem;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: 999;
  backdrop-filter: blur(8px);
  transition: all 0.25s ease;
}
.gx-reading-pill:hover {
  border-color: var(--gx-primary);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.18);
  transform: translateY(-2px);
}
.gx-reading-pill-top {
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--gx-surface-alt);
  border: 1px solid var(--gx-border);
  font-weight: 700;
  font-size: 0.74rem;
}
.gx-reading-pill-top:hover {
  background: var(--gx-primary);
  color: #fff;
}
#component-chips-grid {
  max-height: 240px;
  overflow-y: auto;
  padding: 4px;
}

[data-gx-hover]:hover {
  cursor: pointer;
}
.gx-optimistic-pending {
  opacity: 0.65;
  pointer-events: none;
  filter: grayscale(20%);
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
}

/* Responsive Grid Breakpoints */
@media (min-width: 640px) {
  .gx-grid-responsive { grid-template-columns: repeat(var(--gx-cols-sm, 1), 1fr) !important; }
}
@media (min-width: 768px) {
  .gx-grid-responsive { grid-template-columns: repeat(var(--gx-cols-md, var(--gx-cols-sm, 2)), 1fr) !important; }
}
@media (min-width: 1024px) {
  .gx-grid-responsive { grid-template-columns: repeat(var(--gx-cols-lg, var(--gx-cols-md, 3)), 1fr) !important; }
}
@media (min-width: 1280px) {
  .gx-grid-responsive { grid-template-columns: repeat(var(--gx-cols-xl, var(--gx-cols-lg, 4)), 1fr) !important; }
}

/* Skeleton & Shimmer */
.gx-skeleton {
  background: var(--gx-surface-alt);
  border-radius: var(--gx-radius);
  display: block;
}
.gx-skeleton-circle { border-radius: 50%; }
.gx-skeleton-text { border-radius: 4px; }
.gx-skeleton-shimmer {
  background: linear-gradient(90deg, var(--gx-surface-alt) 25%, var(--gx-border) 50%, var(--gx-surface-alt) 75%);
  background-size: 200% 100%;
  animation: gx-shimmer 1.5s infinite;
}
@keyframes gx-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* Empty State */
.gx-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  text-align: center;
  background: var(--gx-surface);
  border: 1px dashed var(--gx-border-strong);
  border-radius: var(--gx-radius);
}
.gx-empty-icon { font-size: 2.5rem; margin-bottom: 10px; }
.gx-empty-title { margin: 0 0 6px 0; font-size: 1.1rem; font-weight: 600; color: var(--gx-text); }
.gx-empty-desc { margin: 0; font-size: 0.9rem; color: var(--gx-text-muted); }

/* File Upload */
.gx-file-upload { width: 100%; }
.gx-file-input { display: none; }
.gx-file-dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 28px 16px;
  border: 2px dashed var(--gx-border-strong);
  border-radius: var(--gx-radius);
  background: var(--gx-surface);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.gx-file-dropzone:hover, .gx-file-dropzone.dragover {
  border-color: var(--gx-primary);
  background: var(--gx-primary-subtle);
}
.gx-file-icon { font-size: 2rem; margin-bottom: 6px; }
.gx-file-label { font-weight: 500; font-size: 0.92rem; color: var(--gx-text); }
.gx-file-subtext { font-size: 0.8rem; color: var(--gx-text-muted); margin-top: 4px; }
.gx-file-list { margin-top: 8px; font-size: 0.85rem; color: var(--gx-text-muted); }

/* Virtual List */
.gx-virtual-list {
  border: 1px solid var(--gx-border);
  border-radius: var(--gx-radius);
  background: var(--gx-surface);
}
.gx-virtual-item {
  display: flex;
  align-items: center;
  padding: 0 16px;
  border-bottom: 1px solid var(--gx-border);
  box-sizing: border-box;
  font-size: 0.9rem;
}

/* Command Palette */
.gx-palette-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
  display: none;
  align-items: flex-start;
  justify-content: center;
  padding-top: 14vh;
  z-index: 9999;
}
.gx-palette-backdrop.open { display: flex; }
.gx-palette-dialog {
  width: 100%;
  max-width: 580px;
  background: var(--gx-surface);
  border: 1px solid var(--gx-border);
  border-radius: 12px;
  box-shadow: 0 20px 45px -10px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}
.gx-palette-header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--gx-border);
  gap: 10px;
}
.gx-palette-input {
  flex: 1;
  border: none;
  background: transparent;
  font-size: 1.05rem;
  color: var(--gx-text);
  outline: none;
}
.gx-palette-list {
  max-height: 320px;
  overflow-y: auto;
  list-style: none;
  margin: 0;
  padding: 8px;
}
.gx-palette-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.92rem;
  color: var(--gx-text);
  transition: background 0.1s ease;
}
.gx-palette-item:hover, .gx-palette-item.selected {
  background: var(--gx-primary-subtle);
  color: var(--gx-primary);
}
.gx-palette-badge {
  font-size: 0.75rem;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--gx-surface-alt);
  color: var(--gx-text-muted);
}

/* Error Boundary */
.gx-error-boundary {
  border: 1px solid #ef4444;
  background: rgba(239, 68, 68, 0.08);
  border-radius: var(--gx-radius);
  padding: 16px;
  color: #ef4444;
  margin: 8px 0;
}
.gx-error-title {
  font-weight: 700;
  font-size: 0.95rem;
  margin-bottom: 6px;
}
.gx-error-message {
  font-size: 0.85rem;
  margin: 0 0 10px 0;
  opacity: 0.9;
}

/* Offline & Reconnection Banner */
.gx-connection-banner {
  position: fixed;
  bottom: 20px;
  right: 20px;
  background: #ef4444;
  color: #ffffff;
  padding: 8px 16px;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  box-shadow: 0 10px 25px rgba(0,0,0,0.3);
  display: none;
  z-index: 10000;
}
.gx-connection-banner.visible {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Toast Notifications */
.gx-toast-container {
  position: fixed;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
  max-width: 420px;
  width: calc(100% - 32px);
}
.gx-toast-top-right { top: 20px; right: 20px; }
.gx-toast-top-left { top: 20px; left: 20px; }
.gx-toast-bottom-right { bottom: 20px; right: 20px; }
.gx-toast-bottom-left { bottom: 20px; left: 20px; }
.gx-toast-top-center { top: 20px; left: 50%; transform: translateX(-50%); }
.gx-toast-bottom-center { bottom: 20px; left: 50%; transform: translateX(-50%); }

.gx-toast {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 14px 16px;
  border-radius: var(--gx-radius);
  background: var(--gx-surface);
  border: 1px solid var(--gx-border);
  box-shadow: var(--gx-shadow-lg);
  font-size: 0.92rem;
  transition: transform 0.25s ease, opacity 0.25s ease;
  animation: gx-toast-in 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes gx-toast-in {
  from { opacity: 0; transform: translateY(-10px) scale(0.96); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.gx-toast-info { border-left: 4px solid var(--gx-info); }
.gx-toast-success { border-left: 4px solid var(--gx-success); }
.gx-toast-warning { border-left: 4px solid var(--gx-warning); }
.gx-toast-danger { border-left: 4px solid var(--gx-danger); }
.gx-toast-title { font-weight: 600; margin-bottom: 2px; }
.gx-toast-msg { color: var(--gx-text); }
.gx-toast-close { background: none; border: none; cursor: pointer; color: var(--gx-text-muted); font-size: 1rem; padding: 0 4px; margin-left: 12px; }

/* Tooltip */
.gx-tooltip-wrapper { position: relative; display: inline-flex; }
.gx-tooltip-content {
  position: absolute;
  background: #0f172a;
  color: #f8fafc;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s ease, transform 0.15s ease;
  z-index: 1000;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
}
.gx-tooltip-top { bottom: 100%; left: 50%; transform: translate(-50%, -6px); }
.gx-tooltip-bottom { top: 100%; left: 50%; transform: translate(-50%, 6px); }
.gx-tooltip-left { right: 100%; top: 50%; transform: translate(-6px, -50%); }
.gx-tooltip-right { left: 100%; top: 50%; transform: translate(6px, -50%); }
.gx-tooltip-wrapper:hover .gx-tooltip-content,
.gx-tooltip-wrapper:focus-within .gx-tooltip-content {
  opacity: 1;
}

/* Popover */
.gx-popover { position: relative; display: inline-block; }
.gx-popover summary { list-style: none; outline: none; cursor: pointer; }
.gx-popover summary::-webkit-details-marker { display: none; }
.gx-popover-panel {
  position: absolute;
  background: var(--gx-surface);
  border: 1px solid var(--gx-border);
  border-radius: var(--gx-radius);
  box-shadow: var(--gx-shadow-lg);
  padding: 16px;
  min-width: 240px;
  max-width: 380px;
  z-index: 950;
  margin-top: 8px;
}
.gx-popover-top { bottom: 100%; margin-bottom: 8px; margin-top: 0; }
.gx-popover-right { left: 100%; top: 0; margin-left: 8px; margin-top: 0; }
.gx-popover-left { right: 100%; top: 0; margin-right: 8px; margin-top: 0; }
.gx-popover-header { font-weight: 600; margin-bottom: 8px; border-bottom: 1px solid var(--gx-border); padding-bottom: 6px; }

/* Accordion */
.gx-accordion { display: flex; flex-direction: column; border: 1px solid var(--gx-border); border-radius: var(--gx-radius); overflow: hidden; }
.gx-accordion-item { border-bottom: 1px solid var(--gx-border); }
.gx-accordion-item:last-child { border-bottom: none; }
.gx-accordion-header {
  padding: 14px 18px;
  font-weight: 600;
  font-size: 0.95rem;
  background: var(--gx-surface);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
  list-style: none;
}
.gx-accordion-header::-webkit-details-marker { display: none; }
.gx-accordion-header:hover { background: var(--gx-surface-alt); }
.gx-accordion-arrow { font-size: 1.2rem; transition: transform 0.2s ease; color: var(--gx-text-muted); }
.gx-accordion-item[open] .gx-accordion-arrow { transform: rotate(90deg); }
.gx-accordion-content { padding: 16px 18px; background: var(--gx-surface); border-top: 1px solid var(--gx-border); }

/* Drawer */
.gx-drawer-backdrop {
  position: fixed; top: 0; left: 0; width: 100%; height: 100%;
  background: rgba(0,0,0,0.5); z-index: 1000; display: none;
}
.gx-drawer-backdrop.open { display: flex; }
.gx-drawer-panel {
  background: var(--gx-surface);
  box-shadow: var(--gx-shadow-lg);
  padding: 24px;
  overflow-y: auto;
  position: fixed;
  display: flex;
  flex-direction: column;
}
.gx-drawer-right .gx-drawer-panel { top: 0; right: 0; width: min(440px, 90%); height: 100%; }
.gx-drawer-left .gx-drawer-panel { top: 0; left: 0; width: min(440px, 90%); height: 100%; }
.gx-drawer-top .gx-drawer-panel { top: 0; left: 0; width: 100%; height: min(340px, 60%); }
.gx-drawer-bottom .gx-drawer-panel { bottom: 0; left: 0; width: 100%; height: min(340px, 60%); }
.gx-drawer-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--gx-border); padding-bottom: 12px; margin-bottom: 16px; }
.gx-drawer-close { background: none; border: none; font-size: 1.2rem; cursor: pointer; color: var(--gx-text-muted); }

/* Breadcrumb */
.gx-breadcrumb-list { display: flex; flex-wrap: wrap; align-items: center; list-style: none; margin: 0; padding: 0; gap: 8px; font-size: 0.9rem; }
.gx-breadcrumb-item { display: inline-flex; align-items: center; gap: 8px; }
.gx-breadcrumb-separator { color: var(--gx-text-muted); user-select: none; }
.gx-breadcrumb-active { color: var(--gx-text-muted); font-weight: 500; }

/* Pagination */
.gx-pagination { display: inline-flex; align-items: center; gap: 12px; }
.gx-pagination-info { font-size: 0.9rem; color: var(--gx-text-muted); }

/* Progress Bar */
.gx-progress-wrap { width: 100%; background: var(--gx-border); border-radius: 9999px; overflow: hidden; height: 12px; }
.gx-progress-bar { height: 100%; transition: width 0.3s ease; border-radius: 9999px; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; color: white; font-weight: 600; }
.gx-progress-primary { background: var(--gx-primary); }
.gx-progress-success { background: var(--gx-success); }
.gx-progress-warning { background: var(--gx-warning); }
.gx-progress-danger { background: var(--gx-danger); }
.gx-progress-info { background: var(--gx-info); }
.gx-progress-striped {
  background-image: linear-gradient(45deg, rgba(255,255,255,0.15) 25%, transparent 25%, transparent 50%, rgba(255,255,255,0.15) 50%, rgba(255,255,255,0.15) 75%, transparent 75%, transparent);
  background-size: 1rem 1rem;
}
.gx-progress-animated { animation: gx-progress-stripes 1s linear infinite; }
@keyframes gx-progress-stripes { from { background-position: 1rem 0; } to { background-position: 0 0; } }

/* Progress Circle */
.gx-progress-circle { display: inline-flex; position: relative; align-items: center; justify-content: center; }
.gx-progress-circle-text { position: absolute; font-size: 0.85rem; font-weight: 600; color: var(--gx-text); }

/* Avatar */
.gx-avatar {
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%; background: var(--gx-primary-subtle); color: var(--gx-primary);
  font-weight: 600; position: relative; overflow: visible; flex-shrink: 0; user-select: none;
}
.gx-avatar-sm { width: 32px; height: 32px; font-size: 0.75rem; }
.gx-avatar-md { width: 40px; height: 40px; font-size: 0.9rem; }
.gx-avatar-lg { width: 48px; height: 48px; font-size: 1.1rem; }
.gx-avatar-xl { width: 64px; height: 64px; font-size: 1.4rem; }
.gx-avatar img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
.gx-avatar-status {
  position: absolute; bottom: 0; right: 0; width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid var(--gx-surface);
}
.gx-avatar-status-online { background: #22c55e; }
.gx-avatar-status-busy { background: #ef4444; }
.gx-avatar-status-away { background: #eab308; }
.gx-avatar-status-offline { background: #94a3b8; }
.gx-avatar-group { display: inline-flex; align-items: center; }
.gx-avatar-group .gx-avatar { margin-left: -10px; border: 2px solid var(--gx-surface); }
.gx-avatar-group .gx-avatar:first-child { margin-left: 0; }

/* Slider */
.gx-slider-field { display: flex; flex-direction: column; gap: 8px; }
.gx-slider { width: 100%; accent-color: var(--gx-primary); cursor: pointer; }

/* Split Panel */
.gx-split-panel { display: flex; width: 100%; height: 100%; min-height: 240px; border: 1px solid var(--gx-border); border-radius: var(--gx-radius); overflow: hidden; }
.gx-split-horizontal { flex-direction: row; }
.gx-split-vertical { flex-direction: column; }
.gx-split-pane-1 { flex: 0 0 calc(var(--gx-split-ratio, 0.5) * 100%); overflow: auto; padding: 14px; }
.gx-split-pane-2 { flex: 1; overflow: auto; padding: 14px; }
.gx-split-handle { background: var(--gx-border-strong); user-select: none; flex-shrink: 0; }
.gx-split-horizontal > .gx-split-handle { width: 4px; cursor: col-resize; }
.gx-split-vertical > .gx-split-handle { height: 4px; cursor: row-resize; }

/* Dropdown Menu */
.gx-dropdown { position: relative; display: inline-block; }
.gx-dropdown summary { list-style: none; outline: none; cursor: pointer; }
.gx-dropdown summary::-webkit-details-marker { display: none; }
.gx-dropdown-menu {
  position: absolute; top: 100%; left: 0; margin-top: 6px;
  background: var(--gx-surface); border: 1px solid var(--gx-border);
  border-radius: var(--gx-radius); box-shadow: var(--gx-shadow-lg);
  min-width: 180px; padding: 6px; z-index: 900;
  display: flex; flex-direction: column; gap: 2px;
}
.gx-dropdown-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border-radius: 6px; text-decoration: none; color: var(--gx-text);
  font-size: 0.9rem; cursor: pointer; background: none; border: none; width: 100%; text-align: left;
  transition: background 0.12s ease;
}
.gx-dropdown-item:hover { background: var(--gx-surface-alt); }
.gx-dropdown-item-danger { color: var(--gx-danger); }
.gx-dropdown-item-danger:hover { background: var(--gx-danger-subtle); }

/* Kbd */
.gx-kbd { display: inline-flex; gap: 4px; font-family: var(--gx-font-mono); }
.gx-kbd kbd {
  background: var(--gx-surface-alt); border: 1px solid var(--gx-border-strong);
  border-radius: 4px; padding: 2px 6px; font-size: 0.78rem; box-shadow: 0 1px 0 var(--gx-border-strong);
}

/* Container & Stack */
.gx-container { width: 100%; box-sizing: border-box; }
.gx-stack { display: flex; }
.gx-stack-vertical { flex-direction: column; }
.gx-stack-horizontal { flex-direction: row; flex-wrap: wrap; }
.gx-stack-align-start { align-items: flex-start; }
.gx-stack-align-center { align-items: center; }
.gx-stack-align-end { align-items: flex-end; }
.gx-stack-align-stretch { align-items: stretch; }

/* Tag */
.gx-tag {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
  border-radius: 6px; font-size: 0.82rem; font-weight: 500;
}
.gx-tag-neutral { background: var(--gx-surface-alt); color: var(--gx-text); border: 1px solid var(--gx-border); }
.gx-tag-primary { background: var(--gx-primary-subtle); color: var(--gx-primary); }
.gx-tag-success { background: var(--gx-success-subtle); color: var(--gx-success); }
.gx-tag-warning { background: var(--gx-warning-subtle); color: var(--gx-warning); }
.gx-tag-danger { background: var(--gx-danger-subtle); color: var(--gx-danger); }
.gx-tag-info { background: var(--gx-info-subtle); color: var(--gx-info); }
.gx-tag-remove { background: none; border: none; cursor: pointer; color: inherit; padding: 0; font-size: 0.9rem; line-height: 1; }

/* Scroll Reveal */
[data-gx-reveal] {
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.6s cubic-bezier(0.16, 1, 0.3, 1), transform 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
[data-gx-reveal].gx-revealed {
  opacity: 1;
  transform: translateY(0);
}
""".strip()


STATIC_JS = r"""(() => {
  const announce = (message) => {
    const live = document.querySelector(".gx-aria-live");
    if (live) live.textContent = message;
  };

  const RADUI_COMPONENTS = {"column": {"example": "ui.column(\n    ui.heading(\"User Profile\", level=2),\n    ui.text(\"Manage account security and permissions.\"),\n    ui.button(\"Save Changes\", variant=\"primary\"),\n    gap=16,\n)", "domain": "Layout & Disclosure", "desc": "Vertical flexbox container arranging child components top-to-bottom."}, "row": {"example": "ui.row(\n    ui.button(\"Cancel\", variant=\"secondary\"),\n    ui.button(\"Submit\", variant=\"primary\"),\n    gap=12,\n)", "domain": "Layout & Disclosure", "desc": "Horizontal flexbox container with alignment, spacing, and wrapping controls."}, "grid": {"example": "ui.grid(\n    ui.card(ui.text(\"Metric A\")),\n    ui.card(ui.text(\"Metric B\")),\n    ui.card(ui.text(\"Metric C\")),\n    columns=3,\n    gap=16,\n)", "domain": "Layout & Disclosure", "desc": "Responsive CSS Grid container with column counts and responsive breakpoints."}, "container": {"example": "ui.container(\n    ui.heading(\"Dashboard Overview\", level=1),\n    ui.text(\"Welcome to RADUI portal.\"),\n    max_width=\"1200px\",\n)", "domain": "Layout & Disclosure", "desc": "Centered structural page wrapper with max-width and horizontal margins."}, "stack": {"example": "ui.stack(\n    ui.badge(\"Python\"),\n    ui.badge(\"ASGI\"),\n    ui.badge(\"SSE\"),\n    gap=8,\n)", "domain": "Layout & Disclosure", "desc": "Flexible wrapping layout for button strips, tag clouds, and badge rows."}, "split_panel": {"example": "ui.split_panel(\n    left=ui.card(ui.text(\"Navigation List\")),\n    right=ui.card(ui.text(\"Detail View\")),\n    initial_ratio=0.35,\n)", "domain": "Layout & Disclosure", "desc": "Resizable two-pane layout with draggable divider for master-detail views."}, "card": {"example": "ui.card(\n    ui.metric_card(\"Throughput\", \"1,420 rps\"),\n    title=\"API Cluster Status\",\n    subtitle=\"Updated 1s ago\",\n)", "domain": "Layout & Disclosure", "desc": "Structured visual container panel with optional title, description, and footer."}, "dynamic_card": {"example": "ui.dynamic_card(\"Live State Viewer\", bind=s_count,\n    ui.text(\"Content dynamically re-evaluates on state mutation.\")\n)", "domain": "Layout & Disclosure", "desc": "Reactive card container observing a StateRef and re-rendering on mutations."}, "accordion": {"example": "ui.accordion(\n    ui.accordion_item(\"Section 1\", ui.text(\"Content 1\"), open=True),\n    ui.accordion_item(\"Section 2\", ui.text(\"Content 2\")),\n)", "domain": "Layout & Disclosure", "desc": "Collapsible disclosure container organizing vertically stacked expandable panels."}, "accordion_item": {"example": "ui.accordion_item(\"How does SSR work?\",\n    ui.text(\"Initial requests render complete HTML in under 3.1ms.\"),\n    open=True\n)", "domain": "Layout & Disclosure", "desc": "Individual collapsible section with interactive header toggle and body."}, "spacer": {"example": "ui.spacer(size=24)", "domain": "Layout & Disclosure", "desc": "Explicit layout spacing element creating vertical or horizontal margin."}, "divider": {"example": "ui.divider(direction=\"horizontal\")", "domain": "Layout & Disclosure", "desc": "Structural visual separator rule segmenting sections within columns or rows."}, "heading": {"example": "ui.heading(\"Reactive Execution Lifecycle\", level=2)", "domain": "Typography & Code", "desc": "Semantic typography element rendering h1 through h6 with hierarchy validation."}, "text": {"example": "ui.text(\"Sub-DOM diffing completes in 0.168 ms.\", variant=\"lead\")", "domain": "Typography & Code", "desc": "Text display component supporting variants: body, caption, code, lead, muted."}, "callout": {"example": "ui.callout(\"Production Ready\", \"All 6 benchmark tiers verified.\", variant=\"success\")", "domain": "Typography & Code", "desc": "Highlighted informational callout banner with status semantics."}, "code_block": {"example": "ui.code_block(\"pip install radui\", language=\"bash\", copyable=True)", "domain": "Typography & Code", "desc": "Syntax-formatted monospace code block featuring line numbers and copy button."}, "kbd": {"example": "ui.row(ui.text(\"Press\"), ui.kbd(\"Ctrl\", \"K\"), ui.text(\"for Command Palette\"), gap=6)", "domain": "Typography & Code", "desc": "Keyboard shortcut indicator styled as hardware keycaps."}, "button": {"example": "ui.button(\"Deploy Cluster\", command=\"cluster.deploy\", variant=\"primary\")", "domain": "Action & Trigger", "desc": "Interactive trigger button dispatching a registered RADUI server command."}, "link": {"example": "ui.link(\"GitHub Repository\", \"https://github.com/flux-py/radui\", external=True)", "domain": "Action & Trigger", "desc": "Hyperlink strictly validated against secure http/https schemes to prevent XSS."}, "dropdown_menu": {"example": "ui.dropdown_menu(\"Export Options\", [\n    ui.dropdown_menu_item(\"CSV Export\", command=\"export.csv\"),\n    ui.dropdown_menu_item(\"JSON Export\", command=\"export.json\"),\n])", "domain": "Action & Trigger", "desc": "Floating contextual menu revealing actions on trigger click."}, "dropdown_menu_item": {"example": "ui.dropdown_menu_item(\"Purge Cache\", command=\"cache.purge\", danger=True)", "domain": "Action & Trigger", "desc": "Action item within a dropdown menu supporting command dispatch or navigation."}, "theme_toggle": {"example": "ui.theme_toggle(\"Toggle Theme\")", "domain": "Action & Trigger", "desc": "Interactive theme switcher with dark/light mode transitions and localStorage persistence."}, "form": {"example": "ui.form(\n    ui.input(\"Workspace Name\", bind=s_name),\n    ui.button(\"Create\", variant=\"primary\"),\n    command=\"workspace.create\",\n)", "domain": "Form & Data Input", "desc": "Declarative form container automatically injecting CSRF tokens and binding child inputs."}, "input": {"example": "ui.input(\"Email Address\", bind=s_email, type=\"email\", placeholder=\"developer@flux.py\")", "domain": "Form & Data Input", "desc": "Single-line text input bound to a reactive StateRef. Supports text, email, number, url."}, "textarea": {"example": "ui.textarea(\"Prompt Instructions\", bind=s_prompt, rows=5)", "domain": "Form & Data Input", "desc": "Multi-line text entry field bound to a reactive StateRef."}, "checkbox": {"example": "ui.checkbox(\"Enable Telemetry Tracing\", bind=s_telemetry)", "domain": "Form & Data Input", "desc": "Boolean toggle checkbox bound directly to a boolean StateRef."}, "switch": {"example": "ui.switch(\"Maintenance Mode\", bind=s_maintenance)", "domain": "Form & Data Input", "desc": "Hardware-styled toggle switch component bound to boolean reactive state."}, "radio_group": {"example": "ui.radio_group(\"Database Backend\", bind=s_db, options=[\"sqlite\", \"postgres\", \"redis\"])", "domain": "Form & Data Input", "desc": "Mutually-exclusive radio selection list bound to a string StateRef."}, "select": {"example": "ui.select(\"Cluster Region\", bind=s_region, options=[(\"us-east-1\", \"US East\"), (\"eu-west-1\", \"EU West\")])", "domain": "Form & Data Input", "desc": "Single-choice dropdown select control supporting label-value option tuples."}, "slider": {"example": "ui.slider(\"Concurrent Jobs\", bind=s_concurrency, min_value=1, max_value=64, step=1)", "domain": "Form & Data Input", "desc": "Continuous or stepped numeric range input with live value readouts."}, "date_picker": {"example": "ui.date_picker(\"Deployment Date\", bind=s_date)", "domain": "Form & Data Input", "desc": "Accessible calendar date picker input formatted to ISO-8601 (YYYY-MM-DD)."}, "time_picker": {"example": "ui.time_picker(\"Daily Backup Time\", bind=s_time)", "domain": "Form & Data Input", "desc": "Accessible time selection control formatted to 24-hour time (HH:MM)."}, "file_upload": {"example": "ui.file_upload(command=\"dataset.upload\", accept=\".csv,.json\", max_size_mb=25)", "domain": "Form & Data Input", "desc": "Drag-and-drop file upload zone with client-side size validation and file listing."}, "modal": {"example": "ui.modal(\"Restart Server\", ui.text(\"Are you sure you want to restart?\"), trigger_label=\"Restart\")", "domain": "Feedback & Overlays", "desc": "Accessible dialog overlay featuring focus-trapping, Escape key dismissal, and backdrop handling."}, "drawer": {"example": "ui.drawer(\"Node Inspector\", ui.text(\"Detailed trace records\"), trigger_label=\"Inspect\")", "domain": "Feedback & Overlays", "desc": "Off-canvas sliding drawer panel supporting placements: left, right, top, bottom."}, "popover": {"example": "ui.popover(\"Lease Fencing\", \"Guarantees split-brain prevention under partitions.\")", "domain": "Feedback & Overlays", "desc": "Contextual floating popover bubble anchored to a trigger button."}, "tooltip": {"example": "ui.tooltip(\"Copy command\", ui.button(\"Copy\"))", "domain": "Feedback & Overlays", "desc": "Lightweight hover/focus indicator providing descriptive text for buttons and icons."}, "toast": {"example": "ui.toast(\"State synchronized successfully\", variant=\"success\")", "domain": "Feedback & Overlays", "desc": "Individual transient toast alert message. Variants: info, success, warning, danger."}, "toast_container": {"example": "ui.toast_container(ui.toast(\"Cache purged\", variant=\"info\"))", "domain": "Feedback & Overlays", "desc": "Fixed viewport overlay positioning toast notifications."}, "error_boundary": {"example": "ui.error_boundary(failing_widget(), fallback_message=\"Live widget temporarily unavailable.\")", "domain": "Feedback & Overlays", "desc": "Catches unhandled rendering exceptions in isolated subtrees without breaking surrounding page."}, "breadcrumb": {"example": "ui.breadcrumb(\n    ui.breadcrumb_item(\"Home\", href=\"/\"),\n    ui.breadcrumb_item(\"Components\", href=\"/components\"),\n    ui.breadcrumb_item(\"Button\", active=True),\n)", "domain": "Navigation", "desc": "Breadcrumb navigation bar indicating hierarchical path position."}, "breadcrumb_item": {"example": "ui.breadcrumb_item(\"Architecture\", href=\"/architecture\")", "domain": "Navigation", "desc": "Individual breadcrumb entry supporting hyperlinked routes or active leaf nodes."}, "pagination": {"example": "ui.pagination(current_page=2, total_pages=8, command=\"records.page\")", "domain": "Navigation", "desc": "Page selector control with Previous, Next, and numeric page buttons dispatching commands."}, "tabs": {"example": "ui.tabs(\n    ui.tab_item(\"Python API\", ui.code_block(\"import radui as ui\")),\n    ui.tab_item(\"CLI\", ui.code_block(\"radui run\")),\n)", "domain": "Navigation", "desc": "Tabbed container switching visible child panels based on active tab selection."}, "tab_item": {"example": "ui.tab_item(\"Benchmarks\", ui.text(\"AST Construction: 0.039 ms\"))", "domain": "Navigation", "desc": "Single tab section holding child components associated with a tab header."}, "table": {"example": "ui.table(\n    headers=[\"Worker\", \"Status\", \"Latency\"],\n    rows=[[\"worker-1\", \"ACTIVE\", \"0.039ms\"], [\"worker-2\", \"ACTIVE\", \"0.042ms\"]],\n)", "domain": "Data Display & Tables", "desc": "Responsive data table with striped alternating rows and hover highlighting."}, "data_grid": {"example": "ui.data_grid(\n    headers=[\"Component\", \"Category\", \"AST Overhead\"],\n    rows=[[\"button\", \"Action\", \"0.015ms\"], [\"data_grid\", \"Data\", \"0.082ms\"]],\n    searchable=True,\n)", "domain": "Data Display & Tables", "desc": "Interactive data grid featuring instant search filtering, column sorting, and pagination."}, "virtual_list": {"example": "ui.virtual_list(items=[f\"Log Entry #{i}\" for i in range(10000)], item_height=36, viewport_height=300)", "domain": "Data Display & Tables", "desc": "Windowed virtualization list rendering massive datasets via CSS translateY spacers."}, "metric_card": {"example": "ui.metric_card(\"Reconciliation Time\", \"0.168 ms\", delta=\"-42% latency\")", "domain": "Data Display & Tables", "desc": "KPI metric card with formatted values, comparison deltas, and trend status indicators."}, "plot": {"example": "ui.plot(data=[{\"x\": \"T1\", \"y\": 0.039}, {\"x\": \"T2\", \"y\": 0.038}, {\"x\": \"T3\", \"y\": 3.037}], plot_type=\"bar\")", "domain": "Data Display & Tables", "desc": "Zero-dependency pure SVG chart generator rendering bar, line, and scatter series with zero JS."}, "badge": {"example": "ui.badge(\"v1.0.0 Production\", variant=\"primary\")", "domain": "Indicators & Avatars", "desc": "Compact status pill badge. Variants: primary, secondary, success, warning, danger."}, "tag": {"example": "ui.tag(\"Python 3.12\", variant=\"secondary\")", "domain": "Indicators & Avatars", "desc": "Categorization tag element with optional dismiss button dispatching a command."}, "progress_bar": {"example": "ui.progress_bar(value=85.0, variant=\"success\")", "domain": "Indicators & Avatars", "desc": "Horizontal progress bar indicator with optional striping and animations."}, "progress_circle": {"example": "ui.progress_circle(value=98.5, size=72, variant=\"primary\")", "domain": "Indicators & Avatars", "desc": "Radial SVG progress ring with centered percentage readout."}, "avatar": {"example": "ui.avatar(name=\"Core Maintainer\", size=\"md\", status=\"online\")", "domain": "Indicators & Avatars", "desc": "User profile avatar displaying image source or automatically derived initials."}, "avatar_group": {"example": "ui.avatar_group(\n    ui.avatar(name=\"Ada Lovelace\"),\n    ui.avatar(name=\"Alan Turing\"),\n    ui.avatar(name=\"Grace Hopper\"),\n    ui.avatar(name=\"Linus Torvalds\"),\n    max_visible=3,\n)", "domain": "Indicators & Avatars", "desc": "Overlapping avatar cluster automatically truncating excess users into an +N overflow badge."}, "skeleton": {"example": "ui.skeleton(shape=\"rect\", width=\"100%\", height=\"48px\")", "domain": "Indicators & Avatars", "desc": "Shimmering placeholder loader matching content shape (rect, circle, text)."}, "empty_state": {"example": "ui.empty_state(\"No Telemetry Found\", \"Trigger command to populate event logs.\", action=ui.button(\"Start Telemetry\"))", "domain": "Indicators & Avatars", "desc": "Zero-state presentation screen with heading, explanation, and action button."}, "diagram": {"example": "ui.diagram(\n    nodes=[\n        ui.diagram_node(\"n1\", \"Client DOM\", 50, 100),\n        ui.diagram_node(\"n2\", \"ASGI Engine\", 250, 100),\n    ],\n    edges=[ui.diagram_edge(\"n1\", \"n2\", label=\"POST /command\")],\n)", "domain": "Diagrams & Trees", "desc": "Pure SVG architecture diagram and flowchart canvas supporting interactive click commands."}, "tree_view": {"example": "ui.tree_view([\n    ui.tree_node(\"radui\", \"radui/\", children=[\n        ui.tree_node(\"core\", \"core/\"),\n        ui.tree_node(\"state\", \"state/\"),\n    ], expanded=True),\n])", "domain": "Diagrams & Trees", "desc": "Hierarchical tree explorer with collapsible branches, expandable carets, and selection listeners."}, "chat_view": {"example": "ui.chat_view(\n    ui.chat_message(\"Hello from RADUI AI agent!\", sender=\"assistant\"),\n    height=\"400px\",\n)", "domain": "AI Agent & Workflow", "desc": "Conversation message scrollbox featuring auto-scroll, message bubbles, and typing indicators."}, "chat_message": {"example": "ui.chat_message(\"Can you explain transactional outboxes?\", sender=\"user\")", "domain": "AI Agent & Workflow", "desc": "Individual chat message bubble supporting markdown, code formatting, and metadata."}, "chat_input": {"example": "ui.chat_input(command=\"agent.chat\", placeholder=\"Ask RADUI agent...\")", "domain": "AI Agent & Workflow", "desc": "Conversational input box supporting Enter-to-submit and file attachments."}, "streaming_text": {"example": "ui.streaming_text(\"Tokens arriving in 0.007ms chunks...\", is_streaming=True)", "domain": "AI Agent & Workflow", "desc": "Real-time token stream text box with animated blinking cursor."}, "action_card": {"example": "ui.action_card(\n    title=\"Authorize Tool Dispatch?\",\n    description=\"Execute query on production DB.\",\n    confirm_command=\"agent.approve\",\n    cancel_command=\"agent.reject\",\n)", "domain": "AI Agent & Workflow", "desc": "Human-in-the-loop (HITL) card enabling users to authorize or reject agent tool executions."}, "step_timeline": {"example": "ui.step_timeline([\n    {\"title\": \"Request Validated\", \"status\": \"completed\", \"latency\": \"0.12ms\"},\n    {\"title\": \"State Invalidation\", \"status\": \"completed\", \"latency\": \"0.168ms\"},\n    {\"title\": \"SSE Patch Emitted\", \"status\": \"active\", \"latency\": \"0.007ms\"},\n])", "domain": "AI Agent & Workflow", "desc": "Multi-step execution audit timeline displaying tool invocations, progress state, and latency."}, "generative_slot": {"example": "ui.generative_slot(id=\"dynamic_ai_slot\", component=ui.card(ui.text(\"Agent generated view\")))", "domain": "AI Agent & Workflow", "desc": "Dynamic DOM container allowing backend AI agents to swap or generate UI component trees."}, "job_panel": {"example": "ui.job_panel(job_id=\"export-daily-kpis\")", "domain": "AI Agent & Workflow", "desc": "Real-time background job monitor with progress bar, state badge, and cancellation trigger."}};

  document.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    const surface = event.target.closest(".gx-card, .gx-metric, .gx-code-block");
    if (!surface) return;
    const rect = surface.getBoundingClientRect();
    surface.style.setProperty("--gx-pointer-x", `${event.clientX - rect.left}px`);
    surface.style.setProperty("--gx-pointer-y", `${event.clientY - rect.top}px`);
  }, { passive: true });

  let currentCompName = "button";

  const updateLivePreview = (name) => {
    if (name) currentCompName = name;
    const previewContainer = document.getElementById("component-preview");
    if (!previewContainer) return;

    const labelInput = document.querySelector('input[name="prop.label"]') || document.querySelector('.gx-card input[type="text"]');
    const variantSelect = document.querySelector('select[name="prop.variant"]') || document.querySelector('.gx-card select');
    const disabledSwitch = document.querySelector('input[name="prop.disabled"]') || document.querySelector('.gx-card input[type="checkbox"]');

    const label = (labelInput && labelInput.value.trim()) ? labelInput.value.trim() : (
      currentCompName === "button" ? "Launch Cluster" :
      currentCompName === "badge" ? "v1.0.0 Verified" :
      currentCompName === "callout" ? "Production AST pipeline verified." :
      currentCompName === "slider" ? "Real-Time Value" :
      currentCompName.includes("metric") ? "0.039 ms" : `Demo ${currentCompName.replace('_', ' ')}`
    );
    const variant = variantSelect ? variantSelect.value : "primary";
    const disabled = disabledSwitch ? disabledSwitch.checked : false;
    const disabledAttr = disabled ? " disabled" : "";
    const disabledCode = disabled ? ", disabled=True" : "";

    let widgetHtml = "";
    let snippet = "";
    const compMeta = RADUI_COMPONENTS[currentCompName] || {};

    if (currentCompName === "button") {
      widgetHtml = `<button class="gx-button gx-button-${variant}" type="button"${disabledAttr} style="min-width:180px">${label}</button>`;
      snippet = `import radui as ui\n\nwidget = ui.button("${label}", variant="${variant}"${disabledCode})`;
    } else if (currentCompName === "badge") {
      widgetHtml = `<span class="gx-badge gx-badge-${variant}" style="font-size:0.95rem;padding:6px 14px">${label}</span>`;
      snippet = `import radui as ui\n\nwidget = ui.badge("${label}", variant="${variant}")`;
    } else if (currentCompName === "callout") {
      widgetHtml = `<div class="gx-callout gx-callout-${variant}" style="width:100%"><h4 style="margin:0 0 6px">Inspection Callout</h4><p class="gx-text" style="margin:0">${label}</p></div>`;
      snippet = `import radui as ui\n\nwidget = ui.callout("${label}", title="Inspection Callout", variant="${variant}")`;
    } else if (currentCompName === "metric_card" || currentCompName === "metric") {
      widgetHtml = `<div class="gx-metric" style="width:100%"><span class="gx-metric-label">Real-Time KPI</span><span class="gx-metric-value" style="display:block;margin:6px 0">${label}</span><span class="gx-metric-delta" style="color:var(--gx-primary)">+12% vs target</span></div>`;
      snippet = `import radui as ui\n\nwidget = ui.metric_card("Real-Time KPI", "${label}", delta="+12% vs target")`;
    } else if (currentCompName === "progress_bar" || currentCompName === "progress") {
      widgetHtml = `<div style="width:100%"><div style="display:flex;justify-content:space-between;margin-bottom:6px"><span class="gx-text">Task Progress (${label})</span><span class="gx-text" style="font-weight:700">75%</span></div><div class="gx-progress" style="background:var(--gx-surface-alt);border-radius:999px;height:12px;overflow:hidden"><div class="gx-progress-bar gx-progress-${variant}" style="width:75%;height:100%;border-radius:999px;background:var(--gx-primary);transition:width .3s ease"></div></div></div>`;
      snippet = `import radui as ui\n\nwidget = ui.progress_bar(value=75.0, variant="${variant}")`;
    } else if (currentCompName === "slider") {
      widgetHtml = `<div style="width:100%"><label class="gx-label" style="display:block;margin-bottom:8px">${label}: <span id="comp-slider-val" style="font-weight:700">65</span>%</label><input type="range" min="0" max="100" value="65" class="gx-slider" style="width:100%" oninput="document.getElementById('comp-slider-val').textContent=this.value"></div>`;
      snippet = `import radui as ui\n\nwidget = ui.slider("${label}", min=0, max=100, step=1, value=65)`;
    } else if (currentCompName === "switch") {
      widgetHtml = `<label class="gx-switch-label" style="display:flex;align-items:center;gap:12px;cursor:pointer"><input type="checkbox" checked class="gx-switch"><span class="gx-text" style="font-weight:600">${label}</span></label>`;
      snippet = `import radui as ui\n\nwidget = ui.switch("${label}", checked=True)`;
    } else if (currentCompName === "checkbox") {
      widgetHtml = `<label style="display:flex;align-items:center;gap:10px;cursor:pointer"><input type="checkbox" checked class="gx-checkbox"><span class="gx-text">${label}</span></label>`;
      snippet = `import radui as ui\n\nwidget = ui.checkbox("${label}", checked=True)`;
    } else if (currentCompName === "input") {
      widgetHtml = `<div style="width:100%"><label class="gx-label" style="display:block;margin-bottom:6px">${label}</label><input type="text" class="gx-input" value="user@domain.com" style="width:100%"></div>`;
      snippet = `import radui as ui\n\nwidget = ui.input("${label}", placeholder="Enter text...")`;
    } else if (currentCompName === "textarea") {
      widgetHtml = `<div style="width:100%"><label class="gx-label" style="display:block;margin-bottom:6px">${label}</label><textarea class="gx-textarea" rows="3" style="width:100%">System instructions and reactive prompt template...</textarea></div>`;
      snippet = `import radui as ui\n\nwidget = ui.textarea("${label}", rows=3)`;
    } else if (currentCompName === "modal") {
      widgetHtml = `<div><button class="gx-button gx-button-primary" type="button" onclick="const m=document.getElementById('demo-modal-dialog');m.style.display=m.style.display==='none'?'block':'none'">Open Interactive Modal</button><div id="demo-modal-dialog" style="display:none;margin-top:16px;padding:20px;background:var(--gx-surface);border:1px solid var(--gx-border);border-radius:var(--gx-radius);box-shadow:var(--gx-shadow)"><h4 style="margin:0 0 8px">${label}</h4><p class="gx-text">This modal overlay isolates focus and provides confirm/cancel actions.</p><button class="gx-button gx-button-secondary" type="button" onclick="document.getElementById('demo-modal-dialog').style.display='none'">Close</button></div></div>`;
      snippet = `import radui as ui\n\nwidget = ui.modal(ui.heading("${label}"), ui.text("Modal content"), title="${label}")`;
    } else if (currentCompName === "chat_view" || currentCompName === "chat_message") {
      widgetHtml = `<div class="gx-chat" style="width:100%;border:1px solid var(--gx-border);border-radius:var(--gx-radius);padding:14px;background:var(--gx-surface-alt)"><div class="gx-chat-msg gx-chat-assistant" style="background:var(--gx-surface);padding:8px 12px;border-radius:8px;margin-bottom:8px"><strong>Assistant:</strong> Connected to Model Context Protocol server.</div><div class="gx-chat-msg gx-chat-user" style="background:var(--gx-primary);color:#fff;padding:8px 12px;border-radius:8px;margin-bottom:8px;margin-left:auto;max-width:80%"><strong>User:</strong> ${label}</div><div class="gx-chat-msg gx-chat-assistant" style="background:var(--gx-surface);padding:8px 12px;border-radius:8px"><strong>Assistant:</strong> Executing reactive stream derivation...</div></div>`;
      snippet = compMeta.example || `import radui as ui\n\nwidget = ui.chat_view(\n    ui.chat_message("Connected to agent", role="assistant"),\n    ui.chat_message("${label}", role="user"),\n)`;
    } else if (currentCompName === "action_card") {
      widgetHtml = `<div class="gx-action-card" style="width:100%;padding:16px;border:1px solid var(--gx-primary);border-radius:var(--gx-radius);background:var(--gx-surface)"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><h4 style="margin:0">${label}</h4><span class="gx-badge gx-badge-warning">PENDING</span></div><p class="gx-text" style="margin:0 0 12px">Privileged gate for autonomous tool execution</p><div style="display:flex;gap:8px"><button class="gx-button gx-button-success" type="button" onclick="this.textContent='Approved ✓'">Approve</button><button class="gx-button gx-button-danger" type="button" onclick="this.textContent='Rejected ✕'">Reject</button></div></div>`;
      snippet = compMeta.example || `import radui as ui\n\nwidget = ui.action_card(title="${label}", approve_command="agent.approve")`;
    } else if (currentCompName === "tabs" || currentCompName === "tab_item") {
      widgetHtml = `<div class="gx-tabs" style="width:100%"><div class="gx-tabs-list" style="display:flex;gap:8px;border-bottom:1px solid var(--gx-border);padding-bottom:8px"><button class="gx-tab is-active" type="button" style="font-weight:700;color:var(--gx-primary);border-bottom:2px solid var(--gx-primary);padding:4px 12px;background:none;border-top:none;border-left:none;border-right:none">Overview</button><button class="gx-tab" type="button" style="padding:4px 12px;background:none;border:none;color:var(--gx-text-muted)">Analytics</button><button class="gx-tab" type="button" style="padding:4px 12px;background:none;border:none;color:var(--gx-text-muted)">Logs</button></div><div style="padding:14px 0"><p class="gx-text">${label}: Active Tab Workspace</p></div></div>`;
      snippet = compMeta.example || `import radui as ui\n\nwidget = ui.tabs(ui.tab_item("Overview", ui.text("${label}")))`;
    } else if (currentCompName === "avatar" || currentCompName === "avatar_group") {
      widgetHtml = `<div style="display:flex;align-items:center;gap:12px"><div class="gx-avatar" style="width:48px;height:48px;border-radius:50%;background:var(--gx-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:1.1rem;position:relative">RX<span style="position:absolute;bottom:0;right:0;width:12px;height:12px;border-radius:50%;background:#10b981;border:2px solid var(--gx-surface)"></span></div><div><strong style="display:block">${label}</strong><span style="color:var(--gx-text-muted);font-size:0.85rem">Active Session Contributor</span></div></div>`;
      snippet = compMeta.example || `import radui as ui\n\nwidget = ui.avatar(name="${label}", status="online")`;
    } else {
      widgetHtml = `<div style="width:100%;padding:18px;background:var(--gx-surface-alt);border:1px solid var(--gx-border);border-radius:var(--gx-radius)"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><strong style="font-size:1.05rem;color:var(--gx-text)">ui.${currentCompName}()</strong><span class="gx-badge gx-badge-primary">${compMeta.domain || "Primitive"}</span></div><p class="gx-text" style="margin:0 0 10px">${compMeta.desc || label}</p><div style="display:flex;gap:8px"><button class="gx-button gx-button-sm gx-button-${variant}" type="button"${disabledAttr}>Interactive Test</button><span class="gx-badge gx-badge-neutral">AST Verified</span></div></div>`;
      snippet = compMeta.example || `import radui as ui\n\nwidget = ui.${currentCompName}()`;
    }

    // Target the front face or preview card
    const target = previewContainer.querySelector('.gx-flip-front .gx-card') || previewContainer.querySelector('.gx-flip-front') || previewContainer;
    const existingHeader = target.querySelector('#comp-preview-heading')?.parentElement;
    if (existingHeader) {
      const heading = target.querySelector('#comp-preview-heading');
      if (heading) heading.textContent = `Live Preview: ui.${currentCompName}`;
      const rest = [...target.children].filter(c => c !== existingHeader && !c.classList?.contains('gx-flip-badge-pill'));
      rest.forEach(r => r.remove());
      const wrap = document.createElement("div");
      wrap.style.marginTop = "12px";
      wrap.innerHTML = widgetHtml;
      target.appendChild(wrap);
    } else {
      target.innerHTML = widgetHtml;
    }

    // Update code block below
    const pre = document.querySelector('#comp-code-block code') || document.querySelector('#docs-content .gx-code-container code');
    if (pre) {
      pre.textContent = snippet;
      const copy = pre.closest('.gx-code-container')?.querySelector('[data-gx-copy]');
      if (copy) copy.dataset.gxRawCode = snippet;
    }

    // Update backside of 3D flip card
    const flipCard = previewContainer.closest('.gx-flip-card') || previewContainer;
    const backCode = flipCard.querySelector('.gx-flip-back code');
    if (backCode) backCode.textContent = snippet;
  };

  const runDemoCommand = (command, source) => {
    const card = source.closest(".gx-card") || document;
    const metrics = [...card.querySelectorAll(".gx-metric-val, .gx-metric-value")];
    if (command === "demo.inc" || command === "demo.dec") {
      const metric = metrics[0];
      if (metric) {
        const current = Number(metric.textContent.trim()) || 0;
        const next = current + (command === "demo.inc" ? 1 : -1);
        metric.textContent = String(next);
        metric.animate?.([{ transform: "scale(.9)", opacity: .55 }, { transform: "scale(1)", opacity: 1 }], { duration: 220, easing: "ease-out" });
        announce(`Counter updated to ${next}`);
      }
    } else if (command === "calc.update") {
      const inputs = [...card.querySelectorAll('input[type="number"], input.gx-input')].filter(i => !isNaN(Number(i.value)) && i.value.trim() !== "");
      if (inputs.length >= 2 && metrics.length >= 3) {
        const p = Number(inputs[0].value) || 0;
        const t = Number(inputs[1].value) || 0;
        const tot = p * (1 + t);
        metrics[0].textContent = `$${p.toFixed(2)}`;
        metrics[1].textContent = `${(t * 100).toFixed(0)}%`;
        metrics[2].textContent = `$${tot.toFixed(2)}`;
        metrics[2].animate?.([{ transform: "scale(1.08)" }, { transform: "scale(1)" }], { duration: 240, easing: "ease-out" });
        announce(`Computed total updated to $${tot.toFixed(2)}`);
      }
    } else if (command === "job.start" || command === "job.cancel") {
      if (metrics[0]) metrics[0].textContent = command === "job.start" ? "RUNNING" : "CANCELLED";
      if (metrics[1]) metrics[1].textContent = command === "job.start" ? "45%" : "0%";
      const bar = card.querySelector(".gx-progress-bar");
      if (bar) bar.style.width = command === "job.start" ? "45%" : "0%";
      announce(command === "job.start" ? "Demo job started" : "Demo job cancelled");
    } else if (command === "agent.approve_demo") {
      const btn = source.closest("button") || source;
      btn.textContent = "Authorized ✓";
      btn.classList.add("gx-button-success");
      announce("Agent query authorized");
    } else if (command === "agent.reject_demo") {
      const btn = source.closest("button") || source;
      btn.textContent = "Declined ✕";
      announce("Agent query declined");
    } else if (command.startsWith("comp.select_")) {
      const name = command.replace("comp.select_", "");
      document.querySelectorAll('[data-gx-command^="comp.select_"]').forEach(button => {
        const isCurrent = button === source;
        button.classList.toggle("is-selected", isCurrent);
        button.classList.toggle("gx-button-primary", isCurrent);
        button.classList.toggle("gx-btn-primary", isCurrent);
        button.classList.toggle("gx-button-outline", !isCurrent);
        button.classList.toggle("gx-btn-outline", !isCurrent);
        button.setAttribute("aria-pressed", String(isCurrent));
      });
      const selection = document.getElementById("component-selection");
      if (selection) selection.textContent = `Selected: ui.${name}`;
      const descElem = document.getElementById("component-description-text");
      if (descElem && RADUI_COMPONENTS[name]) descElem.textContent = RADUI_COMPONENTS[name].desc;
      updateLivePreview(name);
      announce(`${name} primitive selected`);
    } else if (command === "comp.apply_props" || command === "comp.test_trigger") {
      updateLivePreview();
      announce("Applied inspector parameters to live component");
    } else {
      announce("Example interaction received");
    }
  };

  // 3D Flip Card System: seamlessly equips component cards with 3D flip animation & code
  const initFlipCards = (root = document) => {
    const cards = root.querySelectorAll('.gx-card, section.gx-card, [data-gx-flippable]');
    cards.forEach(card => {
      if (card._gxFlipInited) return;
      if (card.querySelector('form[data-gx-command="comp.apply_props"]') || card.querySelector('#comp-search-bar') || card.id === "docs-sidebar") {
        return;
      }
      card._gxFlipInited = true;

      let compCode = "";
      if (card.dataset.gxCode) {
        compCode = card.dataset.gxCode;
      } else if (card.id === "component-preview") {
        const meta = RADUI_COMPONENTS[currentCompName] || {};
        compCode = meta.example || `import radui as ui\n\nwidget = ui.${currentCompName}()`;
      } else {
        const parentGrid = card.closest('.gx-grid');
        const siblingCode = parentGrid ? parentGrid.querySelector('.gx-code-container code') : null;
        if (siblingCode) {
          compCode = siblingCode.textContent.trim();
        } else {
          const heading = card.querySelector('h1, h2, h3, h4, .gx-heading');
          const hText = (heading ? heading.textContent : "").toLowerCase();
          for (const [k, v] of Object.entries(RADUI_COMPONENTS)) {
            if (hText.includes(k.replace('_', ' ')) || hText.includes(k)) {
              compCode = v.example;
              break;
            }
          }
          if (!compCode) {
            if (card.querySelector('.gx-chat')) compCode = RADUI_COMPONENTS['chat_view']?.example || "";
            else if (card.querySelector('.gx-action-card')) compCode = RADUI_COMPONENTS['action_card']?.example || "";
            else if (card.querySelector('.gx-streaming')) compCode = RADUI_COMPONENTS['streaming_text']?.example || "";
            else if (card.querySelector('.gx-diagram')) compCode = RADUI_COMPONENTS['diagram']?.example || "";
            else if (card.querySelector('.gx-tree')) compCode = RADUI_COMPONENTS['tree_view']?.example || "";
            else if (card.querySelector('.gx-metric')) compCode = RADUI_COMPONENTS['metric_card']?.example || "";
            else if (card.querySelector('.gx-progress')) compCode = RADUI_COMPONENTS['progress_bar']?.example || "";
            else if (card.querySelector('.gx-accordion')) compCode = RADUI_COMPONENTS['accordion']?.example || "";
            else if (card.querySelector('.gx-tabs')) compCode = RADUI_COMPONENTS['tabs']?.example || "";
            else if (card.querySelector('.gx-slider')) compCode = RADUI_COMPONENTS['slider']?.example || "";
          }
        }
      }

      if (!compCode) return;

      const scene = document.createElement("div");
      scene.className = "gx-flip-scene";
      
      const flipCard = document.createElement("div");
      flipCard.className = "gx-flip-card";
      
      const front = document.createElement("div");
      front.className = "gx-flip-front";
      
      const frontBadge = document.createElement("button");
      frontBadge.type = "button";
      frontBadge.className = "gx-flip-badge-pill gx-flip-trigger";
      frontBadge.innerHTML = "⟳ Code";
      frontBadge.title = "Click to flip card and view RadUI implementation code";

      const back = document.createElement("div");
      back.className = "gx-flip-back";
      
      const backHeader = document.createElement("div");
      backHeader.className = "gx-flip-back-header";
      backHeader.innerHTML = `
        <span style="font-weight:700;font-size:0.88rem;color:var(--gx-text);display:flex;align-items:center;gap:6px;">
          <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--gx-primary);"></span>
          RadUI Implementation Code
        </span>
        <div style="display:flex;gap:8px;align-items:center;">
          <button type="button" class="gx-btn-copy-code" data-copy-flip>Copy Code</button>
          <button type="button" class="gx-flip-badge-pill gx-flip-back-btn" title="Flip back to interactive preview">⟲ Preview</button>
        </div>
      `;

      const codeWrap = document.createElement("div");
      codeWrap.className = "gx-code-container";
      codeWrap.style.flex = "1";
      codeWrap.style.overflow = "auto";
      const codePre = document.createElement("pre");
      codePre.className = "gx-code-block";
      codePre.style.height = "100%";
      codePre.style.margin = "0";
      const codeElem = document.createElement("code");
      codeElem.className = "language-python";
      codeElem.textContent = compCode;
      codePre.appendChild(codeElem);
      codeWrap.appendChild(codePre);

      back.appendChild(backHeader);
      back.appendChild(codeWrap);

      card.parentNode.insertBefore(scene, card);
      scene.appendChild(flipCard);
      flipCard.appendChild(front);
      flipCard.appendChild(back);
      front.appendChild(card);

      const cardHeader = card.querySelector('h1, h2, h3, h4, .gx-heading, .gx-card-header');
      if (cardHeader && cardHeader.parentElement) {
        const headerRow = cardHeader.closest('.gx-row') || cardHeader.parentElement;
        headerRow.style.display = "flex";
        headerRow.style.alignItems = "center";
        headerRow.style.justifyContent = "space-between";
        headerRow.appendChild(frontBadge);
      } else {
        front.appendChild(frontBadge);
        frontBadge.style.position = "absolute";
        frontBadge.style.top = "16px";
        frontBadge.style.right = "16px";
        frontBadge.style.zIndex = "10";
      }

      flipCard.addEventListener("click", (e) => {
        if (e && e.target.closest("button:not(.gx-flip-trigger):not(.gx-flip-back-btn), input, select, textarea, a, .gx-grid-pagination, [data-gx-copy]")) {
          return;
        }
        flipCard.classList.toggle("is-flipped");
        announce(flipCard.classList.contains("is-flipped") ? "Flipped to RadUI code" : "Flipped to live preview");
      });

      const copyBtn = back.querySelector('[data-copy-flip]');
      if (copyBtn) {
        copyBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          try {
            await navigator.clipboard.writeText(codeElem.textContent);
            const old = copyBtn.textContent;
            copyBtn.textContent = "Copied! ✓";
            setTimeout(() => { copyBtn.textContent = old; }, 1600);
            announce("Implementation code copied to clipboard");
          } catch (err) {
            announce("Clipboard copy failed");
          }
        });
      }
    });
  };

  // 68-Primitive Search & Domain Filter Toolbar
  const initComponentSearch = () => {
    const searchInput = document.getElementById("comp-search-bar");
    const countBadge = document.getElementById("comp-results-count");
    const chipsGrid = document.getElementById("component-chips-grid");
    const domainPills = document.getElementById("comp-domain-pills");
    if (!searchInput || !chipsGrid) return;

    let activeDomain = "all";

    const filterChips = () => {
      const query = (searchInput.value || "").trim().toLowerCase();
      const chips = [...chipsGrid.querySelectorAll('button')];
      let matched = 0;

      chips.forEach(chip => {
        const name = (chip.dataset.gxComp || chip.textContent).trim().toLowerCase();
        const meta = RADUI_COMPONENTS[name] || {};
        const domain = (meta.domain || chip.dataset.domain || "").toLowerCase();
        const desc = (meta.desc || chip.dataset.desc || "").toLowerCase();

        const matchesQuery = !query || name.includes(query) || domain.includes(query) || desc.includes(query);
        const matchesDomain = activeDomain === "all" || domain.includes(activeDomain);

        const visible = matchesQuery && matchesDomain;
        chip.style.display = visible ? "inline-flex" : "none";
        if (visible) matched++;
      });

      if (countBadge) {
        countBadge.textContent = `Showing ${matched} of 68 primitives`;
        countBadge.className = matched === 0 ? "gx-badge gx-badge-danger" : (matched < 68 ? "gx-badge gx-badge-warning" : "gx-badge gx-badge-primary");
      }
    };

    searchInput.addEventListener("input", filterChips);

    if (domainPills) {
      domainPills.addEventListener("click", (e) => {
        const btn = e.target.closest("button");
        if (!btn) return;
        e.preventDefault();
        const text = btn.textContent.toLowerCase();
        if (text.includes("all")) activeDomain = "all";
        else if (text.includes("layout")) activeDomain = "layout";
        else if (text.includes("form")) activeDomain = "form";
        else if (text.includes("action")) activeDomain = "action";
        else if (text.includes("data")) activeDomain = "data";
        else if (text.includes("feedback")) activeDomain = "feedback";
        else if (text.includes("navigation") || text.includes("nav")) activeDomain = "navigation";
        else if (text.includes("indicator")) activeDomain = "indicator";
        else if (text.includes("ai")) activeDomain = "ai";

        domainPills.querySelectorAll("button").forEach(b => {
          const isCurrent = b === btn;
          b.className = isCurrent ? "gx-button gx-button-primary" : "gx-button gx-button-outline";
        });
        filterChips();
      });
    }

    const flipToggleBtn = document.getElementById("comp-flip-toggle-btn");
    if (flipToggleBtn) {
      flipToggleBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const flipCard = flipToggleBtn.closest(".gx-flip-card") || document.getElementById("component-preview")?.closest(".gx-flip-card");
        if (flipCard) flipCard.classList.toggle("is-flipped");
      });
    }
  };

  // Seamless Continuous Reading & Scroll Navigation
  const DOCS_NAV_SEQUENCE = [
    { path: "index.html", title: "Overview", url: "index.html" },
    { path: "getting-started.html", title: "Getting Started with RADUI", url: "getting-started.html" },
    { path: "api-reference.html", title: "Python API Reference", url: "api-reference.html" },
    { path: "architecture.html", title: "RADUI System Architecture & Execution Lifecycle", url: "architecture.html" },
    { path: "components.html", title: "Interactive Component Explorer (68 Built-in Primitives)", url: "components.html" },
    { path: "components-layout.html", title: "Layout & Grid Architecture", url: "components-layout.html" },
    { path: "components-forms.html", title: "Forms, Form Validation & Reactive Input Controls", url: "components-forms.html" },
    { path: "components-data.html", title: "Data Display, DataGrids, Virtualized Lists & Vector Topology", url: "components-data.html" },
    { path: "components-feedback.html", title: "Feedback Overlays, Modals, Drawers & System Toasts", url: "components-feedback.html" },
    { path: "components-ai.html", title: "AI Agents, Streaming LLM Interfaces & Human-in-the-Loop Controls", url: "components-ai.html" },
    { path: "cli.html", title: "CLI & Toolchain Reference (45 Subcommands)", url: "cli.html" },
    { path: "cli-workflows.html", title: "Developer CLI Workflows, Scaffolding & CI/CD Pipelines", url: "cli-workflows.html" },
    { path: "state.html", title: "5-Tier Reactive State & Computed Signals", url: "state.html" },
    { path: "transport.html", title: "SSE Streaming & Sub-DOM Morphing Transport", url: "transport.html" },
    { path: "jobs.html", title: "Distributed Background Jobs & Lease Fencing", url: "jobs.html" },
    { path: "ai.html", title: "Autonomous AI Agents & Human-in-the-Loop Approvals", url: "ai.html" },
    { path: "adrs.html", title: "Architecture Decision Records (ADRs)", url: "adrs.html" }
  ];

  const initContinuousScroll = () => {
    const content = document.getElementById("docs-content");
    if (!content) return;

    const currentPath = window.location.pathname.split("/").filter(Boolean).pop() || "index.html";
    const normalizedCurrent = currentPath.endsWith(".html") ? currentPath : `${currentPath}.html`;
    
    let currentIdx = DOCS_NAV_SEQUENCE.findIndex(item => item.path === normalizedCurrent || item.path.replace(".html", "") === currentPath);
    if (currentIdx === -1) currentIdx = 0;

    const loadedChapters = new Set([DOCS_NAV_SEQUENCE[currentIdx].path]);
    let nextIdx = currentIdx + 1;
    let isLoading = false;

    let pill = document.querySelector(".gx-reading-pill");
    if (!pill) {
      pill = document.createElement("div");
      pill.className = "gx-reading-pill";
      pill.innerHTML = `
        <span style="font-size:1.05rem">📖</span>
        <span class="gx-reading-pill-text">Reading: <strong>${DOCS_NAV_SEQUENCE[currentIdx].title}</strong></span>
        <button type="button" class="gx-reading-pill-top" title="Scroll back to top">↑ Top</button>
      `;
      document.body.appendChild(pill);
      pill.querySelector(".gx-reading-pill-top").addEventListener("click", () => {
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }

    const updatePill = (title) => {
      const text = pill.querySelector(".gx-reading-pill-text strong");
      if (text) text.textContent = title;
    };

    const loadNextChapter = async () => {
      if (isLoading || nextIdx >= DOCS_NAV_SEQUENCE.length) return;
      const nextChapter = DOCS_NAV_SEQUENCE[nextIdx];
      if (loadedChapters.has(nextChapter.path)) {
        nextIdx++;
        return;
      }

      isLoading = true;
      const loadingElem = document.createElement("div");
      loadingElem.className = "gx-chapter-loading";
      loadingElem.innerHTML = `<span class="gx-spinner" style="display:inline-block;width:16px;height:16px;border:2px solid var(--gx-primary);border-top-color:transparent;border-radius:50%;animation:gx-spin .6s linear infinite"></span> Loading next chapter: <strong>${nextChapter.title}</strong>...`;
      content.appendChild(loadingElem);

      try {
        const res = await fetch(nextChapter.url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const htmlText = await res.text();
        const doc = new DOMParser().parseFromString(htmlText, "text/html");
        const fetchedContent = doc.getElementById("docs-content");

        if (fetchedContent) {
          loadedChapters.add(nextChapter.path);
          
          const section = document.createElement("article");
          section.className = "gx-continuous-chapter";
          section.id = `chapter-${nextChapter.path.replace(".html", "")}`;
          section.dataset.chapterUrl = nextChapter.url;
          section.dataset.chapterTitle = nextChapter.title;

          section.innerHTML = `
            <div class="gx-chapter-divider">
              <span class="gx-chapter-tag">Next Chapter (${nextIdx + 1}/${DOCS_NAV_SEQUENCE.length})</span>
              <h2 class="gx-chapter-divider-title">${nextChapter.title}</h2>
              <p class="gx-chapter-divider-sub">Seamless continuous reading • Scroll down or inspect primitives</p>
            </div>
            <div class="gx-chapter-body">
              ${fetchedContent.innerHTML}
            </div>
          `;

          loadingElem.remove();
          content.appendChild(section);
          nextIdx++;

          initGrids();
          initFlipCards(section);
          announce(`Loaded next chapter: ${nextChapter.title}`);
        } else {
          loadingElem.remove();
        }
      } catch (err) {
        loadingElem.innerHTML = `<span>Could not load next chapter automatically.</span> <a href="${nextChapter.url}" style="color:var(--gx-primary);text-decoration:underline">Click here to open ${nextChapter.title} →</a>`;
      } finally {
        isLoading = false;
      }
    };

    window.addEventListener("scroll", () => {
      const scrollPos = window.innerHeight + window.scrollY;
      const threshold = document.documentElement.scrollHeight - 600;
      if (scrollPos >= threshold) {
        loadNextChapter();
      }

      const chapters = [
        { elem: content.firstElementChild, url: DOCS_NAV_SEQUENCE[currentIdx].url, title: DOCS_NAV_SEQUENCE[currentIdx].title },
        ...[...document.querySelectorAll(".gx-continuous-chapter")].map(sec => ({
          elem: sec,
          url: sec.dataset.chapterUrl,
          title: sec.dataset.chapterTitle
        }))
      ];

      for (let i = chapters.length - 1; i >= 0; i--) {
        const ch = chapters[i];
        if (!ch.elem) continue;
        const rect = ch.elem.getBoundingClientRect();
        if (rect.top <= 200) {
          if (window.location.pathname.split("/").pop() !== ch.url) {
            try {
              history.replaceState(null, "", ch.url);
              document.title = `${ch.title} — RADUI Documentation`;
              updatePill(ch.title);

              document.querySelectorAll("#docs-sidebar a").forEach(a => {
                const href = a.getAttribute("href") || "";
                const matches = href === ch.url || href.endsWith("/" + ch.url);
                a.style.color = matches ? "var(--gx-primary)" : "";
                a.style.fontWeight = matches ? "700" : "";
              });
            } catch(e) {}
          }
          break;
        }
      }
    }, { passive: true });
  };

  document.addEventListener("input", (e) => {
    if (e.target.closest('form[data-gx-command="calc.update"]')) {
      const card = e.target.closest(".gx-card") || document;
      const inputs = [...card.querySelectorAll('input[type="number"], input.gx-input')].filter(i => !isNaN(Number(i.value)) && i.value.trim() !== "");
      const metrics = [...card.querySelectorAll(".gx-metric-val, .gx-metric-value")];
      if (inputs.length >= 2 && metrics.length >= 3) {
        const p = Number(inputs[0].value) || 0;
        const t = Number(inputs[1].value) || 0;
        const tot = p * (1 + t);
        metrics[0].textContent = `$${p.toFixed(2)}`;
        metrics[1].textContent = `${(t * 100).toFixed(0)}%`;
        metrics[2].textContent = `$${tot.toFixed(2)}`;
      }
    } else if (e.target.closest('form[data-gx-command="comp.apply_props"]') || e.target.closest('#docs-content')) {
      if (e.target.matches('input, select')) updateLivePreview();
    }
  });
  document.addEventListener("change", (e) => {
    if (e.target.closest('form[data-gx-command="comp.apply_props"]') || e.target.closest('#docs-content')) {
      updateLivePreview();
    }
  });

  document.addEventListener("submit", (event) => {
    const form = event.target.closest("form[data-gx-command]");
    if (!form) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    runDemoCommand(form.dataset.gxCommand || "", form);
  }, true);

  document.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-gx-command]");
    if (!button || button.closest("form")) return;
    event.preventDefault();
    runDemoCommand(button.dataset.gxCommand || "", button);
  }, true);

  document.addEventListener("click", async (event) => {
    const copy = event.target.closest("[data-gx-copy]");
    if (!copy) return;
    const code = document.getElementById(copy.dataset.gxCopy);
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code.dataset.gxRawCode || code.innerText);
      const old = copy.textContent;
      copy.textContent = "Copied!";
      setTimeout(() => { copy.textContent = old; }, 1400);
    } catch (_) { announce("Clipboard access is unavailable"); }
  });

  const toggleTheme = () => {
    const current = document.documentElement.dataset.theme || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("gx-theme", next); } catch(err) {}
    announce(`Theme switched to ${next} mode`);
  };
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-gx-theme-toggle], #theme-toggle, .gx-theme-toggle")) toggleTheme();
  });
  document.addEventListener("gx-theme-toggle", toggleTheme);
  try {
    const saved = localStorage.getItem("gx-theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch(err) {}

  const initGrids = () => document.querySelectorAll("[data-gx-grid]").forEach(grid => {
    if (grid.dataset.staticReady) return;
    grid.dataset.staticReady = "true";
    const body = grid.querySelector("tbody");
    if (!body) return;
    const rows = [...body.querySelectorAll("tr")];
    const search = grid.querySelector("[data-gx-grid-search]");
    const total = grid.querySelector("[data-gx-grid-total]");
    const pageInfo = grid.querySelector("[data-gx-grid-page-info]");
    const previous = grid.querySelector("[data-gx-grid-prev]");
    const next = grid.querySelector("[data-gx-grid-next]");
    const size = Number(grid.dataset.gxPageSize) || 10;
    let page = 1, column = -1, ascending = true, visible = rows;
    const update = () => {
      const query = (search?.value || "").trim().toLowerCase();
      visible = rows.filter(row => row.textContent.toLowerCase().includes(query));
      if (column >= 0) visible.sort((a, b) => {
        const av = a.children[column]?.textContent.trim() || "";
        const bv = b.children[column]?.textContent.trim() || "";
        const an = Number(av), bn = Number(bv);
        const compare = av && bv && Number.isFinite(an) && Number.isFinite(bn) ? an - bn : av.localeCompare(bv);
        return ascending ? compare : -compare;
      });
      const pages = Math.max(1, Math.ceil(visible.length / size));
      page = Math.min(page, pages);
      rows.forEach(row => { row.hidden = true; });
      visible.slice((page - 1) * size, page * size).forEach(row => { row.hidden = false; body.appendChild(row); });
      if (total) total.textContent = `${visible.length} items`;
      if (pageInfo) pageInfo.textContent = `Page ${page} of ${pages}`;
      if (previous) previous.disabled = page <= 1;
      if (next) next.disabled = page >= pages;
    };
    search?.addEventListener("input", () => { page = 1; update(); });
    grid.querySelectorAll("th[data-gx-sort-col]").forEach(header => header.addEventListener("click", () => {
      const selected = Number(header.dataset.gxSortCol);
      ascending = column === selected ? !ascending : true;
      column = selected;
      page = 1;
      update();
    }));
    previous?.addEventListener("click", () => { page--; update(); });
    next?.addEventListener("click", () => { page++; update(); });
    update();
  });

  const initAll = () => {
    initGrids();
    initFlipCards();
    initComponentSearch();
    initContinuousScroll();
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initAll);
  else initAll();
})();""".strip()


CLIENT_JS = r"""(() => {
  const view = document.querySelector('meta[name="gx-view"]')?.content || location.pathname;
  const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const initMotion = (root = document) => {
    if (prefersReducedMotion()) return;
    const targets = root.querySelectorAll ? [...root.querySelectorAll("[data-gx-motion]")] : [];
    if (root.dataset && root.dataset.gxMotion) targets.unshift(root);
    for (const el of targets) {
      if (el._gxMotionDone) continue;
      el._gxMotionDone = true;
      try {
        const conf = JSON.parse(el.dataset.gxMotion);
        const delay = (conf.delay || 0) * 1000;
        const duration = (conf.duration || 0.4) * 1000;
        const initial = conf.initial || { opacity: 0, transform: "translateY(12px)" };
        const animate = conf.animate || { opacity: 1, transform: "translateY(0)" };
        if (el.animate) {
          el.animate([initial, animate], {
            duration,
            delay,
            easing: "cubic-bezier(0.16, 1, 0.3, 1)",
            fill: "forwards"
          });
        }
      } catch (err) {}
    }

    const staggers = root.querySelectorAll ? [...root.querySelectorAll("[data-gx-stagger]")] : [];
    for (const cont of staggers) {
      const step = parseFloat(cont.dataset.gxStagger) || 0.04;
      [...cont.children].forEach((child, i) => {
        if (!child.dataset.gxMotion && child.animate && !child._gxStaggerDone) {
          child._gxStaggerDone = true;
          child.animate([
            { opacity: 0, transform: "translateY(10px)" },
            { opacity: 1, transform: "translateY(0)" }
          ], {
            duration: 350,
            delay: i * step * 1000,
            easing: "cubic-bezier(0.16, 1, 0.3, 1)",
            fill: "both"
          });
        }
      });
    }
  };

  const animateNumber = (el, startVal, endVal, prefix = "", suffix = "") => {
    if (prefersReducedMotion() || isNaN(startVal) || isNaN(endVal)) {
      el.textContent = `${prefix}${endVal}${suffix}`;
      return;
    }
    const duration = 600;
    const startTime = performance.now();
    const tick = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const ease = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      const current = Math.round(startVal + (endVal - startVal) * ease);
      el.textContent = `${prefix}${current.toLocaleString()}${suffix}`;
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };

  const applyPatches = (patches) => {
    const doApply = () => {
      for (const patch of patches || []) {
        if (patch.id === "gx-root") {
          const current = document.querySelector("[data-gx-root]");
          if (current) {
            current.innerHTML = patch.html;
            initMotion(current);
          }
          continue;
        }
        const target = [...document.querySelectorAll("[data-gx-id]")]
          .find((node) => node.dataset.gxId === patch.id);
        if (!target) continue;

        let oldNum = null, prefix = "", suffix = "";
        const oldNumEl = target.querySelector("[data-gx-animate-number]") || (target.matches("[data-gx-animate-number]") ? target : null);
        if (oldNumEl) {
          const txt = oldNumEl.textContent.trim();
          const match = txt.match(/^([^0-9\-\.]*)([0-9\.,]+)(.*)$/);
          if (match) {
            prefix = match[1];
            oldNum = parseFloat(match[2].replace(/,/g, ""));
            suffix = match[3];
          }
        }

        const oldRect = (!prefersReducedMotion() && target.getBoundingClientRect) ? target.getBoundingClientRect() : null;

        const temp = document.createElement("div");
        temp.innerHTML = patch.html;
        const newEl = temp.firstElementChild;
        if (!newEl) {
          target.outerHTML = patch.html;
          continue;
        }

        target.replaceWith(newEl);
        initMotion(newEl);

        if (oldNum !== null && !isNaN(oldNum)) {
          const newNumEl = newEl.querySelector("[data-gx-animate-number]") || (newEl.matches("[data-gx-animate-number]") ? newEl : null);
          if (newNumEl) {
            const txt = newNumEl.textContent.trim();
            const match = txt.match(/^([^0-9\-\.]*)([0-9\.,]+)(.*)$/);
            if (match) {
              const newNum = parseFloat(match[2].replace(/,/g, ""));
              if (!isNaN(newNum) && newNum !== oldNum) {
                animateNumber(newNumEl, oldNum, newNum, prefix, suffix);
              }
            }
          }
        }

        if (oldRect && newEl.animate) {
          const newRect = newEl.getBoundingClientRect();
          const dx = oldRect.left - newRect.left;
          const dy = oldRect.top - newRect.top;
          const dw = oldRect.width / Math.max(1, newRect.width);
          const dh = oldRect.height / Math.max(1, newRect.height);

          if (Math.abs(dx) > 1 || Math.abs(dy) > 1 || Math.abs(dw - 1) > 0.05 || Math.abs(dh - 1) > 0.05) {
            newEl.animate([
              { transformOrigin: "top left", transform: `translate(${dx}px, ${dy}px) scale(${dw}, ${dh})` },
              { transformOrigin: "top left", transform: "translate(0, 0) scale(1, 1)" }
            ], {
              duration: 260,
              easing: "cubic-bezier(0.16, 1, 0.3, 1)"
            });
          }
        }
      }
      if (window._gxInitDataGrids) window._gxInitDataGrids();
    };

    if (document.startViewTransition && !prefersReducedMotion()) {
      document.startViewTransition(() => doApply());
    } else {
      doApply();
    }
  };

  // Tab switching
  document.addEventListener("click", (e) => {
    const tabBtn = e.target.closest("[data-gx-tab-target]");
    if (!tabBtn) return;
    const container = tabBtn.closest("[data-gx-tabs]");
    if (!container) return;
    const targetId = tabBtn.dataset.gxTabTarget;
    container.querySelectorAll(".gx-tab-btn").forEach(b => b.classList.remove("active"));
    container.querySelectorAll(".gx-tab-pane").forEach(p => p.classList.remove("active"));
    tabBtn.classList.add("active");
    const pane = container.querySelector(`[data-gx-tab-pane="${targetId}"]`);
    if (pane) pane.classList.add("active");
  });

  // Modal open/close & Accessible Focus Trapping
  let lastActiveModalTrigger = null;
  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-gx-modal-open]");
    if (trigger) {
      const modal = document.querySelector(`[data-gx-modal="${trigger.dataset.gxModalOpen}"]`);
      if (modal) {
        lastActiveModalTrigger = trigger;
        modal.classList.add("open");
        const focusables = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
        if (focusables.length) focusables[0].focus();
      }
      return;
    }
    const close = e.target.closest("[data-gx-modal-close]");
    if (close) {
      const modal = close.closest(".gx-modal-backdrop");
      if (modal) {
        modal.classList.remove("open");
        if (lastActiveModalTrigger) {
          lastActiveModalTrigger.focus();
          lastActiveModalTrigger = null;
        }
      }
    }
  });

  document.addEventListener("keydown", (e) => {
    const openModal = document.querySelector(".gx-modal-backdrop.open");
    if (!openModal) return;
    if (e.key === "Escape") {
      openModal.classList.remove("open");
      if (lastActiveModalTrigger) {
        lastActiveModalTrigger.focus();
        lastActiveModalTrigger = null;
      }
      return;
    }
    if (e.key === "Tab") {
      const focusables = [...openModal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(el => !el.disabled);
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  });

  // Form submission with Optimistic UI & Rollback
  document.addEventListener("submit", async (event) => {
    const form = event.target.closest("form[data-gx-command]");
    if (!form) return;
    event.preventDefault();
    const submit = form.querySelector('button[type="submit"]');
    const error = form.querySelector("[data-gx-error]");
    if (error) error.textContent = "";

    const serializeForm = (f) => {
      const entries = [];
      const fd = new FormData(f);
      for (const [k, v] of fd.entries()) {
        if (typeof v === "string") entries.push([k, v]);
      }
      const actionId = f.querySelector('input[name="_gx_action_id"]')?.value || (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()));
      return { type: "form", actionId: actionId, url: f.action, entries: entries, timestamp: Date.now() };
    };

    if (!navigator.onLine) {
      if (window._gxPushOfflineQueue) window._gxPushOfflineQueue(serializeForm(form));
      if (window.gxShowToast) {
        window.gxShowToast("Offline: Form action saved to persistent queue. Replays on reconnection.", "Offline Buffered", "warning", 4000);
      }
      return;
    }
    if (submit) submit.disabled = true;

    const isOptimistic = form.hasAttribute("data-gx-optimistic");
    let originalHtml = null;
    if (isOptimistic) {
      originalHtml = form.innerHTML;
      form.classList.add("gx-optimistic-pending");
    }

    try {
      const response = await fetch(form.action, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        body: new URLSearchParams(new FormData(form))
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || `Request failed (${response.status})`);
      }
      if (result.replayed || result.reload) {
        location.reload();
        return;
      }
      applyPatches(result.patches);
      const currentForm = [...document.querySelectorAll("form[data-gx-command]")]
        .find((node) => node.dataset.gxCommand === form.dataset.gxCommand);
      const actionId = currentForm?.querySelector('input[name="_gx_action_id"]');
      if (actionId) actionId.value = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}${Math.random().toString(36).slice(2)}`);
    } catch (err) {
      if (!navigator.onLine || err.message.includes("Failed to fetch") || err.name === "TypeError") {
        if (window._gxPushOfflineQueue) window._gxPushOfflineQueue(serializeForm(form));
        if (window.gxShowToast) {
          window.gxShowToast("Network dropped. Form action saved to persistent offline queue.", "Offline Queued", "warning", 4000);
        }
      }
      if (isOptimistic && originalHtml !== null) {
        form.innerHTML = originalHtml;
      }
      const currentForm = document.querySelector(`form[data-gx-command="${CSS.escape(form.dataset.gxCommand)}"]`);
      const currentError = currentForm?.querySelector("[data-gx-error]");
      if (currentError) currentError.textContent = err.message || "Request failed";
      else console.error("RADUI command failed", err);
    } finally {
      if (isOptimistic) {
        form.classList.remove("gx-optimistic-pending");
      }
      const currentForm = document.querySelector(`form[data-gx-command="${CSS.escape(form.dataset.gxCommand)}"]`);
      const currentSubmit = currentForm?.querySelector('button[type="submit"]');
      if (currentSubmit) currentSubmit.disabled = false;
    }
  });

  // Pointer & Micro-interaction handlers (hover & tap)
  // Keep the pointer origin on native RadUI surfaces so themes can render a
  // subtle cursor-following highlight without adding per-component scripts.
  document.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    const surface = event.target.closest(".gx-card, .gx-metric, .gx-code-block");
    if (!surface) return;
    const rect = surface.getBoundingClientRect();
    surface.style.setProperty("--gx-pointer-x", `${event.clientX - rect.left}px`);
    surface.style.setProperty("--gx-pointer-y", `${event.clientY - rect.top}px`);
  }, { passive: true });

  document.addEventListener("pointerdown", (e) => {
    const tapEl = e.target.closest("[data-gx-tap]");
    if (!tapEl || prefersReducedMotion()) return;
    try {
      const conf = JSON.parse(tapEl.dataset.gxTap);
      tapEl.style.transition = `transform ${conf.duration || 0.1}s ease`;
      tapEl.style.transform = `scale(${conf.scale || 0.97})`;
      const reset = () => {
        tapEl.style.transform = "";
        window.removeEventListener("pointerup", reset);
        window.removeEventListener("pointercancel", reset);
      };
      window.addEventListener("pointerup", reset, { once: true });
      window.addEventListener("pointercancel", reset, { once: true });
    } catch(err) {}
  });

  document.addEventListener("mouseover", (e) => {
    const hoverEl = e.target.closest("[data-gx-hover]");
    if (!hoverEl || hoverEl._gxHoverActive || prefersReducedMotion()) return;
    try {
      const conf = JSON.parse(hoverEl.dataset.gxHover);
      hoverEl._gxHoverActive = true;
      hoverEl.style.transition = `transform ${conf.duration || 0.2}s cubic-bezier(0.16, 1, 0.3, 1), box-shadow ${conf.duration || 0.2}s ease`;
      const transforms = [];
      if (conf.scale) transforms.push(`scale(${conf.scale})`);
      if (conf.translateY) transforms.push(`translateY(${conf.translateY}px)`);
      if (transforms.length) hoverEl.style.transform = transforms.join(" ");
      if (conf.shadow) hoverEl.style.boxShadow = conf.shadow;

      const onLeave = () => {
        hoverEl.style.transform = "";
        hoverEl.style.boxShadow = "";
        hoverEl._gxHoverActive = false;
        hoverEl.removeEventListener("mouseleave", onLeave);
      };
      hoverEl.addEventListener("mouseleave", onLeave);
    } catch(err) {}
  });

  document.addEventListener("DOMContentLoaded", () => initMotion(document));
  setTimeout(() => initMotion(document), 20);

  // Job cancellation
  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-gx-job-cancel]");
    if (!button) return;
    button.disabled = true;
    try {
      const response = await fetch(button.dataset.endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-GX-CSRF": button.dataset.csrf || "",
          "Accept": "application/json"
        }
      });
      const result = await response.json();
      if (!response.ok || !result.ok) throw new Error(result.error || "Cancellation failed");
    } catch (err) {
      button.disabled = false;
      const error = button.closest("[data-gx-id]")?.querySelector("[data-gx-job-error]");
      if (error) error.textContent = err.message || "Cancellation failed";
    }
  });

  // Standalone button and ActionCard approval/rejection triggers
  document.addEventListener("click", async (event) => {
    const actionBtn = event.target.closest("[data-gx-action-trigger], [data-gx-command]");
    if (!actionBtn) return;
    const form = actionBtn.closest("form");
    if (form) return; // let form handler take it
    const command = actionBtn.dataset.gxActionTrigger || actionBtn.dataset.gxCommand;
    const csrf = actionBtn.dataset.csrf || actionBtn.dataset.gxCsrf;

    const serializeAction = () => {
      const actionId = crypto.randomUUID ? crypto.randomUUID() : String(Date.now());
      return {
        type: "action",
        actionId: actionId,
        url: `/_gx/commands/${encodeURIComponent(command)}`,
        command: command,
        csrf: csrf,
        payload: actionBtn.dataset.actionPayload || null,
        timestamp: Date.now()
      };
    };

    if (!navigator.onLine) {
      if (window._gxPushOfflineQueue) window._gxPushOfflineQueue(serializeAction());
      if (window.gxShowToast) {
        window.gxShowToast("Offline: Action saved to persistent queue. Replays on reconnection.", "Offline Buffered", "warning", 4000);
      }
      return;
    }

    actionBtn.disabled = true;
    try {
      const params = new URLSearchParams();
      params.set("_csrf", csrf);
      params.set("_gx_action_id", crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}`);
      params.set("_gx_view_id", view);
      if (actionBtn.dataset.actionPayload) {
        const payload = JSON.parse(actionBtn.dataset.actionPayload);
        for (const [k, v] of Object.entries(payload)) params.set(k, String(v));
      }
      const res = await fetch(`/_gx/commands/${encodeURIComponent(command)}`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Accept": "application/json" },
        body: params
      });
      const data = await res.json();
      if (data.patches) applyPatches(data.patches);
    } catch(e) {
      if (!navigator.onLine || e.message.includes("Failed to fetch") || e.name === "TypeError") {
        if (window._gxPushOfflineQueue) window._gxPushOfflineQueue(serializeAction());
        if (window.gxShowToast) {
          window.gxShowToast("Network dropped. Action saved to persistent offline queue.", "Offline Queued", "warning", 4000);
        }
      } else {
        console.error("Action trigger failed", e);
      }
      actionBtn.disabled = false;
    }
  });

  // EventSource stream & targeted invalidations
  const cursor = document.querySelector('meta[name="gx-event-cursor"]')?.content || "0";
  const source = new EventSource("/_gx/events?since=" + encodeURIComponent(cursor));
  source.addEventListener("reset", () => location.reload());
  const pendingInvalidations = new Set();
  let refreshRunning = false;
  const drainInvalidations = async () => {
    if (refreshRunning) return;
    refreshRunning = true;
    try {
      while (pendingInvalidations.size) {
        const batch = [...pendingInvalidations].slice(0, 50);
        for (const id of batch) pendingInvalidations.delete(id);
        const url = new URL("/_gx/refresh", location.origin);
        url.searchParams.set("view_id", view);
        for (const id of batch) url.searchParams.append("id", id);
        const response = await fetch(url, { cache: "no-store", credentials: "same-origin", headers: { "Accept": "application/json" } });
        if (!response.ok) throw new Error("Refresh failed");
        const result = await response.json();
        applyPatches(result.patches);
      }
    } catch (err) {
      console.error("RADUI refresh failed", err);
      location.reload();
    } finally {
      refreshRunning = false;
      if (pendingInvalidations.size) void drainInvalidations();
    }
  };

  source.addEventListener("invalidate", (event) => {
    try {
      const detail = JSON.parse(event.data);
      if (detail.view_id !== view) return;
      for (const id of detail.component_ids || []) pendingInvalidations.add(id);
      if (!pendingInvalidations.size) return;
      void drainInvalidations();
    } catch (err) {
      console.error("Invalid RADUI event", err);
      location.reload();
    }
  });

  // Offline & Reconnection Status Indicator
  const banner = document.createElement("div");
  banner.className = "gx-connection-banner";
  banner.id = "gx-connection-banner";
  banner.innerHTML = "<span>Connection lost. Reconnecting...</span>";
  document.addEventListener("DOMContentLoaded", () => document.body.appendChild(banner));
  if (document.body) document.body.appendChild(banner);

  window.addEventListener("offline", () => banner.classList.add("visible"));
  window.addEventListener("online", () => banner.classList.remove("visible"));
  source.addEventListener("open", () => banner.classList.remove("visible"));
  source.addEventListener("error", () => {
    if (source.readyState === 0 || source.readyState === 2) {
      banner.classList.add("visible");
    }
  });

  // Developer Inspector Drawer toggle
  const inspectBadge = document.getElementById("gx-inspect-badge");
  const inspectDrawer = document.getElementById("gx-inspect-drawer");
  if (inspectBadge && inspectDrawer) {
    inspectBadge.addEventListener("click", () => {
      inspectDrawer.classList.toggle("open");
      if (inspectDrawer.classList.contains("open")) {
        loadInspectorData("traces");
      }
    });

    document.querySelectorAll(".gx-insp-tab").forEach(tab => {
      tab.addEventListener("click", () => {
        document.querySelectorAll(".gx-insp-tab").forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        loadInspectorData(tab.dataset.target);
      });
    });

    async function loadInspectorData(tab) {
      const body = document.getElementById("gx-insp-content");
      if (!body) return;
      body.innerHTML = "<p>Loading inspector data...</p>";
      try {
        const res = await fetch("/_gx/inspect/traces?limit=50", { credentials: "same-origin" });
        const data = await res.json();
        if (tab === "traces") {
          body.innerHTML = `<div><strong>Recent Execution Traces (${data.total || 0})</strong><pre>${JSON.stringify(data.records, null, 2)}</pre></div>`;
        } else if (tab === "stats") {
          body.innerHTML = `<div><strong>Runtime Statistics</strong><pre>${JSON.stringify(data.stats, null, 2)}</pre></div>`;
        } else {
          body.innerHTML = `<pre>${JSON.stringify(data, null, 2)}</pre>`;
        }
      } catch (err) {
        body.innerHTML = `<p style="color:#ef4444">Failed to load inspector: ${err.message}</p>`;
      }
    }

    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey && e.shiftKey && (e.key === "I" || e.key === "i")) {
        e.preventDefault();
        inspectDrawer.classList.toggle("open");
      }
    });
  }

  // CodeBlock copy button
  document.addEventListener("click", async (e) => {
    const copyBtn = e.target.closest("[data-gx-copy]");
    if (!copyBtn) return;
    const targetId = copyBtn.dataset.gxCopy;
    const codeEl = document.getElementById(targetId);
    if (!codeEl) return;
    const textToCopy = codeEl.dataset.gxRawCode || codeEl.innerText;
    try {
      await navigator.clipboard.writeText(textToCopy);
      const original = copyBtn.innerHTML;
      copyBtn.textContent = "Copied!";
      setTimeout(() => { copyBtn.innerHTML = original; }, 1800);
    } catch(err) {
      console.warn("Clipboard copy failed", err);
    }
  });

  // TreeView expand/collapse
  document.addEventListener("click", (e) => {
    const caret = e.target.closest("[data-gx-tree-toggle]");
    if (!caret) return;
    e.stopPropagation();
    const item = caret.closest(".gx-tree-item");
    if (!item) return;
    const nested = item.querySelector(":scope > .gx-tree-nested");
    if (nested) {
      const isOpen = nested.classList.contains("open");
      if (isOpen) {
        nested.classList.remove("open");
        caret.classList.remove("expanded");
      } else {
        nested.classList.add("open");
        caret.classList.add("expanded");
      }
    }
  });

  // DataGrid interactive search, sort, and pagination
  const initDataGrids = () => {
    document.querySelectorAll("[data-gx-grid]").forEach(grid => {
      if (grid._gxGridInitialized) return;
      grid._gxGridInitialized = true;
      const searchInput = grid.querySelector("[data-gx-grid-search]");
      const table = grid.querySelector(".gx-table");
      const tbody = table?.querySelector("tbody");
      if (!tbody) return;
      const allRows = Array.from(tbody.querySelectorAll("tr"));
      const totalCountEl = grid.querySelector("[data-gx-grid-total]");
      const pageInfoEl = grid.querySelector("[data-gx-grid-page-info]");
      const prevBtn = grid.querySelector("[data-gx-grid-prev]");
      const nextBtn = grid.querySelector("[data-gx-grid-next]");
      const pageSize = parseInt(grid.dataset.gxPageSize || "10", 10);
      let currentPage = 1;
      let sortCol = -1;
      let sortAsc = true;
      let filteredRows = [...allRows];

      const updateView = () => {
        const query = (searchInput?.value || "").toLowerCase().trim();
        filteredRows = allRows.filter(row => {
          if (!query) return true;
          return row.textContent.toLowerCase().includes(query);
        });
        if (sortCol >= 0) {
          filteredRows.sort((a, b) => {
            const aVal = a.children[sortCol]?.textContent.trim() || "";
            const bVal = b.children[sortCol]?.textContent.trim() || "";
            const numA = parseFloat(aVal), numB = parseFloat(bVal);
            let comp = 0;
            if (!isNaN(numA) && !isNaN(numB)) comp = numA - numB;
            else comp = aVal.localeCompare(bVal);
            return sortAsc ? comp : -comp;
          });
        }
        const total = filteredRows.length;
        const totalPages = Math.max(1, Math.ceil(total / pageSize));
        if (currentPage > totalPages) currentPage = totalPages;
        if (currentPage < 1) currentPage = 1;

        allRows.forEach(r => r.style.display = "none");
        const start = (currentPage - 1) * pageSize;
        const end = Math.min(start + pageSize, total);
        for (let i = start; i < end; i++) {
          filteredRows[i].style.display = "";
          tbody.appendChild(filteredRows[i]);
        }
        if (totalCountEl) totalCountEl.textContent = `${total} items`;
        if (pageInfoEl) pageInfoEl.textContent = `Page ${currentPage} of ${totalPages}`;
        if (prevBtn) prevBtn.disabled = currentPage <= 1;
        if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
      };

      if (searchInput) {
        searchInput.addEventListener("input", () => {
          currentPage = 1;
          updateView();
        });
      }
      grid.querySelectorAll("th[data-gx-sort-col]").forEach(th => {
        th.style.cursor = "pointer";
        th.addEventListener("click", () => {
          const col = parseInt(th.dataset.gxSortCol, 10);
          if (sortCol === col) {
            sortAsc = !sortAsc;
          } else {
            sortCol = col;
            sortAsc = true;
          }
          grid.querySelectorAll("th[data-gx-sort-col]").forEach(other => {
            other.querySelector(".gx-sort-icon")?.remove();
          });
          const icon = document.createElement("span");
          icon.className = "gx-sort-icon";
          icon.style.marginLeft = "4px";
          icon.textContent = sortAsc ? "▲" : "▼";
          th.appendChild(icon);
          updateView();
        });
      });
      if (prevBtn) {
        prevBtn.addEventListener("click", () => {
          if (currentPage > 1) { currentPage--; updateView(); }
        });
      }
      if (nextBtn) {
        nextBtn.addEventListener("click", () => {
          const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
          if (currentPage < totalPages) { currentPage++; updateView(); }
        });
      }
      updateView();
    });
  };
  window._gxInitDataGrids = initDataGrids;
  document.addEventListener("DOMContentLoaded", initDataGrids);
  setTimeout(initDataGrids, 10);

  // Virtual Lists
  const initVirtualLists = () => {
    document.querySelectorAll("[data-gx-virtual-items]").forEach(vl => {
      if (vl._gxVlInit) return;
      vl._gxVlInit = true;
      const items = JSON.parse(vl.dataset.gxVirtualItems || "[]");
      const itemHeight = parseInt(vl.dataset.gxItemHeight || "40", 10);
      const content = vl.querySelector(".gx-virtual-content");
      const renderVisible = () => {
        const scrollTop = vl.scrollTop;
        const viewHeight = vl.clientHeight || 320;
        const start = Math.max(0, Math.floor(scrollTop / itemHeight) - 2);
        const end = Math.min(items.length, Math.ceil((scrollTop + viewHeight) / itemHeight) + 2);
        content.style.transform = `translateY(${start * itemHeight}px)`;
        content.innerHTML = items.slice(start, end).map(it => `<div class="gx-virtual-item" style="height:${itemHeight}px">${it}</div>`).join("");
      };
      vl.addEventListener("scroll", renderVisible);
      renderVisible();
    });
  };
  window._gxInitVirtualLists = initVirtualLists;
  document.addEventListener("DOMContentLoaded", initVirtualLists);
  setTimeout(initVirtualLists, 15);

  // Theme toggle
  const toggleTheme = () => {
    const current = document.documentElement.dataset.theme || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("gx-theme", next); } catch(err) {}
  };
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-gx-theme-toggle]")) toggleTheme();
  });
  document.addEventListener("gx-theme-toggle", toggleTheme);
  try {
    const saved = localStorage.getItem("gx-theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch(err) {}

  // File Upload preview
  document.addEventListener("change", (e) => {
    const input = e.target.closest(".gx-file-input");
    if (!input) return;
    const container = input.closest(".gx-file-upload");
    const listEl = container?.querySelector("[data-gx-file-list]");
    if (listEl && input.files) {
      listEl.innerHTML = Array.from(input.files).map(f => `<div>${f.name} (${Math.round(f.size/1024)} KB)</div>`).join("");
    }
  });

  // Native Command Palette (Ctrl+K)
  const paletteBackdrop = document.getElementById("gx-command-palette");
  const paletteInput = paletteBackdrop?.querySelector(".gx-palette-input");
  const paletteList = paletteBackdrop?.querySelector(".gx-palette-list");

  const togglePalette = (show) => {
    if (!paletteBackdrop) return;
    const willOpen = show !== undefined ? show : !paletteBackdrop.classList.contains("open");
    if (willOpen) {
      paletteBackdrop.classList.add("open");
      if (paletteInput) {
        paletteInput.value = "";
        paletteInput.focus();
        filterPalette("");
      }
    } else {
      paletteBackdrop.classList.remove("open");
    }
  };

  const filterPalette = (q) => {
    if (!paletteList) return;
    const items = paletteList.querySelectorAll(".gx-palette-item");
    let first = true;
    items.forEach(it => {
      const txt = it.textContent.toLowerCase();
      const matches = txt.includes(q.toLowerCase());
      it.style.display = matches ? "flex" : "none";
      it.classList.remove("selected");
      if (matches && first) {
        it.classList.add("selected");
        first = false;
      }
    });
  };

  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      togglePalette();
    } else if (e.key === "Escape" && paletteBackdrop?.classList.contains("open")) {
      togglePalette(false);
    }
  });

  if (paletteBackdrop) {
    paletteBackdrop.addEventListener("click", (e) => {
      if (e.target === paletteBackdrop) togglePalette(false);
    });
  }
  if (paletteInput) {
    paletteInput.addEventListener("input", (e) => filterPalette(e.target.value));
    paletteInput.addEventListener("keydown", (e) => {
      if (!paletteList) return;
      const visible = [...paletteList.querySelectorAll(".gx-palette-item")].filter(it => it.style.display !== "none");
      let idx = visible.findIndex(it => it.classList.contains("selected"));
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (idx >= 0) visible[idx].classList.remove("selected");
        const next = (idx + 1) % visible.length;
        visible[next]?.classList.add("selected");
        visible[next]?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (idx >= 0) visible[idx].classList.remove("selected");
        const prev = (idx - 1 + visible.length) % visible.length;
        visible[prev]?.classList.add("selected");
        visible[prev]?.scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        e.preventDefault();
        const sel = visible[idx] || visible[0];
        if (sel) {
          togglePalette(false);
          sel.click();
        }
      }
    });
  }

  // Drawer handlers
  document.addEventListener("click", (e) => {
    const openBtn = e.target.closest("[data-gx-drawer-open]");
    if (openBtn) {
      const drawerWrap = openBtn.closest(".gx-drawer-container");
      const backdrop = drawerWrap?.querySelector(".gx-drawer-backdrop");
      if (backdrop) backdrop.classList.add("open");
      return;
    }
    const closeBtn = e.target.closest(".gx-drawer-close");
    if (closeBtn) {
      const backdrop = closeBtn.closest(".gx-drawer-backdrop");
      if (backdrop) backdrop.classList.remove("open");
      return;
    }
    if (e.target.classList && e.target.classList.contains("gx-drawer-backdrop")) {
      e.target.classList.remove("open");
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".gx-drawer-backdrop.open").forEach(b => b.classList.remove("open"));
    }
  });

  // Toast dynamic notification center
  const showToast = (msg, title = "", variant = "info", duration = 4000) => {
    let container = document.querySelector(".gx-toast-container");
    if (!container) {
      container = document.createElement("div");
      container.className = "gx-toast-container gx-toast-top-right";
      document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = `gx-toast gx-toast-${variant}`;
    toast.setAttribute("role", "status");
    const titleHtml = title ? `<div class="gx-toast-title">${title}</div>` : "";
    toast.innerHTML = `<div class="gx-toast-body">${titleHtml}<div class="gx-toast-msg">${msg}</div></div><button type="button" class="gx-toast-close">&times;</button>`;
    toast.querySelector(".gx-toast-close").addEventListener("click", () => toast.remove());
    container.appendChild(toast);
    if (duration > 0) {
      setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(-10px) scale(0.96)";
        setTimeout(() => toast.remove(), 250);
      }, duration);
    }
  };
  window.gxShowToast = showToast;
  source.addEventListener("gx:toast", (event) => {
    try {
      const data = JSON.parse(event.data);
      showToast(data.message, data.title || "", data.variant || "info", data.duration || 4000);
    } catch(err) {}
  });

  // Scroll Reveal via IntersectionObserver
  const initScrollReveals = () => {
    if (prefersReducedMotion() || !window.IntersectionObserver) {
      document.querySelectorAll("[data-gx-reveal]").forEach(el => el.classList.add("gx-revealed"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add("gx-revealed");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });
    document.querySelectorAll("[data-gx-reveal]:not(.gx-revealed)").forEach(el => observer.observe(el));
  };
  document.addEventListener("DOMContentLoaded", initScrollReveals);
  setTimeout(initScrollReveals, 20);

  // Durable IndexedDB-backed Client Mutation Queue with Web Locks API Cross-Tab Coordination
  const DB_NAME = "_gx_offline_db";
  const DB_VERSION = 1;
  const STORE_NAME = "mutations";

  const openDB = () => {
    return new Promise((resolve) => {
      if (!window.indexedDB) return resolve(null);
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (e) => {
        const db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          const store = db.createObjectStore(STORE_NAME, { keyPath: "actionId" });
          store.createIndex("timestamp", "timestamp", { unique: false });
        }
      };
      req.onsuccess = (e) => resolve(e.target.result);
      req.onerror = () => resolve(null);
    });
  };

  const getPendingMutations = async () => {
    const db = await openDB();
    if (!db) {
      try {
        const raw = localStorage.getItem("__gx_offline_q");
        return raw ? JSON.parse(raw) : [];
      } catch(e) { return []; }
    }
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const store = tx.objectStore(STORE_NAME);
      const req = store.getAll();
      req.onsuccess = () => {
        const items = req.result || [];
        items.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
        resolve(items);
      };
      req.onerror = () => resolve([]);
    });
  };

  const putMutation = async (record) => {
    const now = Date.now();
    const enriched = {
      status: record.status || "QUEUED",
      actionId: record.actionId,
      url: record.url || window.location.href,
      type: record.type || "action",
      entries: record.entries || [],
      payload: record.payload || null,
      csrf: record.csrf || "",
      commandId: record.commandId || "",
      timestamp: record.timestamp || now,
      retries: record.retries || 0,
      lastError: record.lastError || null,
      lastStatusCode: record.lastStatusCode || null,
      nextRetryAt: record.nextRetryAt || null,
      version: 1,
      expiresAt: record.expiresAt || (now + 86400000)
    };
    const db = await openDB();
    if (!db) {
      try {
        const raw = localStorage.getItem("__gx_offline_q");
        const list = raw ? JSON.parse(raw) : [];
        const idx = list.findIndex(x => x.actionId === enriched.actionId);
        if (idx >= 0) {
          list[idx] = enriched;
        } else {
          list.push(enriched);
        }
        localStorage.setItem("__gx_offline_q", JSON.stringify(list));
      } catch(e) {}
      return;
    }
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      store.put(enriched);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  };

  const deleteMutation = async (actionId) => {
    const db = await openDB();
    if (!db) {
      try {
        const raw = localStorage.getItem("__gx_offline_q");
        if (raw) {
          const list = JSON.parse(raw).filter(x => x.actionId !== actionId);
          localStorage.setItem("__gx_offline_q", JSON.stringify(list));
        }
      } catch(e) {}
      return;
    }
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      store.delete(actionId);
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  };

  const clearAllMutations = async () => {
    const db = await openDB();
    if (!db) {
      try { localStorage.removeItem("__gx_offline_q"); } catch(e) {}
      return;
    }
    return new Promise((resolve) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const store = tx.objectStore(STORE_NAME);
      store.clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
    });
  };

  window._gxPushOfflineQueue = putMutation;

  // Web Locks API for coordinating replay so multiple open browser tabs never replay the same queue item concurrently
  const executeReplay = async () => {
    const runWorker = async (leaseToken) => {
      const queue = await getPendingMutations();
      if (queue.length === 0) return;
      const now = Date.now();
      const valid = queue.filter(item => {
        if (item.expiresAt && item.expiresAt <= now) return false;
        if (item.status === "PERMANENT_FAILURE" || item.status === "AUTH_REQUIRED") return false;
        if (item.nextRetryAt && item.nextRetryAt > now) return false;
        return true;
      });
      if (valid.length < queue.length) {
        for (const expired of queue.filter(item => item.expiresAt && item.expiresAt <= now)) {
          await deleteMutation(expired.actionId);
        }
      }
      if (valid.length === 0) return;

      if (window.gxShowToast) {
        window.gxShowToast("Network restored. Syncing " + valid.length + " pending mutation(s)...", "Reconnected", "info", 3000);
      }

      for (const mut of valid) {
        // Guard against tab suspension during fallback lease
        if (!navigator.locks && leaseToken && localStorage.getItem("_gx_replay_lease") !== leaseToken) {
          return; // Lease lost while tab was suspended
        }

        mut.status = "IN_FLIGHT";
        await putMutation(mut);

        try {
          const params = new URLSearchParams();
          if (mut.type === "form" && Array.isArray(mut.entries)) {
            for (const [k, v] of mut.entries) params.append(k, v);
          } else {
            params.set("_csrf", mut.csrf);
            params.set("_gx_action_id", mut.actionId);
            params.set("_gx_view_id", view);
            if (mut.payload) {
              try {
                const p = typeof mut.payload === "string" ? JSON.parse(mut.payload) : mut.payload;
                for (const [k, v] of Object.entries(p)) params.set(k, String(v));
              } catch(e) {}
            }
          }
          const res = await fetch(mut.url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Accept": "application/json" },
            body: params
          });

          if (res.status === 401) {
            mut.status = "AUTH_REQUIRED";
            mut.lastStatusCode = 401;
            mut.lastError = "Authentication expired";
            await putMutation(mut);
            if (window.gxShowToast) {
              window.gxShowToast("Session expired while offline. Sign in to resume synchronizing actions.", "Auth Required", "danger", 6000);
            }
            break; // Pause replay, preserve mutation in queue
          }

          const errData = (res.status >= 400) ? await res.json().catch(() => ({})) : {};
          const errCode = errData.error_code || "";
          const retryAfter = res.headers.get("Retry-After");

          if (res.status === 429 || (res.status === 409 && (errCode === "IDEMPOTENCY_IN_PROGRESS" || retryAfter))) {
            // RETRYABLE: Concurrent worker processing or rate limited -> stay in QUEUED with backoff
            const nextRetries = (mut.retries || 0) + 1;
            if (nextRetries >= 10) {
              mut.status = "PERMANENT_FAILURE";
              mut.lastError = "Max retries exceeded (In-flight conflict/rate limit)";
              mut.lastStatusCode = res.status;
            } else {
              mut.status = "QUEUED";
              mut.retries = nextRetries;
              mut.lastError = errData.error || "Action processing on server";
              mut.lastStatusCode = res.status;
              const delaySec = retryAfter ? parseInt(retryAfter, 10) : Math.min(30, Math.pow(2, nextRetries));
              mut.nextRetryAt = Date.now() + (delaySec * 1000);
            }
            await putMutation(mut);
            continue;
          }

          if (res.status === 400 || res.status === 404 || res.status === 409 || res.status === 422) {
            // PERMANENT_FAILURE: Client payload error, validation failure, or payload fingerprint conflict
            mut.status = "PERMANENT_FAILURE";
            mut.lastStatusCode = res.status;
            mut.lastError = errData.error || ("Permanent rejection: HTTP " + res.status);
            await putMutation(mut);
            if (window.gxShowToast) {
              window.gxShowToast(mut.lastError, res.status === 409 ? "Conflict" : "Submission Error", "danger", 5000);
            }
            continue;
          }

          if (res.ok) {
            mut.status = "SUCCESS";
            const data = await res.json().catch(() => ({}));
            if (data && data.patches) applyPatches(data.patches);
            await deleteMutation(mut.actionId);
          } else {
            // Transient 5xx error: return to QUEUED state with exponential backoff metadata
            const nextRetries = (mut.retries || 0) + 1;
            if (nextRetries >= 10) {
              mut.status = "PERMANENT_FAILURE";
              mut.lastError = "Max retries exceeded (HTTP " + res.status + ")";
              mut.lastStatusCode = res.status;
            } else {
              mut.status = "QUEUED";
              mut.retries = nextRetries;
              mut.lastError = "HTTP " + res.status;
              mut.lastStatusCode = res.status;
              const delay = Math.min(60000, 1000 * Math.pow(2, nextRetries)) + Math.floor(Math.random() * 500);
              mut.nextRetryAt = Date.now() + delay;
            }
            await putMutation(mut);
          }
        } catch(netErr) {
          // Transient network disconnect: return to QUEUED state
          const nextRetries = (mut.retries || 0) + 1;
          if (nextRetries >= 10) {
            mut.status = "PERMANENT_FAILURE";
            mut.lastError = "Max retries exceeded (Network unreachable)";
            mut.lastStatusCode = 0;
          } else {
            mut.status = "QUEUED";
            mut.retries = nextRetries;
            mut.lastError = netErr ? (netErr.message || String(netErr)) : "Network Error";
            mut.lastStatusCode = 0;
            const delay = Math.min(60000, 1000 * Math.pow(2, nextRetries)) + Math.floor(Math.random() * 500);
            mut.nextRetryAt = Date.now() + delay;
          }
          await putMutation(mut);
          break; // Network still disconnected
        }
      }
    };

    if (navigator.locks && navigator.locks.request) {
      try {
        await navigator.locks.request("_gx_replay_lock", { ifAvailable: true }, async (lock) => {
          if (!lock) return; // Another tab holds the replay lock
          await runWorker();
        });
        return;
      } catch(e) {}
    }

    // Fallback cross-tab lease coordination with suspended tab protection
    const now = Date.now();
    const curLease = localStorage.getItem("_gx_replay_lease");
    const leaseExp = parseInt(localStorage.getItem("_gx_replay_lease_exp") || "0", 10);
    if (curLease && now < leaseExp) return;
    const myLease = "lease-" + now + "-" + Math.random().toString(36).slice(2, 8);
    localStorage.setItem("_gx_replay_lease", myLease);
    localStorage.setItem("_gx_replay_lease_exp", String(now + 10000));
    try {
      await runWorker(myLease);
    } finally {
      if (localStorage.getItem("_gx_replay_lease") === myLease) {
        localStorage.removeItem("_gx_replay_lease");
        localStorage.removeItem("_gx_replay_lease_exp");
      }
    }
  };

  // Public Queue Management API
  window._gxQueue = {
    list: getPendingMutations,
    cancel: deleteMutation,
    clear: clearAllMutations,
    replay: executeReplay
  };

  window.addEventListener("online", executeReplay);
  document.addEventListener("DOMContentLoaded", () => {
    if (navigator.onLine) {
      setTimeout(executeReplay, 500);
    }
  });
})();"""


EMBED_JS = """(function() {
  if (window.customElements && !customElements.get("RADUI-view")) {
    class RADUIView extends HTMLElement {
      connectedCallback() {
        const src = this.getAttribute("src") || window.location.origin;
        const view = this.getAttribute("view") || "/";
        const target = `${src.replace(/\\/+$/, "")}${view.startsWith("/") ? view : "/" + view}`;
        const iframe = document.createElement("iframe");
        iframe.src = target;
        iframe.style.width = this.getAttribute("width") || "100%";
        iframe.style.height = this.getAttribute("height") || "100%";
        iframe.style.border = "none";
        iframe.style.display = "block";
        iframe.setAttribute("allow", "clipboard-write");
        this.innerHTML = "";
        this.appendChild(iframe);
      }
    }
    customElements.define("RADUI-view", RADUIView);
  }
})();"""


def _attrs(component: Component) -> str:
    parts: list[str] = []
    if component.id is not None:
        safe_id = escape(component.id, quote=True)
        parts.append(f'id="{safe_id}" data-gx-id="{safe_id}"')

    motion = getattr(component, "motion", None)
    if motion is not None:
        if hasattr(motion, "to_dict"):
            m_dict = motion.to_dict()
        elif isinstance(motion, dict):
            m_dict = motion
        else:
            m_dict = {"preset": str(motion)}
        parts.append(f'data-gx-motion="{escape(json.dumps(m_dict), quote=True)}"')

    hover = getattr(component, "hover", None)
    if hover is not None:
        if hasattr(hover, "to_dict"):
            h_dict = hover.to_dict()
        elif isinstance(hover, dict):
            h_dict = hover
        else:
            h_dict = {"scale": 1.02}
        parts.append(f'data-gx-hover="{escape(json.dumps(h_dict), quote=True)}"')

    tap = getattr(component, "tap", None)
    if tap is not None:
        if hasattr(tap, "to_dict"):
            t_dict = tap.to_dict()
        elif isinstance(tap, dict):
            t_dict = tap
        else:
            t_dict = {"scale": 0.97}
        parts.append(f'data-gx-tap="{escape(json.dumps(t_dict), quote=True)}"')

    motion_id = getattr(component, "motion_id", None)
    if motion_id:
        parts.append(f'data-gx-motion-id="{escape(motion_id, quote=True)}"')

    stagger_children = getattr(component, "stagger_children", 0.0)
    if stagger_children and float(stagger_children) > 0:
        parts.append(f'data-gx-stagger="{float(stagger_children)}"')

    optimistic = getattr(component, "optimistic", False)
    if optimistic:
        parts.append('data-gx-optimistic="true"')

    if not parts:
        return ""
    return " " + " ".join(parts)


class HTMLRenderer:
    def __init__(self, registry: ComponentRegistry | None = None) -> None:
        self.registry = registry or ComponentRegistry.builtins()

    def render_component(
        self,
        component: Component,
        state_context: object | None = None,
        csrf_token: str | None = None,
    ) -> str:
        return self.registry.render(component, state_context, csrf_token)

    def _children(
        self, component: Component, state_context: object | None, csrf_token: str | None
    ) -> str:
        return "".join(
            self.render_component(child, state_context, csrf_token)
            for child in getattr(component, "children", ())
        )

    def render_document(
        self,
        title: str,
        root: Component,
        *,
        state_context: object | None = None,
        csrf_token: str = "",
        view_id: str = "/",
        event_cursor: int = 0,
        debug: bool = False,
        custom_css: str = "",
        command_palette: bool = True,
        direction: str = "ltr",
        static_export: bool = False,
    ) -> str:
        self.registry.validate(root)
        safe_title = escape(title)
        body = self.render_component(root, state_context, csrf_token)
        safe_view = escape(view_id, quote=True)

        inspector_html = ""
        if debug:
            inspector_html = """
            <div id="gx-inspect-badge" title="Toggle RADUI Inspector (Ctrl+Shift+I)">
              <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#38bdf8;"></span>
              GX INSPECT
            </div>
            <div id="gx-inspect-drawer">
              <div class="gx-insp-tabs">
                <button class="gx-insp-tab active" data-target="traces">Traces</button>
                <button class="gx-insp-tab" data-target="stats">Stats</button>
                <button class="gx-insp-tab" onclick="document.getElementById('gx-inspect-drawer').classList.remove('open')" style="margin-left:auto;color:#ef4444;">Close</button>
              </div>
              <div class="gx-insp-body" id="gx-insp-content">
                <p>Click tabs to view telemetry.</p>
              </div>
            </div>
            """

        palette_html = ""
        if command_palette:
            palette_html = """
            <div class="gx-palette-backdrop" id="gx-command-palette">
              <div class="gx-palette-dialog">
                <div class="gx-palette-header">
                  <span style="font-size:1.1rem;color:var(--gx-text-muted);display:flex;align-items:center;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                  </span>
                  <input type="text" class="gx-palette-input" placeholder="Search pages and actions... (Esc to close)" autocomplete="off">
                  <span class="gx-palette-badge">ESC</span>
                </div>
                <ul class="gx-palette-list">
                  <li class="gx-palette-item selected" onclick="location.pathname='/'">
                    <span>Home</span>
                    <span class="gx-palette-badge">Page</span>
                  </li>
                  <li class="gx-palette-item" onclick="document.dispatchEvent(new CustomEvent('gx-theme-toggle'))">
                    <span>Toggle Dark / Light Theme</span>
                    <span class="gx-palette-badge">Theme</span>
                  </li>
                </ul>
              </div>
            </div>
            """
        live_region = '<div class="gx-aria-live" aria-live="polite" aria-atomic="true" style="position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden;"></div>'
        extra_css = f"<style>{custom_css}</style>" if custom_css else ""
        runtime_script = f"<script>{STATIC_JS}</script>" if static_export else '<script src="/_gx/client.js" defer></script>'
        theme_init_script = '<script>(function(){try{var s=localStorage.getItem("gx-theme")||(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");if(s)document.documentElement.dataset.theme=s;}catch(e){}})();</script>'
        favicon_tag = '<link rel="icon" type="image/svg+xml" href="assets/favicon.svg">'
        return (
            "<!doctype html>"
            f'<html lang="en" dir="{direction}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="gx-view" content="{safe_view}">'
            f'<meta name="gx-event-cursor" content="{event_cursor}">'
            f"{theme_init_script}{favicon_tag}"
            f"<title>{safe_title}</title><style>{BASE_CSS}</style>{extra_css}"
            f"{runtime_script}"
            f'</head><body><main class="gx-shell" id="gx-root" data-gx-root>{body}</main>{inspector_html}{palette_html}{live_region}</body></html>'
        )

    def render_patch(
        self,
        title: str,
        root: Component,
        component_ids: set[str],
        *,
        state_context: object,
        csrf_token: str,
    ) -> list[dict[str, str]]:
        self.registry.validate(root)
        index: dict[str, Component] = {}

        def walk(node: Component) -> None:
            if node.id is not None:
                index[node.id] = node
            for child in getattr(node, "children", ()):
                walk(child)
            for attr in ("first", "second"):
                if hasattr(node, attr):
                    val = getattr(node, attr)
                    if isinstance(val, Component):
                        walk(val)

        walk(root)
        if "__page__" in component_ids:
            html = self.render_component(root, state_context, csrf_token)
            return [{"id": "gx-root", "html": html}]

        patches = []
        for component_id in sorted(component_ids):
            component = index.get(component_id)
            if component is not None:
                patches.append({
                    "id": component_id,
                    "html": self.render_component(component, state_context, csrf_token),
                })
        return patches


# --- Component Render Functions ---


def _render_child(
    child: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    return registry.render(child, state_context, csrf_token)


def render_text(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Text)
    if component.state_ref is not None:
        if state_context is None:
            raise RuntimeError("bound Text requires a StateContext")
        value = state_context.read(component.state_ref)
        raw = component.display_format.replace("{value}", str(value))
    else:
        raw = component.value or ""
    return f'<p class="gx-text"{_attrs(component)}>{escape(raw)}</p>'


def render_heading(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Heading)
    tag = f"h{component.level}"
    return f'<{tag}{_attrs(component)}>{escape(component.value)}</{tag}>'


def render_link(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Link)
    href = escape(component.href, quote=True)
    return f'<a class="gx-link" href="{href}"{_attrs(component)}>{escape(component.label)}</a>'


def render_divider(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Divider)
    return f'<hr class="gx-divider"{_attrs(component)}>'


def render_spacer(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Spacer)
    return f'<div class="gx-spacer" style="height:{component.size}px"{_attrs(component)}></div>'


def render_badge(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Badge)
    return f'<span class="gx-badge gx-badge-{component.variant}"{_attrs(component)}>{escape(component.label)}</span>'


def render_callout(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Callout)
    msg = component.message
    if component.binding_key and state_context is not None and hasattr(state_context, "read_bound"):
        val = state_context.read_bound(component.binding_scope, component.binding_key)
        if val is not None:
            msg = str(val)
    title_html = f"<h4>{escape(component.title)}</h4>" if component.title else ""
    return (
        f'<div class="gx-callout gx-callout-{component.variant}" role="alert"{_attrs(component)}>'
        f"{title_html}<p>{escape(msg)}</p></div>"
    )


def render_column(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Column)
    children = "".join(_render_child(child, registry, state_context, csrf_token) for child in component.children)
    return f'<div class="gx-column" style="gap:{component.gap}px"{_attrs(component)}>{children}</div>'


def render_row(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Row)
    styles = [f"gap:{component.gap}px"]
    justify = getattr(component, "justify", None)
    if justify:
        j_map = {
            "start": "flex-start",
            "end": "flex-end",
            "center": "center",
            "between": "space-between",
            "around": "space-around",
            "evenly": "space-evenly",
        }
        styles.append(f"justify-content:{j_map.get(justify, justify)}")
    align = getattr(component, "align", None)
    if align:
        a_map = {
            "start": "flex-start",
            "end": "flex-end",
            "center": "center",
            "stretch": "stretch",
            "baseline": "baseline",
        }
        styles.append(f"align-items:{a_map.get(align, align)}")
    style_attr = ";".join(styles)
    children = "".join(_render_child(child, registry, state_context, csrf_token) for child in component.children)
    return f'<div class="gx-row" style="{style_attr}"{_attrs(component)}>{children}</div>'


def render_grid(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Grid)
    children = "".join(_render_child(child, registry, state_context, csrf_token) for child in component.children)
    if isinstance(component.columns, dict):
        bp_styles = [f"gap:{component.gap}px;"]
        for bp, count in component.columns.items():
            bp_styles.append(f"--gx-cols-{bp}:{count};")
        default_cols = component.columns.get("sm", 1)
        bp_styles.append(f"grid-template-columns:repeat({default_cols}, 1fr);")
        style_str = "".join(bp_styles)
        return f'<div class="gx-grid gx-grid-responsive" style="{style_str}"{_attrs(component)}>{children}</div>'
    return f'<div class="gx-grid" style="grid-template-columns:repeat({component.columns}, 1fr);gap:{component.gap}px"{_attrs(component)}>{children}</div>'


def render_card(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Card)
    children = "".join(_render_child(child, registry, state_context, csrf_token) for child in component.children)
    return f'<section class="gx-card"{_attrs(component)}>{children}</section>'


def render_tab_item(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, TabItem)
    children = "".join(_render_child(child, registry, state_context, csrf_token) for child in component.children)
    return children


def render_tabs(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Tabs)
    tabs_header = []
    tabs_panes = []
    for idx, item in enumerate(component.children):
        active_cls = " active" if idx == component.active_index else ""
        tab_id = f"tab-{idx}"
        tabs_header.append(
            f'<button type="button" class="gx-tab-btn{active_cls}" data-gx-tab-target="{tab_id}">{escape(item.label)}</button>'
        )
        content = "".join(_render_child(child, registry, state_context, csrf_token) for child in item.children)
        tabs_panes.append(f'<div class="gx-tab-pane{active_cls}" data-gx-tab-pane="{tab_id}">{content}</div>')

    return (
        f'<div class="gx-tabs" data-gx-tabs{_attrs(component)}>'
        f'<div class="gx-tabs-header">{"".join(tabs_header)}</div>'
        f'<div class="gx-tabs-content">{"".join(tabs_panes)}</div>'
        "</div>"
    )


def render_modal(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Modal)
    safe_modal_id = escape(component.id or secrets.token_urlsafe(8), quote=True)
    children = "".join(_render_child(child, registry, state_context, csrf_token) for child in component.children)
    return (
        f'<div class="gx-modal-wrap"{_attrs(component)}>'
        f'<button type="button" class="gx-button gx-button-primary" data-gx-modal-open="{safe_modal_id}">{escape(component.trigger_label)}</button>'
        f'<div class="gx-modal-backdrop" data-gx-modal="{safe_modal_id}">'
        f'<div class="gx-modal-box">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">'
        f'<h3 style="margin:0;">{escape(component.title)}</h3>'
        f'<button type="button" class="gx-button gx-button-secondary" data-gx-modal-close style="padding:4px 10px;">&times;</button>'
        f"</div><div>{children}</div></div></div></div>"
    )


def render_input(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Input)
    value = state_context.read(component.state_ref) if state_context is not None else getattr(component.state_ref, "default", "")
    return (
        f'<div class="gx-field"{_attrs(component)}>'
        f'<label for="{escape(component.id or component.name, quote=True)}-control">{escape(component.label)}</label>'
        f'<input class="gx-input" id="{escape(component.id or component.name, quote=True)}-control" '
        f'name="{escape(component.name, quote=True)}" type="{component.input_type}" '
        f'value="{escape(str(value), quote=True)}" '
        f'placeholder="{escape(component.placeholder, quote=True)}">'
        "</div>"
    )


def render_textarea(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Textarea)
    value = state_context.read(component.state_ref) if state_context is not None else getattr(component.state_ref, "default", "")
    return (
        f'<div class="gx-field"{_attrs(component)}>'
        f'<label for="{escape(component.id or component.name, quote=True)}-control">{escape(component.label)}</label>'
        f'<textarea class="gx-textarea" id="{escape(component.id or component.name, quote=True)}-control" '
        f'name="{escape(component.name, quote=True)}" rows="{component.rows}" '
        f'placeholder="{escape(component.placeholder, quote=True)}">{escape(str(value))}</textarea>'
        "</div>"
    )


def render_select(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Select)
    current_val = str(state_context.read(component.state_ref)) if state_context is not None else str(getattr(component.state_ref, "default", ""))
    opts = []
    for val, lbl in component.options:
        selected = ' selected="selected"' if str(val) == current_val else ""
        opts.append(f'<option value="{escape(str(val), quote=True)}"{selected}>{escape(str(lbl))}</option>')
    return (
        f'<div class="gx-field"{_attrs(component)}>'
        f'<label for="{escape(component.id or component.name, quote=True)}-control">{escape(component.label)}</label>'
        f'<select class="gx-select" id="{escape(component.id or component.name, quote=True)}-control" '
        f'name="{escape(component.name, quote=True)}">{"".join(opts)}</select>'
        "</div>"
    )


def render_switch(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Switch)
    val = state_context.read(component.state_ref) if state_context is not None else getattr(component.state_ref, "default", False)
    checked = " checked" if val else ""
    safe_id = escape(component.id or component.name, quote=True)
    return (
        f'<div{_attrs(component)}>'
        f'<label class="gx-switch" for="{safe_id}-control">'
        f'<input id="{safe_id}-control" type="checkbox" name="{escape(component.name, quote=True)}" value="true"{checked}>'
        f'<span class="gx-switch-slider"></span>'
        f'<span>{escape(component.label)}</span></label></div>'
    )


def render_radio_group(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, RadioGroup)
    current_val = str(state_context.read(component.state_ref)) if state_context is not None else str(getattr(component.state_ref, "default", ""))
    radios = []
    for val, lbl in component.options:
        checked = " checked" if str(val) == current_val else ""
        radio_id = escape(f"{component.name}-{val}", quote=True)
        radios.append(
            f'<label class="gx-checkbox" for="{radio_id}">'
            f'<input type="radio" id="{radio_id}" name="{escape(component.name, quote=True)}" value="{escape(str(val), quote=True)}"{checked}>'
            f'{escape(str(lbl))}</label>'
        )
    return (
        f'<div class="gx-field gx-radio-group"{_attrs(component)}>'
        f'<label>{escape(component.label)}</label>'
        f'<div style="display:flex;gap:16px;flex-wrap:wrap;">{"".join(radios)}</div></div>'
    )


def render_checkbox(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Checkbox)
    if state_context is None:
        raise RuntimeError("Checkbox requires a StateContext")
    checked = " checked" if state_context.read(component.state_ref) else ""
    safe_id = escape(component.id or component.name, quote=True)
    return (
        f'<div{_attrs(component)}>'
        f'<label class="gx-checkbox" for="{safe_id}-control">'
        f'<input id="{safe_id}-control" type="checkbox" name="{escape(component.name, quote=True)}" value="true"{checked}>'
        f'{escape(component.label)}</label></div>'
    )


def render_button(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Button)
    disabled_attr = " disabled" if component.disabled else ""
    cmd_attr = f' data-gx-command="{escape(component.command, quote=True)}" data-gx-action-trigger="{escape(component.command, quote=True)}" data-gx-csrf="{escape(csrf_token or "", quote=True)}" data-csrf="{escape(csrf_token or "", quote=True)}"' if component.command else ""
    size_class = f" gx-button-{component.size}" if component.size and component.size != "md" else ""
    return f'<button class="gx-button gx-button-{component.variant}{size_class}" type="submit"{disabled_attr}{cmd_attr}{_attrs(component)}>{escape(component.label)}</button>'


def render_form(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Form)
    if csrf_token is None:
        raise RuntimeError("Form requires a CSRF token")
    action = "/_gx/commands/" + quote(component.command, safe="")
    children = "".join(_render_child(child, registry, state_context, csrf_token) for child in component.children)
    error = '<p class="gx-error" data-gx-error role="alert"></p>'
    return (
        f'<form class="gx-form" method="post" action="{escape(action, quote=True)}" '
        f'data-gx-command="{escape(component.command, quote=True)}"{_attrs(component)}>'
        f'<input type="hidden" name="_csrf" value="{escape(csrf_token, quote=True)}">'
        f'<input type="hidden" name="_gx_action_id" value="{escape(secrets.token_urlsafe(18), quote=True)}">'
        f'<input type="hidden" name="_gx_view_id" value="{escape(getattr(state_context, "view_id", "/"), quote=True)}">'
        f"{children}{error}</form>"
    )


def render_metric_card(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, MetricCard)
    trend_arrow = "↑" if component.trend == "up" else ("↓" if component.trend == "down" else "•")
    trend_html = (
        f'<span class="gx-trend-{component.trend}">{trend_arrow} {escape(component.change)}</span>'
        if component.change
        else ""
    )
    subtitle_html = f'<span style="color:var(--gx-text-muted)">{escape(component.subtitle)}</span>' if component.subtitle else ""
    anim_attr = ' data-gx-animate-number="true"' if getattr(component, "animate_number", False) else ""
    return (
        f'<div class="gx-metric"{_attrs(component)}>'
        f'<div class="gx-metric-title">{escape(component.title)}</div>'
        f'<div class="gx-metric-val gx-metric-value"{anim_attr}>{escape(component.value)}</div>'
        f'<div class="gx-metric-foot">{trend_html}{subtitle_html}</div>'
        "</div>"
    )


def render_table(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Table)
    headers = "".join(f"<th>{escape(str(col))}</th>" for col in component.columns)
    rows_html = []
    for row in component.rows:
        cells = "".join(f"<td>{escape(str(cell))}</td>" for cell in row)
        rows_html.append(f"<tr>{cells}</tr>")
    striped_cls = " striped" if component.striped else ""
    caption_html = f"<caption>{escape(component.caption)}</caption>" if component.caption else ""
    return (
        f'<div class="gx-table-wrap"{_attrs(component)}>'
        f'<table class="gx-table{striped_cls}">{caption_html}'
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table></div>"
    )


def render_plot(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Plot)
    labels = list(component.data.get("labels", []))
    values = list(component.data.get("values", []))
    if not labels or not values:
        items = component.data.get("items", [])
        if isinstance(items, list) and items:
            x_k = component.data.get("x_key", "x")
            y_k = component.data.get("y_key", "y")
            labels = [str(item.get(x_k, "")) if isinstance(item, dict) else str(item) for item in items]
            values = [float(item.get(y_k, 0)) if isinstance(item, dict) else float(item) for item in items]
    title_html = f'<div class="gx-plot-title">{escape(component.title)}</div>' if component.title else ""
    h = component.height
    w = 600

    if not labels or not values or len(labels) != len(values):
        return (
            f'<div class="gx-plot-card"{_attrs(component)}>{title_html}'
            f'<div style="height:{h}px;display:flex;align-items:center;justify-content:center;color:var(--gx-text-muted);">'
            'No data available</div></div>'
        )

    # Clean pure SVG renderer
    max_val = max(values) if values and max(values) > 0 else 1
    svg_body = ""

    if component.chart_type == "bar":
        n = len(values)
        bar_width = max(12, int((w - 80) / n - 12))
        x_start = 50
        svg_body += f'<line x1="40" y1="{h-30}" x2="{w-20}" y2="{h-30}" stroke="var(--gx-border-strong)" stroke-width="1"/>'
        for i, (lbl, val) in enumerate(zip(labels, values)):
            bx = x_start + i * (bar_width + 12)
            bh = int((val / max_val) * (h - 70))
            by = h - 30 - bh
            svg_body += (
                f'<rect x="{bx}" y="{by}" width="{bar_width}" height="{bh}" rx="4" fill="var(--gx-primary)">'
                f'<title>{escape(str(lbl))}: {val}</title></rect>'
                f'<text x="{bx + bar_width//2}" y="{h-12}" font-size="11" fill="var(--gx-text-muted)" text-anchor="middle">{escape(str(lbl)[:8])}</text>'
                f'<text x="{bx + bar_width//2}" y="{by - 6}" font-size="10" font-weight="600" fill="var(--gx-text)" text-anchor="middle">{val}</text>'
            )

    elif component.chart_type == "line":
        n = len(values)
        step_x = (w - 80) / max(1, n - 1)
        points = []
        svg_body += f'<line x1="40" y1="{h-30}" x2="{w-20}" y2="{h-30}" stroke="var(--gx-border-strong)" stroke-width="1"/>'
        for i, val in enumerate(values):
            px = 40 + i * step_x
            py = h - 30 - int((val / max_val) * (h - 70))
            points.append(f"{px:.1f},{py:.1f}")
        poly_pts = " ".join(points)
        svg_body += (
            f'<polyline points="{poly_pts}" fill="none" stroke="var(--gx-primary)" stroke-width="3" stroke-linecap="round"/>'
        )
        for i, (lbl, val) in enumerate(zip(labels, values)):
            px = 40 + i * step_x
            py = h - 30 - int((val / max_val) * (h - 70))
            svg_body += (
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="white" stroke="var(--gx-primary)" stroke-width="2"/>'
                f'<text x="{px:.1f}" y="{h-12}" font-size="11" fill="var(--gx-text-muted)" text-anchor="middle">{escape(str(lbl)[:8])}</text>'
            )

    else:
        # Fallback to bar representation
        svg_body += f'<text x="{w//2}" y="{h//2}" text-anchor="middle" fill="var(--gx-text)">{component.chart_type.title()} Chart</text>'

    svg = (
        f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:{h}px;overflow:visible;" xmlns="http://www.w3.org/2000/svg">'
        f"{svg_body}</svg>"
    )
    return f'<div class="gx-plot-card"{_attrs(component)}>{title_html}{svg}</div>'


def render_chat_message(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ChatMessage)
    role_cls = f"gx-chat-{component.role}"
    role_label = component.role.title()
    citations_html = ""
    if component.citations:
        c_list = ", ".join(f'<a class="gx-link" href="#">{escape(c)}</a>' for c in component.citations)
        citations_html = f'<div class="gx-chat-citations"><strong>Sources:</strong> {c_list}</div>'
    return (
        f'<div class="gx-chat-msg {role_cls}"{_attrs(component)}>'
        f'<div style="font-size:0.75rem;opacity:0.8;margin-bottom:4px;font-weight:600;">{role_label}</div>'
        f'<div>{escape(component.content)}</div>'
        f"{citations_html}</div>"
    )


def render_chat_view(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ChatView)
    messages_html = "".join(_render_child(c, registry, state_context, csrf_token) for c in component.children)
    return (
        f'<div class="gx-chat-box"{_attrs(component)}>'
        f'<div class="gx-chat-header">{escape(component.title)}</div>'
        f'<div class="gx-chat-messages">{messages_html}</div>'
        "</div>"
    )


def render_chat_input(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ChatInput)
    if csrf_token is None:
        raise RuntimeError("ChatInput requires a CSRF token")
    action = "/_gx/commands/" + quote(component.command, safe="")
    return (
        f'<form class="gx-form" method="post" action="{escape(action, quote=True)}" '
        f'data-gx-command="{escape(component.command, quote=True)}" style="display:flex;gap:8px;flex-direction:row;width:100%;"{_attrs(component)}>'
        f'<input type="hidden" name="_csrf" value="{escape(csrf_token, quote=True)}">'
        f'<input type="hidden" name="_gx_action_id" value="{escape(secrets.token_urlsafe(18), quote=True)}">'
        f'<input type="hidden" name="_gx_view_id" value="{escape(getattr(state_context, "view_id", "/"), quote=True)}">'
        f'<input class="gx-input" type="text" name="message" placeholder="{escape(component.placeholder, quote=True)}" required style="flex:1;">'
        f'<button class="gx-button gx-button-primary" type="submit">{escape(component.label)}</button>'
        "</form>"
    )


def render_streaming_text(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, StreamingText)
    if component.state_ref is not None:
        if state_context is None:
            raise RuntimeError("bound StreamingText requires a StateContext")
        value = state_context.read(component.state_ref)
        raw = str(value)
    else:
        raw = component.value or ""
    cursor_cls = " gx-stream-cursor" if component.cursor else ""
    return f'<div class="gx-text{cursor_cls}"{_attrs(component)} style="white-space:pre-wrap;">{escape(raw)}</div>'


def render_action_card(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ActionCard)
    safe_payload = escape(json.dumps(component.data), quote=True)
    status_badge = f'<span class="gx-badge gx-badge-warning">{component.status.title()}</span>'
    actions_html = ""
    if component.status == "pending" and csrf_token:
        approve_action = "/_gx/commands/" + quote(component.approve_command, safe="")
        actions_html = (
            f'<div style="display:flex;gap:8px;margin-top:12px;">'
            f'<form class="gx-form" method="post" action="{escape(approve_action, quote=True)}" data-gx-command="{escape(component.approve_command, quote=True)}" style="margin:0;">'
            f'<input type="hidden" name="_csrf" value="{escape(csrf_token, quote=True)}">'
            f'<input type="hidden" name="_gx_action_id" value="{escape(secrets.token_urlsafe(18), quote=True)}">'
            f'<input type="hidden" name="_gx_view_id" value="{escape(getattr(state_context, "view_id", "/"), quote=True)}">'
            f'<button type="submit" class="gx-button gx-button-primary">Approve</button>'
            f'</form>'
        )
        if component.reject_command:
            reject_action = "/_gx/commands/" + quote(component.reject_command, safe="")
            actions_html += (
                f'<form class="gx-form" method="post" action="{escape(reject_action, quote=True)}" data-gx-command="{escape(component.reject_command, quote=True)}" style="margin:0;">'
                f'<input type="hidden" name="_csrf" value="{escape(csrf_token, quote=True)}">'
                f'<input type="hidden" name="_gx_action_id" value="{escape(secrets.token_urlsafe(18), quote=True)}">'
                f'<input type="hidden" name="_gx_view_id" value="{escape(getattr(state_context, "view_id", "/"), quote=True)}">'
                f'<button type="submit" class="gx-button gx-button-secondary">Reject</button>'
                f'</form>'
            )
        actions_html += "</div>"
    return (
        f'<div class="gx-action-card"{_attrs(component)}>'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<strong>{escape(component.title)}</strong>{status_badge}</div>'
        f'<p style="margin:8px 0 0 0;font-size:0.92rem;">{escape(component.description)}</p>'
        f"{actions_html}</div>"
    )


def render_step_timeline(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, StepTimeline)
    items_html = []
    for title, status, detail in component.steps:
        color = "var(--gx-primary)" if status == "running" else ("var(--gx-success)" if status == "completed" else "var(--gx-border-strong)")
        badge_variant = "primary" if status == "running" else ("success" if status == "completed" else "neutral")
        items_html.append(
            f'<div class="gx-timeline-item">'
            f'<div class="gx-timeline-dot" style="background:{color};"></div>'
            f'<div style="display:flex;align-items:center;gap:8px;">'
            f'<strong>{escape(title)}</strong>'
            f'<span class="gx-badge gx-badge-{badge_variant}">{escape(status.title())}</span>'
            f'</div><p style="margin:4px 0 0 0;font-size:0.85rem;color:var(--gx-text-muted);">{escape(detail)}</p>'
            f"</div>"
        )
    return (
        f'<div class="gx-card"{_attrs(component)}>'
        f'<h4 style="margin:0 0 16px 0;">{escape(component.title)}</h4>'
        f'<div class="gx-timeline">{"".join(items_html)}</div>'
        f"</div>"
    )


def render_dynamic_card(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, DynamicCard)
    pretty = json.dumps(component.spec, indent=2)
    return (
        f'<div class="gx-card"{_attrs(component)}>'
        f'<h4>{escape(component.title or "Dynamic Card")}</h4>'
        f'<pre class="gx-job-result">{escape(pretty)}</pre>'
        f"</div>"
    )


def render_job_panel(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, JobPanel)
    if state_context is None:
        raise RuntimeError("JobPanel requires a StateContext")
    snapshot = component.job_handle.latest_snapshot(state_context.session_id)
    wrapper = f'<section class="gx-job-panel" aria-live="polite"{_attrs(component)}>'
    heading = f'<div class="gx-job-top"><strong>{escape(component.label)}</strong>'
    if snapshot is None:
        return (
            wrapper
            + heading
            + '<span class="gx-job-status">Not started</span></div>'
            '<p class="gx-job-message">No task has been submitted.</p></section>'
        )

    status = escape(snapshot.status.value.title())
    message = escape(snapshot.message)
    body = heading + f'<span class="gx-job-status">{status}</span></div>'
    body += f'<p class="gx-job-message">{message}</p>'
    if snapshot.progress is not None:
        body += (
            f'<progress class="gx-job-progress" max="100" value="{snapshot.progress}" '
            f'aria-label="Task progress">{snapshot.progress}%</progress>'
        )
        body += f'<p class="gx-job-status">{snapshot.progress}%</p>'
    if snapshot.result_text is not None:
        body += f'<pre class="gx-job-result">{escape(snapshot.result_text)}</pre>'
    if snapshot.error_type is not None:
        body += f'<p class="gx-error">Task failed ({escape(snapshot.error_type)}). Check server logs.</p>'
    if snapshot.status.value in {"queued", "running"} and csrf_token:
        endpoint = f"/_gx/jobs/{quote(snapshot.id, safe='')}/cancel"
        body += (
            f'<button class="gx-button gx-button-secondary" type="button" data-gx-job-cancel '
            f'data-endpoint="{escape(endpoint, quote=True)}" '
            f'data-csrf="{escape(csrf_token, quote=True)}">Cancel task</button>'
        )
    body += '<p class="gx-error" data-gx-job-error role="alert"></p>'
    return wrapper + body + "</section>"


def render_code_block(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, CodeBlock)
    code_id = f"gx-code-{secrets.token_hex(4)}"
    copy_btn = ""
    if component.copyable:
        copy_btn = (
            f'<button type="button" class="gx-code-copy-btn" data-gx-copy="{code_id}">'
            f'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
            f'<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>'
            f'<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>'
            f'</svg> Copy</button>'
        )
    title_text = component.title or component.language.upper()
    header_html = (
        f'<div class="gx-code-header">'
        f'<span>{escape(title_text)}</span>'
        f'{copy_btn}</div>'
    )
    code_text = component.code
    if component.show_line_numbers:
        lines = code_text.splitlines()
        formatted_lines = []
        for i, line in enumerate(lines, 1):
            formatted_lines.append(
                f'<span style="color:var(--gx-text-muted);user-select:none;display:inline-block;width:32px;text-align:right;margin-right:12px;">{i}</span>{escape(line)}'
            )
        display_code = "\n".join(formatted_lines)
    else:
        display_code = escape(code_text)

    return (
        f'<div class="gx-code-container"{_attrs(component)}>'
        f'{header_html}'
        f'<pre class="gx-code-body" id="{code_id}" data-gx-raw-code="{escape(code_text, quote=True)}"><code>{display_code}</code></pre>'
        f'</div>'
    )


def _render_tree_node(node: TreeNode, on_select_command: str, csrf_token: str | None) -> str:
    has_children = bool(node.children)
    caret_class = "gx-tree-caret expanded" if node.expanded else "gx-tree-caret"
    caret_html = (
        f'<span class="{caret_class}" data-gx-tree-toggle>▶</span>'
        if has_children
        else '<span style="width:16px;display:inline-block;"></span>'
    )
    icon_html = f'<span style="font-size:1rem;margin-right:4px;">{escape(node.icon)}</span>' if node.icon else ""
    row_class = "gx-tree-row selected" if node.selected else "gx-tree-row"

    action_attrs = ""
    if on_select_command:
        payload = json.dumps({"node_id": node.id, **node.data})
        action_attrs = (
            f' data-gx-action-trigger="{escape(on_select_command, quote=True)}"'
            f' data-action-payload="{escape(payload, quote=True)}"'
            f' data-csrf="{escape(csrf_token or "", quote=True)}"'
        )

    nested_html = ""
    if has_children:
        open_class = "gx-tree-nested open" if node.expanded else "gx-tree-nested"
        children_html = "".join(_render_tree_node(child, on_select_command, csrf_token) for child in node.children)
        nested_html = f'<ul class="{open_class}">{children_html}</ul>'

    return (
        f'<li class="gx-tree-item">'
        f'<div class="{row_class}"{action_attrs}>'
        f'{caret_html}{icon_html}<span>{escape(node.label)}</span>'
        f'</div>{nested_html}</li>'
    )


def render_tree_view(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, TreeView)
    items_html = "".join(_render_tree_node(node, component.on_select_command, csrf_token) for node in component.root_nodes)
    return (
        f'<div class="gx-tree-container"{_attrs(component)}>'
        f'<ul class="gx-tree-list">{items_html}</ul>'
        f'</div>'
    )


def render_data_grid(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, DataGrid)
    toolbar_html = ""
    if component.searchable:
        toolbar_html = (
            f'<div class="gx-grid-toolbar">'
            f'<input type="search" class="gx-grid-search-input" placeholder="Search records..." data-gx-grid-search />'
            f'<span data-gx-grid-total style="font-size:0.85rem;color:var(--gx-text-muted);">{len(component.rows)} items</span>'
            f'</div>'
        )

    headers_html = []
    for col_idx, h in enumerate(component.headers):
        sort_attr = f' data-gx-sort-col="{col_idx}"' if component.sortable else ""
        headers_html.append(f'<th{sort_attr}>{escape(str(h))}</th>')

    rows_html = []
    if not component.rows:
        rows_html.append(
            f'<tr><td colspan="{len(component.headers)}" style="text-align:center;padding:24px;color:var(--gx-text-muted);">{escape(component.empty_message)}</td></tr>'
        )
    else:
        for row in component.rows:
            tds = "".join(f'<td>{escape(str(val))}</td>' for val in row)
            rows_html.append(f'<tr>{tds}</tr>')

    total_pages = max(1, math.ceil(len(component.rows) / component.page_size))
    footer_html = (
        f'<div class="gx-grid-footer">'
        f'<span data-gx-grid-page-info>Page 1 of {total_pages}</span>'
        f'<div class="gx-grid-pagination">'
        f'<button type="button" class="gx-grid-page-btn" data-gx-grid-prev disabled>Previous</button>'
        f'<button type="button" class="gx-grid-page-btn" data-gx-grid-next{" disabled" if len(component.rows) <= component.page_size else ""}>Next</button>'
        f'</div>'
        f'</div>'
    )

    return (
        f'<div class="gx-grid-card"{_attrs(component)} data-gx-grid data-gx-page-size="{component.page_size}">'
        f'{toolbar_html}'
        f'<div class="gx-table-wrap">'
        f'<table class="gx-table striped">'
        f'<thead><tr>{"".join(headers_html)}</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table></div>'
        f'{footer_html}'
        f'</div>'
    )


def render_generative_slot(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, GenerativeSlot)
    inner_html = "".join(
        registry.render(child, state_context=state_context, csrf_token=csrf_token)
        for child in component.children
    )
    return (
        f'<div class="gx-generative-slot"{_attrs(component)} data-gx-slot="{escape(component.name, quote=True)}">'
        f'{inner_html}'
        f'</div>'
    )


def render_diagram(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Diagram)

    nodes = list(component.nodes)
    if component.layout == "vertical" or (nodes and all(n.x == 0.0 and n.y == 0.0 for n in nodes)):
        center_x = 400.0
        current_y = 40.0
        positioned_nodes = []
        for n in nodes:
            positioned_nodes.append(n.model_copy(update={
                "x": center_x - n.width / 2.0,
                "y": current_y,
            }))
            current_y += n.height + 50.0
        nodes = positioned_nodes

    node_map = {n.id: n for n in nodes}

    max_x = max(800.0, max((n.x + n.width + 40.0 for n in nodes), default=800.0))
    max_y = max(float(component.height), max((n.y + n.height + 40.0 for n in nodes), default=float(component.height)))

    edges_svg = []
    for edge in component.edges:
        s = node_map.get(edge.source)
        t = node_map.get(edge.target)
        if not s or not t:
            continue

        if t.y >= s.y + s.height - 5:
            sx, sy = s.x + s.width / 2.0, s.y + s.height
            tx, ty = t.x + t.width / 2.0, t.y
            dy = max(20.0, (ty - sy) / 2.0)
            d = f"M {sx:.1f} {sy:.1f} C {sx:.1f} {sy + dy:.1f}, {tx:.1f} {ty - dy:.1f}, {tx:.1f} {ty:.1f}"
        elif t.x >= s.x + s.width - 5:
            sx, sy = s.x + s.width, s.y + s.height / 2.0
            tx, ty = t.x, t.y + t.height / 2.0
            dx = max(20.0, (tx - sx) / 2.0)
            d = f"M {sx:.1f} {sy:.1f} C {sx + dx:.1f} {sy:.1f}, {tx - dx:.1f} {ty:.1f}, {tx:.1f} {ty:.1f}"
        elif s.y >= t.y + t.height - 5:
            sx, sy = s.x + s.width / 2.0, s.y
            tx, ty = t.x + t.width / 2.0, t.y + t.height
            dy = max(20.0, (sy - ty) / 2.0)
            d = f"M {sx:.1f} {sy:.1f} C {sx:.1f} {sy - dy:.1f}, {tx:.1f} {ty + dy:.1f}, {tx:.1f} {ty:.1f}"
        else:
            sx, sy = s.x, s.y + s.height / 2.0
            tx, ty = t.x + t.width, t.y + t.height / 2.0
            dx = max(20.0, (sx - tx) / 2.0)
            d = f"M {sx:.1f} {sy:.1f} C {sx - dx:.1f} {sy:.1f}, {tx + dx:.1f} {ty:.1f}, {tx:.1f} {ty:.1f}"

        edge_classes = ["gx-diagram-edge"]
        if edge.animated:
            edge_classes.append("gx-diagram-edge-animated")

        dash_attr = ""
        if edge.style == "dashed":
            dash_attr = ' stroke-dasharray="6 4"'
        elif edge.style == "dotted":
            dash_attr = ' stroke-dasharray="2 3"'

        color_attr = f' stroke="{escape(edge.color, quote=True)}"' if edge.color else ""
        marker_attr = ' marker-end="url(#gx-arrow)"' if edge.directional else ""

        edges_svg.append(f'<path d="{d}" class="{" ".join(edge_classes)}"{dash_attr}{color_attr}{marker_attr}/>')

        if edge.label:
            mid_x = (sx + tx) / 2.0
            mid_y = (sy + ty) / 2.0 - 6.0
            edges_svg.append(
                f'<text x="{mid_x:.1f}" y="{mid_y:.1f}" font-size="11" fill="var(--gx-text-muted)" text-anchor="middle">{escape(edge.label)}</text>'
            )

    nodes_svg = []
    status_colors = {
        "normal": {"fill": "var(--gx-surface)", "stroke": "var(--gx-border-strong)", "text": "var(--gx-text)"},
        "active": {"fill": "var(--gx-primary-subtle)", "stroke": "var(--gx-primary)", "text": "var(--gx-primary)"},
        "success": {"fill": "var(--gx-success-subtle)", "stroke": "var(--gx-success)", "text": "var(--gx-success)"},
        "warning": {"fill": "var(--gx-warning-subtle)", "stroke": "var(--gx-warning)", "text": "var(--gx-warning)"},
        "danger": {"fill": "var(--gx-danger-subtle)", "stroke": "var(--gx-danger)", "text": "var(--gx-danger)"},
        "muted": {"fill": "var(--gx-surface-alt)", "stroke": "var(--gx-border)", "text": "var(--gx-text-muted)"},
    }

    for node in nodes:
        colors = status_colors.get(node.status, status_colors["normal"])
        is_selected = component.selected_id == node.id
        stroke_width = "2.5" if is_selected else "1.5"
        stroke_color = "var(--gx-primary)" if is_selected else colors["stroke"]

        if node.kind == "pill":
            shape_svg = f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{node.width:.1f}" height="{node.height:.1f}" rx="{node.height / 2.0:.1f}" ry="{node.height / 2.0:.1f}" fill="{colors["fill"]}" stroke="{stroke_color}" stroke-width="{stroke_width}"/>'
        elif node.kind == "diamond":
            hw, hh = node.width / 2.0, node.height / 2.0
            cx, cy = node.x + hw, node.y + hh
            shape_svg = f'<polygon points="{cx:.1f},{node.y:.1f} {node.x + node.width:.1f},{cy:.1f} {cx:.1f},{node.y + node.height:.1f} {node.x:.1f},{cy:.1f}" fill="{colors["fill"]}" stroke="{stroke_color}" stroke-width="{stroke_width}"/>'
        elif node.kind == "database":
            shape_svg = (
                f'<g>'
                f'<rect x="{node.x:.1f}" y="{node.y + 10:.1f}" width="{node.width:.1f}" height="{node.height - 20:.1f}" fill="{colors["fill"]}" stroke="{stroke_color}" stroke-width="{stroke_width}"/>'
                f'<ellipse cx="{node.x + node.width/2:.1f}" cy="{node.y + 10:.1f}" rx="{node.width/2:.1f}" ry="10" fill="{colors["fill"]}" stroke="{stroke_color}" stroke-width="{stroke_width}"/>'
                f'<ellipse cx="{node.x + node.width/2:.1f}" cy="{node.y + node.height - 10:.1f}" rx="{node.width/2:.1f}" ry="10" fill="{colors["fill"]}" stroke="{stroke_color}" stroke-width="{stroke_width}"/>'
                f'</g>'
            )
        else:
            shape_svg = f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{node.width:.1f}" height="{node.height:.1f}" rx="10" ry="10" fill="{colors["fill"]}" stroke="{stroke_color}" stroke-width="{stroke_width}"/>'

        cx = node.x + node.width / 2.0
        cy = node.y + (node.height / 2.0 if not node.description else node.height / 2.0 - 8.0)

        icon_svg = ""
        if node.icon:
            icon_svg = f'<text x="{node.x + 18:.1f}" y="{node.y + node.height/2.0:.1f}" font-size="16" text-anchor="middle" dominant-baseline="central">{escape(node.icon)}</text>'

        label_svg = f'<text x="{cx:.1f}" y="{cy:.1f}" font-size="13" font-weight="600" fill="{colors["text"]}" text-anchor="middle" dominant-baseline="central">{escape(node.label)}</text>'

        desc_svg = ""
        if node.description:
            desc_svg = f'<text x="{cx:.1f}" y="{cy + 18.0:.1f}" font-size="11" fill="var(--gx-text-muted)" text-anchor="middle" dominant-baseline="central">{escape(node.description)}</text>'

        beacon_svg = ""
        if node.status == "active":
            beacon_svg = (
                f'<circle cx="{node.x + node.width - 12:.1f}" cy="{node.y + 12:.1f}" r="4" fill="var(--gx-primary)">'
                f'<animate attributeName="opacity" values="1;0.2;1" dur="1.2s" repeatCount="indefinite"/>'
                f'</circle>'
            )

        node_classes = ["gx-diagram-node"]
        action_attrs = ""
        if is_selected:
            node_classes.append("selected")
        if component.on_node_click:
            node_classes.append("clickable")
            payload = json.dumps({"node_id": node.id, **node.data})
            action_attrs = (
                f' data-gx-action-trigger="{escape(component.on_node_click, quote=True)}"'
                f' data-action-payload="{escape(payload, quote=True)}"'
                f' data-csrf="{escape(csrf_token or "", quote=True)}"'
            )

        nodes_svg.append(
            f'<g id="gx-node-{escape(node.id, quote=True)}" class="{" ".join(node_classes)}"{action_attrs}>'
            f'{shape_svg}{icon_svg}{label_svg}{desc_svg}{beacon_svg}'
            f'</g>'
        )

    return (
        f'<div class="gx-diagram-container"{_attrs(component)} style="height:{component.height}px;">'
        f'<svg class="gx-diagram-svg" viewBox="0 0 {max_x:.1f} {max_y:.1f}">'
        f'<defs>'
        f'<marker id="gx-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto-start-reverse">'
        f'<polygon points="0 1, 8 4, 0 7" fill="var(--gx-border-strong)"/>'
        f'</marker>'
        f'</defs>'
        f'{"".join(edges_svg)}'
        f'{"".join(nodes_svg)}'
        f'</svg>'
        f'</div>'
    )


def render_skeleton(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Skeleton)
    cls = f"gx-skeleton gx-skeleton-{component.shape}"
    if component.animated:
        cls += " gx-skeleton-shimmer"
    style = f"width:{component.width};height:{component.height};"
    return f'<div class="{cls}" style="{style}"{_attrs(component)} aria-hidden="true"></div>'


def render_empty_state(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, EmptyState)
    icon_html = f'<div class="gx-empty-icon">{escape(component.icon)}</div>' if component.icon else ""
    desc_html = f'<p class="gx-empty-desc">{escape(component.description)}</p>' if component.description else ""
    return (
        f'<div class="gx-empty-state"{_attrs(component)}>'
        f'{icon_html}'
        f'<h3 class="gx-empty-title">{escape(component.title)}</h3>'
        f'{desc_html}'
        f'</div>'
    )


def render_file_upload(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, FileUpload)
    accept_attr = f' accept="{escape(component.accept, quote=True)}"' if component.accept else ""
    multi_attr = " multiple" if component.multiple else ""
    field_id = escape(component.id or f"file-input-{secrets.token_hex(4)}", quote=True)
    return (
        f'<div class="gx-file-upload"{_attrs(component)} data-gx-upload-cmd="{escape(component.command, quote=True)}">'
        f'<input type="file" class="gx-file-input"{accept_attr}{multi_attr} id="{field_id}">'
        f'<label for="{field_id}" class="gx-file-dropzone">'
        f'<span class="gx-file-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg></span>'
        f'<span class="gx-file-label">{escape(component.label)}</span>'
        f'<span class="gx-file-subtext">Max size: {component.max_size_mb} MB</span>'
        f'</label>'
        f'<div class="gx-file-list" data-gx-file-list></div>'
        f'</div>'
    )


def render_virtual_list(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, VirtualList)
    items_json = escape(json.dumps(list(component.items)), quote=True)
    total_height = len(component.items) * component.item_height
    return (
        f'<div class="gx-virtual-list"{_attrs(component)} data-gx-virtual-items="{items_json}" '
        f'data-gx-item-height="{component.item_height}" style="height:{component.viewport_height}px;overflow-y:auto;position:relative;">'
        f'<div class="gx-virtual-spacer" style="height:{total_height}px;position:relative;">'
        f'<div class="gx-virtual-content" style="position:absolute;top:0;left:0;right:0;"></div>'
        f'</div>'
        f'</div>'
    )


def render_theme_toggle(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ThemeToggle)
    return (
        f'<button type="button" class="gx-theme-toggle gx-button gx-button-outline"{_attrs(component)} data-gx-theme-toggle>'
        f'<span class="gx-theme-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg></span> <span>{escape(component.label)}</span>'
        f'</button>'
    )


def render_error_boundary(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ErrorBoundary)
    attrs = _attrs(component)
    try:
        children_html = "".join(
            registry.render(child, state_context, csrf_token)
            for child in component.children
        )
        return f'<div class="gx-error-boundary-wrap"{attrs}>{children_html}</div>'
    except Exception as exc:
        msg = escape(component.fallback_message)
        return (
            f'<div class="gx-error-boundary"{attrs}>'
            f'<div class="gx-error-title">Component Error</div>'
            f'<p class="gx-error-message">{msg}</p>'
            f'<button type="button" class="gx-button gx-button-sm gx-button-secondary" onclick="location.reload()">Retry</button>'
            f'</div>'
        )


def render_toast(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Toast)
    title_html = f'<div class="gx-toast-title">{escape(component.title)}</div>' if component.title else ""
    close_btn = (
        '<button type="button" class="gx-toast-close" onclick="this.closest(\'.gx-toast\').remove()">&times;</button>'
        if component.dismissible
        else ""
    )
    return (
        f'<div class="gx-toast gx-toast-{component.variant}"{_attrs(component)} '
        f'data-gx-duration="{component.duration_ms}" role="status">'
        f'<div class="gx-toast-body">{title_html}<div class="gx-toast-msg">{escape(component.message)}</div></div>'
        f'{close_btn}'
        f'</div>'
    )


def render_toast_container(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ToastContainer)
    children_html = "".join(
        registry.render(child, state_context, csrf_token)
        for child in component.children
    )
    return f'<div class="gx-toast-container gx-toast-{component.position}"{_attrs(component)}>{children_html}</div>'


def render_tooltip(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Tooltip)
    children_html = "".join(
        registry.render(child, state_context, csrf_token)
        for child in component.children
    )
    return (
        f'<div class="gx-tooltip-wrapper"{_attrs(component)} tabindex="0">'
        f'{children_html}'
        f'<div class="gx-tooltip-content gx-tooltip-{component.position}" role="tooltip">{escape(component.content)}</div>'
        f'</div>'
    )


def render_popover(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Popover)
    children_html = "".join(
        registry.render(child, state_context, csrf_token)
        for child in component.children
    )
    title_html = f'<div class="gx-popover-header">{escape(component.title)}</div>' if component.title else ""
    return (
        f'<details class="gx-popover"{_attrs(component)}>'
        f'<summary class="gx-button gx-button-secondary">{escape(component.trigger_label)}</summary>'
        f'<div class="gx-popover-panel gx-popover-{component.placement}">'
        f'{title_html}'
        f'<div class="gx-popover-body">{children_html}</div>'
        f'</div>'
        f'</details>'
    )


def render_accordion_item(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, AccordionItem)
    open_attr = " open" if component.open else ""
    children_html = "".join(
        registry.render(child, state_context, csrf_token)
        for child in component.children
    )
    return (
        f'<details class="gx-accordion-item"{open_attr}{_attrs(component)}>'
        f'<summary class="gx-accordion-header">'
        f'<span>{escape(component.title)}</span>'
        f'<span class="gx-accordion-arrow">›</span>'
        f'</summary>'
        f'<div class="gx-accordion-content">{children_html}</div>'
        f'</details>'
    )


def render_accordion(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Accordion)
    items_html = "".join(
        registry.render(child, state_context, csrf_token)
        for child in component.children
    )
    return f'<div class="gx-accordion"{_attrs(component)}>{items_html}</div>'


def render_drawer(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Drawer)
    children_html = "".join(
        registry.render(child, state_context, csrf_token)
        for child in component.children
    )
    return (
        f'<div class="gx-drawer-container"{_attrs(component)}>'
        f'<button type="button" class="gx-button gx-button-secondary" data-gx-drawer-open>{escape(component.trigger_label)}</button>'
        f'<div class="gx-drawer-backdrop gx-drawer-{component.placement}">'
        f'<div class="gx-drawer-panel" role="dialog" aria-modal="true">'
        f'<div class="gx-drawer-header"><h3>{escape(component.title)}</h3><button type="button" class="gx-drawer-close" aria-label="Close">&times;</button></div>'
        f'<div class="gx-drawer-body">{children_html}</div>'
        f'</div></div></div>'
    )


def render_breadcrumb_item(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, BreadcrumbItem)
    label = escape(component.label)
    if component.active:
        return f'<li class="gx-breadcrumb-item gx-breadcrumb-active" aria-current="page"{_attrs(component)}>{label}</li>'
    if component.href:
        return f'<li class="gx-breadcrumb-item"{_attrs(component)}><a href="{escape(component.href, quote=True)}" class="gx-link">{label}</a></li>'
    return f'<li class="gx-breadcrumb-item"{_attrs(component)}><span>{label}</span></li>'


def render_breadcrumb(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Breadcrumb)
    items = []
    sep = escape(component.separator)
    for i, item in enumerate(component.items):
        item_html = registry.render(item, state_context, csrf_token)
        if i > 0:
            items.append(f'<li class="gx-breadcrumb-separator" aria-hidden="true">{sep}</li>')
        items.append(item_html)
    return f'<nav aria-label="Breadcrumb" class="gx-breadcrumb"{_attrs(component)}><ol class="gx-breadcrumb-list">{"".join(items)}</ol></nav>'


def render_pagination(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Pagination)
    cmd = escape(component.command, quote=True)
    prev_disabled = " disabled" if component.current_page <= 1 else ""
    next_disabled = " disabled" if component.current_page >= component.total_pages else ""
    return (
        f'<nav aria-label="Pagination" class="gx-pagination"{_attrs(component)} data-gx-pagination data-gx-cmd="{cmd}">'
        f'<button type="button" class="gx-button gx-button-sm gx-button-secondary gx-pagination-prev"{prev_disabled} data-page="{component.current_page - 1}">‹ Prev</button>'
        f'<span class="gx-pagination-info">Page {component.current_page} of {component.total_pages}</span>'
        f'<button type="button" class="gx-button gx-button-sm gx-button-secondary gx-pagination-next"{next_disabled} data-page="{component.current_page + 1}">Next ›</button>'
        f'</nav>'
    )


def render_progress_bar(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ProgressBar)
    pct = min(100.0, max(0.0, (component.value / component.max_value) * 100.0))
    striped = " gx-progress-striped" if component.striped else ""
    animated = " gx-progress-animated" if component.animated else ""
    label_text = escape(component.label) if component.label else f"{pct:.0f}%" if pct > 10 else ""
    return (
        f'<div class="gx-progress-wrap"{_attrs(component)}>'
        f'<div class="gx-progress-bar gx-progress-{component.variant}{striped}{animated}" '
        f'role="progressbar" aria-valuenow="{component.value}" aria-valuemin="0" '
        f'aria-valuemax="{component.max_value}" style="width:{pct:.1f}%">{label_text}</div>'
        f'</div>'
    )


def render_progress_circle(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, ProgressCircle)
    size = component.size
    stroke = component.stroke_width
    radius = (size - stroke) / 2
    circumference = 2 * math.pi * radius
    pct = min(100.0, max(0.0, component.value))
    offset = circumference - (pct / 100.0) * circumference
    label = escape(component.label) if component.label else f"{pct:.0f}%"
    color_var = f"var(--gx-{component.variant})"
    return (
        f'<div class="gx-progress-circle"{_attrs(component)} style="width:{size}px;height:{size}px;">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" class="gx-progress-circle-svg">'
        f'<circle cx="{size/2}" cy="{size/2}" r="{radius}" fill="none" stroke="var(--gx-border)" stroke-width="{stroke}"></circle>'
        f'<circle cx="{size/2}" cy="{size/2}" r="{radius}" fill="none" stroke="{color_var}" stroke-width="{stroke}" '
        f'stroke-dasharray="{circumference:.2f}" stroke-dashoffset="{offset:.2f}" stroke-linecap="round" '
        f'transform="rotate(-90 {size/2} {size/2})" style="transition: stroke-dashoffset 0.35s ease;"></circle>'
        f'</svg>'
        f'<span class="gx-progress-circle-text">{label}</span>'
        f'</div>'
    )


def render_avatar(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Avatar)
    initials = "".join(word[0].upper() for word in component.name.split()[:2]) if component.name else "?"
    img_html = f'<img src="{escape(component.src, quote=True)}" alt="{escape(component.name, quote=True)}">' if component.src else f'<span class="gx-avatar-initials">{escape(initials)}</span>'
    status_html = f'<span class="gx-avatar-status gx-avatar-status-{component.status}"></span>' if component.status else ""
    return (
        f'<div class="gx-avatar gx-avatar-{component.size}"{_attrs(component)} title="{escape(component.name, quote=True)}">'
        f'{img_html}{status_html}'
        f'</div>'
    )


def render_avatar_group(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, AvatarGroup)
    visible = component.children[:component.max_visible]
    overflow = len(component.children) - component.max_visible
    rendered = [registry.render(av, state_context, csrf_token) for av in visible]
    if overflow > 0:
        rendered.append(f'<div class="gx-avatar gx-avatar-md gx-avatar-more">+{overflow}</div>')
    return f'<div class="gx-avatar-group"{_attrs(component)}>{"".join(rendered)}</div>'


def render_date_picker(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, DatePicker)
    current_value = ""
    if state_context is not None and hasattr(state_context, "get"):
        current_value = state_context.get(component.binding_scope, component.binding_key) or ""
    safe_val = escape(str(current_value), quote=True)
    min_attr = f' min="{escape(component.min_date, quote=True)}"' if component.min_date else ""
    max_attr = f' max="{escape(component.max_date, quote=True)}"' if component.max_date else ""
    return (
        f'<div class="gx-field"{_attrs(component)}>'
        f'<label>{escape(component.label)}</label>'
        f'<input type="date" class="gx-input" name="{escape(component.name, quote=True)}" value="{safe_val}"'
        f'{min_attr}{max_attr} data-gx-bound data-gx-bind-key="{escape(component.binding_key, quote=True)}" '
        f'data-gx-bind-scope="{escape(component.binding_scope, quote=True)}">'
        f'</div>'
    )


def render_time_picker(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, TimePicker)
    current_value = ""
    if state_context is not None and hasattr(state_context, "get"):
        current_value = state_context.get(component.binding_scope, component.binding_key) or ""
    safe_val = escape(str(current_value), quote=True)
    return (
        f'<div class="gx-field"{_attrs(component)}>'
        f'<label>{escape(component.label)}</label>'
        f'<input type="time" class="gx-input" name="{escape(component.name, quote=True)}" value="{safe_val}" '
        f'data-gx-bound data-gx-bind-key="{escape(component.binding_key, quote=True)}" '
        f'data-gx-bind-scope="{escape(component.binding_scope, quote=True)}">'
        f'</div>'
    )


def render_slider(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Slider)
    current_value = component.min_value
    if state_context is not None and hasattr(state_context, "get"):
        val = state_context.get(component.binding_scope, component.binding_key)
        if val is not None:
            try:
                current_value = float(val)
            except (ValueError, TypeError):
                pass
    return (
        f'<div class="gx-field gx-slider-field"{_attrs(component)}>'
        f'<label>{escape(component.label)}: <span class="gx-slider-val">{current_value}</span></label>'
        f'<input type="range" class="gx-slider" min="{component.min_value}" max="{component.max_value}" '
        f'step="{component.step}" name="{escape(component.name, quote=True)}" value="{current_value}" '
        f'data-gx-bound data-gx-bind-key="{escape(component.binding_key, quote=True)}" '
        f'data-gx-bind-scope="{escape(component.binding_scope, quote=True)}" '
        f'oninput="this.previousElementSibling.querySelector(\'.gx-slider-val\').textContent = this.value">'
        f'</div>'
    )


def render_split_panel(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, SplitPanel)
    first_html = registry.render(component.first, state_context, csrf_token)
    second_html = registry.render(component.second, state_context, csrf_token)
    return (
        f'<div class="gx-split-panel gx-split-{component.direction}"{_attrs(component)} style="--gx-split-ratio:{component.initial_ratio}">'
        f'<div class="gx-split-pane-1">{first_html}</div>'
        f'<div class="gx-split-handle" role="separator"></div>'
        f'<div class="gx-split-pane-2">{second_html}</div>'
        f'</div>'
    )


def render_dropdown_menu_item(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, DropdownMenuItem)
    danger_class = " gx-dropdown-item-danger" if component.danger else ""
    icon_html = f'<span class="gx-dropdown-icon">{escape(component.icon)}</span> ' if component.icon else ""
    label = escape(component.label)
    if component.href:
        return f'<a href="{escape(component.href, quote=True)}" class="gx-dropdown-item{danger_class}"{_attrs(component)}>{icon_html}{label}</a>'
    cmd_attr = f' data-gx-cmd="{escape(component.command, quote=True)}"' if component.command else ""
    return f'<button type="button" class="gx-dropdown-item{danger_class}"{cmd_attr}{_attrs(component)}>{icon_html}{label}</button>'


def render_dropdown_menu(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, DropdownMenu)
    items_html = "".join(
        registry.render(item, state_context, csrf_token)
        for item in component.items
    )
    return (
        f'<details class="gx-dropdown"{_attrs(component)}>'
        f'<summary class="gx-button gx-button-secondary">{escape(component.trigger_label)} ▾</summary>'
        f'<div class="gx-dropdown-menu">{items_html}</div>'
        f'</details>'
    )


def render_kbd(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Kbd)
    keys_html = "".join(f'<kbd>{escape(k)}</kbd>' for k in component.keys)
    return f'<span class="gx-kbd"{_attrs(component)}>{keys_html}</span>'


def render_container(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Container)
    margin = "0 auto" if component.centered else "0"
    children_html = "".join(
        registry.render(child, state_context, csrf_token)
        for child in component.children
    )
    return f'<div class="gx-container"{_attrs(component)} style="max-width:{escape(component.max_width, quote=True)};margin:{margin};">{children_html}</div>'


def render_stack(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Stack)
    children_html = "".join(
        registry.render(child, state_context, csrf_token)
        for child in component.children
    )
    return (
        f'<div class="gx-stack gx-stack-{component.direction} gx-stack-align-{component.align}"{_attrs(component)} '
        f'style="gap:{component.gap}px;">{children_html}</div>'
    )


def render_tag(
    component: Component, registry: ComponentRegistry, state_context: object | None, csrf_token: str | None
) -> str:
    assert isinstance(component, Tag)
    remove_btn = ""
    if component.removable:
        cmd_attr = f' data-gx-cmd="{escape(component.remove_command, quote=True)}"' if component.remove_command else ' onclick="this.closest(\'.gx-tag\').remove()"'
        remove_btn = f'<button type="button" class="gx-tag-remove"{cmd_attr} aria-label="Remove">&times;</button>'
    return (
        f'<span class="gx-tag gx-tag-{component.variant}"{_attrs(component)}>'
        f'<span>{escape(component.label)}</span>{remove_btn}'
        f'</span>'
    )
