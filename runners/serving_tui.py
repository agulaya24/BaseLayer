#!/usr/bin/env python3
"""
Serving TUI — Visual debugger for the behavioral diff cascade.

Thin wrapper around serving_engine.py. Displays results in a 3x3 grid
with live updates as each step completes.

Usage:
    python runners/serving_tui.py

Requires: pip install textual anthropic openai sentence-transformers
"""

import sys
import logging
import traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

import argparse

from serving_engine import (
    load_spec, load_facts, EmbeddingStore, run_cascade, OUTPUT_DIR,
    resolve_subject_paths,
)
import anthropic

# File-based error logging
LOG_FILE = OUTPUT_DIR / "tui_errors.log"
logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.ERROR,
    format="%(asctime)s %(levelname)s %(message)s",
)

from textual.app import App, ComposeResult
from textual.widgets import Static, Header, Footer, Input, RichLog
from textual.containers import Horizontal, Vertical, Container
from textual import work


TCSS = """
Screen {
    layout: grid;
    grid-size: 1;
    grid-rows: auto 1fr auto;
}

#input-area {
    height: 3;
    padding: 0 1;
}

#input-box {
    width: 100%;
}

#main-area {
    height: 1fr;
}

.row {
    height: 1fr;
    layout: horizontal;
}

.row-spec {
    height: auto;
    max-height: 10;
}

.row > .panel {
    width: 1fr;
}

.panel {
    border: solid $accent;
    padding: 0 1;
    overflow-y: auto;
}

#panel-mem0-facts { border: solid $error; }
#panel-bl-facts { border: solid $success; }
#panel-divergence { border: solid $warning; }
#panel-mem0-response { border: solid $error; }
#panel-bl-response { border: solid $success; }
#panel-merged-response { border: solid $warning; }

#panel-spec-activation {
    column-span: 3;
    height: auto;
    max-height: 10;
    border: solid $accent;
    padding: 0 1;
}

.panel-title-mem0 { text-style: bold; color: $error; }
.panel-title-bl { text-style: bold; color: $success; }
.panel-title-delta { text-style: bold; color: $warning; }
.panel-title-spec { text-style: bold; color: $accent; }
"""


ALL_LOGS = [
    "mem0-facts-log", "bl-facts-log", "divergence-log",
    "mem0-response-log", "bl-response-log", "merged-response-log",
    "spec-activation-log",
]


class ServingTUI(App):
    CSS = TCSS
    TITLE = "Base Layer - Serving Layer Debugger"
    BINDINGS = [("q", "quit", "Quit"), ("ctrl+l", "clear", "Clear")]

    def __init__(self, subject=None):
        super().__init__()
        self.claude = anthropic.Anthropic()
        self.subject = subject
        self.spec = None
        self.store = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Input(placeholder="Type a statement and press Enter...", id="input-box"),
            id="input-area",
        )
        yield Vertical(
            # Row 1: Retrieval
            Horizontal(
                Vertical(
                    Static("MEM0 RETRIEVAL", classes="panel-title-mem0"),
                    RichLog(id="mem0-facts-log", markup=True, wrap=True),
                    id="panel-mem0-facts", classes="panel",
                ),
                Vertical(
                    Static("DIVERGENCE", classes="panel-title-delta"),
                    RichLog(id="divergence-log", markup=True, wrap=True),
                    id="panel-divergence", classes="panel",
                ),
                Vertical(
                    Static("BASE LAYER RETRIEVAL", classes="panel-title-bl"),
                    RichLog(id="bl-facts-log", markup=True, wrap=True),
                    id="panel-bl-facts", classes="panel",
                ),
                classes="row",
            ),
            # Row 2: Spec activation
            Vertical(
                Static("SPEC ACTIVATION", classes="panel-title-spec"),
                RichLog(id="spec-activation-log", markup=True, wrap=True),
                id="panel-spec-activation", classes="panel row-spec",
            ),
            # Row 3: Three response conditions
            Horizontal(
                Vertical(
                    Static("MEM0 RESPONSE", classes="panel-title-mem0"),
                    RichLog(id="mem0-response-log", markup=True, wrap=True),
                    id="panel-mem0-response", classes="panel",
                ),
                Vertical(
                    Static("BASE LAYER RESPONSE", classes="panel-title-bl"),
                    RichLog(id="bl-response-log", markup=True, wrap=True),
                    id="panel-bl-response", classes="panel",
                ),
                Vertical(
                    Static("MERGED (SPEC + ALL FACTS)", classes="panel-title-delta"),
                    RichLog(id="merged-response-log", markup=True, wrap=True),
                    id="panel-merged-response", classes="panel",
                ),
                classes="row",
            ),
            id="main-area",
        )
        yield Footer()

    async def on_mount(self):
        self.load_data_async()

    @work(thread=True)
    def load_data_async(self):
        status = self.query_one("#divergence-log", RichLog)
        try:
            subject_label = self.subject or "default"
            status.write(f"[bold]Loading subject: {subject_label}...[/bold]")

        layers_dir, db_file, cache_dir = resolve_subject_paths(self.subject)
        self.spec = load_spec(layers_dir)
        facts = load_facts(db_file)
        status.write(f"Spec: ~{int(len(self.spec.split()) * 1.3)} tokens | Facts: {len(facts)}")

        self.store = EmbeddingStore(facts)
        self.store.load(on_status=lambda m: status.write(f"[dim]{m}[/dim]"), cache_dir=cache_dir)

            status.clear()
            status.write("[bold green]Ready.[/bold green] Type a statement above.")
        except Exception as e:
            err_msg = traceback.format_exc()
            logging.error(f"Startup failed:\n{err_msg}")
            status.write(f"[bold red]STARTUP ERROR: {e}[/bold red]")
            status.write(f"[dim]Full trace logged to {LOG_FILE}[/dim]")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        statement = event.value.strip()
        if not statement:
            return
        for log_id in ALL_LOGS:
            self.query_one(f"#{log_id}", RichLog).clear()
        self.query_one("#input-box", Input).value = ""
        self.run_cascade(statement)

    @work(thread=True)
    def run_cascade(self, statement: str):
        div_log = self.query_one("#divergence-log", RichLog)
        try:
            result = run_cascade(
                statement, self.spec, self.store, self.claude,
                on_status=lambda m: div_log.write(f"[dim]{m}[/dim]"),
                on_behavioral_query=lambda q: self._on_behavioral_query(q, statement),
                on_mem0_facts=lambda facts: self._show_facts("#mem0-facts-log", facts, "red"),
                on_bl_facts=lambda facts: self._show_facts("#bl-facts-log", facts, "green"),
                on_divergence=lambda d: self._show_divergence_data(d),
                on_spec_activation=lambda a: self._show_activation_text(a),
                on_mem0_response=lambda r: self._show_response("#mem0-response-log", r),
                on_bl_response=lambda r: self._show_response("#bl-response-log", r),
                on_merged_response=lambda r: self._show_response("#merged-response-log", r),
            )
            self._show_word_counts(result)
        except Exception as e:
            err_msg = traceback.format_exc()
            logging.error(f"Cascade failed for '{statement}':\n{err_msg}")
            div_log.write(f"[bold red]ERROR: {e}[/bold red]")
            div_log.write(f"[dim]Full trace logged to {LOG_FILE}[/dim]")

    def _on_behavioral_query(self, query, statement):
        log = self.query_one("#divergence-log", RichLog)
        log.write(f"[bold]Raw:[/bold] {statement}")
        log.write(f"[bold]Behavioral:[/bold] [green]{query}[/green]")
        log.write("")

    def _show_facts(self, log_id, facts, color):
        log = self.query_one(log_id, RichLog)
        for f in facts[:10]:
            sim = f"[dim]{f['similarity']:.3f}[/dim]"
            pred = f"[{color}][{f['predicate']}][/{color}] " if f.get("predicate") else ""
            log.write(f"{sim} {pred}{f['fact_text']}")

    def _show_divergence_data(self, d):
        log = self.query_one("#divergence-log", RichLog)
        log.write(f"[bold yellow]{d['only_mem0']+d['only_bl']}/{d['total_unique']} facts differ[/bold yellow]")
        log.write(f"Shared: {d['shared']} | Mem0: [red]{d['only_mem0']}[/red] | BL: [green]{d['only_bl']}[/green]")

        if d.get("only_mem0_snippets"):
            log.write("")
            log.write("[red]Mem0 only:[/red]")
            for s in d["only_mem0_snippets"]:
                log.write(f"  [dim]{s}[/dim]")
        if d.get("only_bl_snippets"):
            log.write("")
            log.write("[green]BL only:[/green]")
            for s in d["only_bl_snippets"]:
                log.write(f"  [dim]{s}[/dim]")

    def _show_activation_text(self, activation_raw):
        log = self.query_one("#spec-activation-log", RichLog)
        for line in activation_raw.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                parts = line.split(":", 1)
                name = parts[0].strip()
                reason = parts[1].strip() if len(parts) > 1 else ""
                log.write(f"[bold cyan]{name}[/bold cyan]: {reason}")
            else:
                log.write(f"[dim]{line}[/dim]")

    def _show_response(self, log_id, response):
        log = self.query_one(log_id, RichLog)
        log.write(response)

    def _show_word_counts(self, result):
        log = self.query_one("#divergence-log", RichLog)
        dl = result["delta"]
        log.write("")
        log.write(f"[bold]Words:[/bold] Mem0=[red]{dl['mem0_words']}[/red] BL=[green]{dl['bl_words']}[/green] Merged=[yellow]{dl['merged_words']}[/yellow]")
        log.write(f"[dim]{result.get('output_file', '')}[/dim]")

    def action_clear(self):
        for log_id in ALL_LOGS:
            self.query_one(f"#{log_id}", RichLog).clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serving Layer TUI")
    parser.add_argument("--subject", default=None, help="Subject name (e.g. buffett, marks)")
    args = parser.parse_args()
    app = ServingTUI(subject=args.subject)
    app.run()
