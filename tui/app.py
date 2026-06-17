# Auto-extracted from scripts/eve-tui during v3.1 Part 2 §2.3.
"""Eve TUI App class. Imported and run by scripts/eve-tui."""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Coroutine
from contextlib import suppress
from pathlib import Path
from typing import Any, ClassVar, Literal, cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    SelectionList,
    Static,
    TextArea,
)
from textual.widgets.selection_list import Selection

from tui.commands import (
    bundle_make_args,
    catalog_options,
    create_instance_args,
    instance_ip,
    instance_observe_view,
    instance_statuses,
    instance_rows,
    make_args,
    package_make_args,
    provider_dispatch_args,
    provider_dispatch_provider_args,
    provider_has_capability,
    provider_pane_data,
    provider_status_table,
    upload_folders,
)
from tui.render import (
    command_label,
    display_state,
    format_aggregate,
    glyph_for_status,
    markup_for_status,
    package_source_label,
    package_summary_label,
    plain_log_line,
)
from tui.settings import load_missing_fields
from tui.state import (
    action_allowed_for_instance,
    aggregate_summary,
    password_supported,
    provider_actions_available,
    status_instance_name,
)
from tui.widgets import (
    ChoiceScreen,
    ConfirmScreen,
    DeleteConfirmScreen,
    FirstRunScreen,
    NewInstanceScreen,
    PluginSourcesScreen,
    ProviderConfigScreen,
    ProviderPane,
    SettingsScreen,
    UploadScreen,
)

ROOT = Path(__file__).resolve().parents[1]

NEW_INSTANCE_KEY = "__new_instance__"
PACKAGE_ACTION_BUTTONS = 9
PROVIDER_ACTION_BUTTONS = 5
APP_NAME = "Eve"
APP_EXPANSION = "Ephemeral VM Environment"
APP_TAGLINE = "create -> provision -> connect"


class EveTui(App[None]):
    """Instance-first manager built on the existing v3 command surface."""

    CSS = """
    Screen {
        background: $background;
        color: $text;
    }

    #root {
        height: 1fr;
        layout: vertical;
    }

    #root.busy #hero,
    #root.busy #body {
        display: none;
    }

    #root.busy #summary {
        background: $warning 20%;
    }

    #busy-cancel-command {
        width: 100%;
        margin: 0 1;
    }

    #root.busy #output {
        height: 1fr;
        border: round $accent;
    }

    #root.busy #output-help {
        height: 2;
        color: $text;
        background: $warning 20%;
    }

    #hero {
        height: 1;
        padding: 0 1;
        background: $primary 15%;
    }

    #summary {
        height: 1;
        padding: 0 1;
        background: $surface;
    }

    #body {
        height: 2fr;
    }

    #left {
        width: 58;
        min-width: 52;
        border-right: solid $primary;
        padding: 1;
    }

    #refresh {
        margin-bottom: 1;
    }

    #provider-pane {
        height: 7;
        margin-bottom: 1;
    }

    #right {
        width: 1fr;
        padding: 1;
    }

    #empty-state {
        height: 1fr;
        content-align: center middle;
        border: round $primary;
        background: black;
        color: white;
    }

    #instance-detail {
        height: 1fr;
        display: none;
    }

    #state-strip {
        height: 4;
        margin-bottom: 1;
    }

    #detail-tabs {
        height: 3;
        margin-bottom: 1;
        background: transparent;
    }

    #detail-tabs Button {
        width: 1fr;
        min-width: 12;
    }

    #overview-tab,
    #packages-tab,
    #ops-tab {
        height: 1fr;
    }

    #action-groups {
        height: 1fr;
        margin-bottom: 1;
    }

    .action-group {
        width: 1fr;
    }

    .action-title {
        height: 1;
        color: $text-muted;
    }

    #remote-strip,
    #lifecycle-strip,
    #utility-strip,
    #provider-debug-strip,
    #package-actions,
    #bundle-actions,
    #danger-strip {
        layout: grid;
        grid-gutter: 1;
        background: transparent;
    }

    #remote-strip {
        grid-size: 5 2;
        grid-columns: 1fr 1fr 1fr 1fr 1fr;
        grid-rows: 3 3;
        height: 7;
    }

    #instance-actions-group {
        height: 4;
    }

    #utility-actions-group {
        height: 8;
    }

    #package-actions-group {
        height: 8;
    }

    #lifecycle-strip {
        grid-size: 4 1;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-rows: 3;
        height: 3;
    }

    #utility-strip,
    #provider-debug-strip {
        grid-size: 4 2;
        grid-columns: 1fr 1fr 1fr 1fr;
        grid-rows: 3 3;
        height: 7;
    }

    #package-actions {
        grid-size: 3 2;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 3 3;
        height: 7;
    }

    #bundle-actions,
    #danger-strip {
        grid-size: 3 1;
        grid-columns: 1fr 1fr 1fr;
        grid-rows: 3;
        height: 3;
    }

    #detail-grid {
        height: 1fr;
    }

    #danger-strip {
        margin-top: 1;
    }

    #packages-pane {
        width: 1fr;
    }

    #bundles {
        height: 8;
        margin-bottom: 1;
    }

    #bundle-actions {
        margin-bottom: 1;
    }

    #packages {
        height: 1fr;
    }

    #output {
        height: 16;
        border-top: solid $primary;
        padding: 1;
        background: $boost;
    }

    #output-help {
        height: 1;
        color: $text-muted;
        background: $boost;
        padding: 0 1;
    }

    #output:focus {
        border-top: solid $accent;
    }

    TextArea#output {
        background: $boost;
    }

    .section-title {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }

    .pill {
        width: 1fr;
        content-align: center middle;
        border: round $primary;
        margin-right: 1;
    }

    Button {
        width: 1fr;
        min-width: 9;
        height: 3;
    }
    """

    BINDINGS: ClassVar[list[Binding | tuple[str, str] | tuple[str, str, str]]] = [
        Binding("?", "help", "Help", show=True),
        Binding("h", "toggle_hidden", "Hidden"),
        Binding("r", "queue_refresh", "Refresh"),
        Binding("u", "queue_provider('up')", "Up"),
        Binding("t", "queue_provider('stop')", "Stop"),
        Binding("p", "queue_provision", "Provision"),
        Binding("x", "down_instance", "Down"),
        Binding("d", "delete_instance", "Delete Local Entry"),
        Binding("c", "queue_cancel_command", "Cancel", priority=True),
        Binding("ctrl+c", "queue_cancel_command", "Cancel", priority=True),
        Binding("escape", "queue_cancel_command", "Cancel"),
        Binding("l", "focus_log", "Log", priority=True),
        Binding("y", "copy_log", "Copy Log", priority=True),
        Binding("ctrl+y", "copy_log", "Copy Log", priority=True),
        Binding("q", "quit", "Quit"),
        Binding("s", "open_settings", "Settings"),
        Binding("g", "open_plugins", "Plugins"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.instances: list[dict[str, Any]] = []
        self.statuses: dict[str, dict[str, Any]] = {}
        self.catalog_options: dict[str, Any] = {"providers": [], "platforms": [], "bundles": [], "packages": []}
        self.current_instance: str | None = None
        self.current_bundle: str | None = None
        self.current_package: str | None = None
        self.current_status: dict[str, Any] | None = None
        self.command_running = False
        self.current_command_label: str | None = None
        self.current_process: asyncio.subprocess.Process | None = None
        self.current_provider_actions: list[dict[str, Any]] = []
        self.current_remote_actions: list[dict[str, Any]] = []
        self.instance_ips: dict[str, str] = {}
        self.background_tasks: set[asyncio.Task[None]] = set()
        self._copy_selection_timer: Any = None
        self.hero_frame = 0
        self._eye_blinking = False
        self._rendering_instances = False
        self._detail_refresh_seq = 0
        self._status_refreshing: set[str] = set()
        self._list_status_task: asyncio.Task[None] | None = None
        self._cached_aggregate: dict[str, int] = {"running": 0, "stopped": 0, "failed": 0, "other": 0}
        self.detail_tab = "overview"
        self.show_disabled = False
        self._provider_pane_data: list[dict[str, Any]] = []
        self._provider_reachability: dict[str, bool] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="root"):
            yield Static(
                f"[primary]◇[/] {APP_NAME}  [dim]{APP_EXPANSION}[/]  "
                f"[success]starting[/]  [dim]{APP_TAGLINE}[/dim]",
                id="hero",
            )
            yield Static("Loading instances...", id="summary")
            yield Button("Cancel Running Command", id="busy-cancel-command", variant="error")
            with Horizontal(id="body"):
                with Vertical(id="left"):
                    yield Static("Providers", classes="section-title")
                    yield ProviderPane([], id="provider-pane")
                    yield Static("Instances", classes="section-title")
                    yield DataTable(id="instances")
                    yield Button("Refresh", id="refresh", variant="primary")
                with Vertical(id="right"):
                    yield Static(
                        "\n".join(
                            [
                                "[primary]◇[/]",
                                "[b]Please, select an instance[/b]",
                                "",
                                "Loading instances...",
                                "Press Enter on << New Instance >> to create one.",
                            ]
                        ),
                        id="empty-state",
                    )
                    with Vertical(id="instance-detail"):
                        yield Static("Select an instance.", id="title", classes="section-title")
                        with Horizontal(id="state-strip"):
                            yield Static("Provider\nunknown", id="provider-pill", classes="pill")
                            yield Static("State\nunknown", id="state-pill", classes="pill")
                            yield Static("IP\n-", id="ip-pill", classes="pill")
                            yield Static("Provision\nunknown", id="provision-pill", classes="pill")
                            yield Static("Packages\nunknown", id="packages-pill", classes="pill")
                        with Horizontal(id="detail-tabs"):
                            yield Button("Overview", id="tab-overview", variant="primary")
                            yield Button("Packages", id="tab-packages")
                            yield Button("Ops", id="tab-ops")
                        with Vertical(id="overview-tab"), Vertical(id="action-groups"):
                            with Vertical(id="instance-actions-group", classes="action-group"):
                                yield Static("Instance Controls", classes="action-title")
                                with Grid(id="lifecycle-strip"):
                                    yield Button("Up", id="provider-up", variant="success")
                                    yield Button("Stop", id="provider-stop", variant="warning")
                                    yield Button("Reboot", id="reboot", variant="warning")
                                    yield Button("Provision", id="provision", variant="primary")
                            with Vertical(id="utility-actions-group", classes="action-group"):
                                yield Static("Utilities", classes="action-title")
                                with Grid(id="utility-strip"):
                                    yield Button("Logs", id="logs")
                                    yield Button("Update", id="update-tools")
                                    yield Button("Upload", id="upload")
                                    yield Button("Password", id="show-password")
                            with Vertical(id="package-actions-group", classes="action-group"):
                                yield Static("Actions", classes="action-title")
                                with Grid(id="remote-strip"):
                                    yield Button("SSH", id="connect-ssh")
                                    for index in range(PACKAGE_ACTION_BUTTONS):
                                        yield Button("", id=f"pkg-action-{index}")
                        with Vertical(id="packages-tab"), Vertical(id="packages-pane"):
                            yield Static("Bundles", classes="section-title")
                            yield DataTable(id="bundles")
                            with Grid(id="bundle-actions"):
                                yield Button("Add Bundle", id="bundle-select")
                                yield Button("Remove Bundle", id="bundle-unselect")
                            yield Static("Packages", classes="section-title")
                            yield DataTable(id="packages")
                            with Grid(id="package-actions"):
                                yield Button("Status", id="package-status")
                                yield Button("Add Extra", id="package-select")
                                yield Button("Remove Extra", id="package-unselect")
                                yield Button("Install", id="package-install", variant="success")
                                yield Button("Reinstall", id="package-reinstall", variant="warning")
                                yield Button("Uninstall", id="package-down", variant="warning")
                        with Vertical(id="ops-tab"):
                            yield Static("Recent Ops", classes="section-title")
                            yield Static("No operations yet.", id="ops")
                            with Vertical(id="provider-debug-group", classes="action-group"):
                                yield Static("Provider Debug", classes="action-title")
                                with Grid(id="provider-debug-strip"):
                                    for index in range(PROVIDER_ACTION_BUTTONS):
                                        yield Button("", id=f"provider-action-{index}")
                            with Grid(id="danger-strip"):
                                yield Button("Down", id="provider-down", variant="error")
                                yield Button("Recover", id="instance-recover")
                                yield Button("Delete Entry", id="delete-instance", variant="error")
            yield Static(
                "Output  |  press l to focus, arrows/PageUp/PageDown to scroll, y to copy selected/all log text",
                id="output-help",
            )
            yield TextArea(
                "",
                id="output",
                read_only=True,
                show_line_numbers=False,
                soft_wrap=True,
                show_cursor=False,
            )
        yield Footer()

    async def on_mount(self) -> None:
        instances = self.query_one("#instances", DataTable)
        instances.cursor_type = "row"
        instances.add_columns("", "Instance", "State", "OS")

        packages = self.query_one("#packages", DataTable)
        packages.cursor_type = "row"
        packages.add_columns("Package", "Selection", "State", "OK", "Source")

        bundles = self.query_one("#bundles", DataTable)
        bundles.cursor_type = "row"
        bundles.add_columns("Bundle", "Selection", "Includes")

        self.update_detail_tabs()
        self.animate_hero()
        self.set_interval(1.2, self.animate_hero)
        self.set_interval(15, self.trigger_blink)
        self.set_interval(30, self.poll_statuses)
        self.start_task(self.load_initial_data())
        self.start_task(self.load_provider_health())
        self.park_terminal_cursor()
        self.call_after_refresh(self._check_first_run)

    async def load_initial_data(self) -> None:
        await self.load_catalog_options()
        await self.load_provider_pane_data()
        await self.action_refresh()
        self.call_after_refresh(self.focus_instance_list_if_empty)

    async def load_provider_pane_data(self) -> None:
        try:
            self._provider_pane_data = await asyncio.to_thread(provider_pane_data)
        except Exception as exc:
            self.log_line(f"[warning]provider-pane-data failed:[/] {exc}")
            self._provider_pane_data = []

        try:
            pane = self.query_one("#provider-pane", ProviderPane)
            pane.update_providers(self._provider_pane_data)
        except Exception as exc:
            self.log_line(f"[warning]provider-pane render failed:[/] {exc}")

    async def load_provider_health(self) -> None:
        pane = self.query_one("#provider-pane", ProviderPane)
        try:
            text = await asyncio.to_thread(provider_status_table)
        except Exception as exc:
            pane.update_status({}, {}, {"_error": str(exc)})
            return
        lines = text.splitlines()
        configured: dict[str, bool] = {}
        reachable: dict[str, bool] = {}
        notes: dict[str, str] = {}
        for row in lines[2:]:
            parts = row.split(None, 3)
            if len(parts) < 3:
                continue
            name, conf, reach = parts[:3]
            note = parts[3] if len(parts) > 3 else "-"
            configured[name] = conf == "yes"
            reachable[name] = reach == "yes"
            notes[name] = note
        self._provider_reachability = reachable
        pane.update_status(configured, reachable, notes)

    async def load_catalog_options(self) -> None:
        try:
            self.catalog_options = await asyncio.to_thread(catalog_options)
        except Exception as exc:
            self.log_line(f"[warning]catalog-options failed:[/] {exc}")
            self.catalog_options = {"providers": [], "platforms": [], "bundles": [], "packages": []}

    def trigger_blink(self) -> None:
        if self.current_instance is not None:
            return
        self._eye_blinking = True
        self.render_empty_state()
        self.set_timer(0.18, self._end_blink)

    def _end_blink(self) -> None:
        self._eye_blinking = False
        if self.current_instance is None:
            self.render_empty_state()

    def animate_hero(self) -> None:
        frames = [
            f"[primary]◇[/] {APP_NAME}  [dim]{APP_EXPANSION}[/]  [success]ready[/]  [dim]{APP_TAGLINE}[/dim]",
            f"[primary]◈[/] {APP_NAME}  [dim]{APP_EXPANSION}[/]  [success]ready[/]  [dim]{APP_TAGLINE}[/dim]",
            f"[primary]◆[/] {APP_NAME}  [dim]{APP_EXPANSION}[/]  [success]ready[/]  [dim]{APP_TAGLINE}[/dim]",
            f"[primary]◈[/] {APP_NAME}  [dim]{APP_EXPANSION}[/]  [success]ready[/]  [dim]{APP_TAGLINE}[/dim]",
        ]
        self.query_one("#hero", Static).update(frames[self.hero_frame % len(frames)])
        self.hero_frame += 1
        if self.current_instance is None:
            self.render_empty_state()
        self.park_terminal_cursor()

    def log_line(self, message: str) -> None:
        if not message.strip():
            return
        output = self.query_one("#output", TextArea)
        should_autoscroll = not output.has_focus or output.is_vertical_scroll_end
        lines = output.document.lines
        location = (len(lines) - 1, len(lines[-1]) if lines else 0)
        output.insert(plain_log_line(message) + "\n", location=location)
        if should_autoscroll:
            output.scroll_end(animate=False, force=True)
        self.park_terminal_cursor()

    def park_terminal_cursor(self) -> None:
        # Let Textual own the terminal cursor. Manually moving it produced
        # a full-width cursor row in some terminals after focus changes.
        return

    def start_task(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)

    async def stream_command(
        self,
        label: str,
        args: list[str],
        *,
        refresh_instance: str | None = None,
        env: dict[str, str] | None = None,
    ) -> int:
        if self.command_running:
            self.notify("A command is already running", severity="warning")
            return 1
        self.command_running = True
        self.current_command_label = label
        status_poll_done = asyncio.Event()
        status_poll_task: asyncio.Task[None] | None = None

        async def poll_running_status() -> None:
            while not status_poll_done.is_set():
                try:
                    await asyncio.wait_for(status_poll_done.wait(), timeout=2)
                except TimeoutError:
                    if refresh_instance:
                        with suppress(TimeoutError):
                            await asyncio.wait_for(
                                self.refresh_status_for(refresh_instance, resolve_ip=False),
                                timeout=4,
                            )

        if refresh_instance:
            status_poll_task = asyncio.create_task(poll_running_status())
        self.update_action_state()
        self.log_line(f"[primary]$ {command_label(args)}[/]")
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=ROOT,
                env={**os.environ, **(env or {})},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
            self.current_process = proc
            assert proc.stdout is not None
            partial_line = ""
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                text = chunk.decode(errors="replace").replace("\r\n", "\n").replace("\r", "\n")
                partial_line += text
                while "\n" in partial_line:
                    line, partial_line = partial_line.split("\n", 1)
                    self.log_line(line)
                    await asyncio.sleep(0)
                if len(partial_line) >= 4096:
                    self.log_line(partial_line)
                    await asyncio.sleep(0)
                    partial_line = ""
            if partial_line:
                self.log_line(partial_line)
                await asyncio.sleep(0)
            code = await proc.wait()
            if code == 0:
                self.log_line(f"[success]{label} completed.[/]")
            else:
                self.log_line(f"[error]{label} failed with exit {code}.[/]")
            return int(code)
        finally:
            status_poll_done.set()
            if status_poll_task:
                status_poll_task.cancel()
                with suppress(asyncio.CancelledError):
                    await status_poll_task
            self.current_process = None
            self.command_running = False
            self.current_command_label = None
            self.update_action_state()
            try:
                if refresh_instance:
                    await asyncio.wait_for(
                        self.refresh_status_for(refresh_instance, repaint_table=True, resolve_ip=False),
                        timeout=4,
                    )
                else:
                    await asyncio.wait_for(self.refresh_current_status(resolve_ip=False), timeout=4)
            except TimeoutError:
                self.log_line("[warning]Status refresh timed out; press Refresh to retry.[/]")
            finally:
                self.update_action_state()

    async def poll_statuses(self) -> None:
        if self.command_running:
            return
        if self.current_instance:
            await self.refresh_status_for(self.current_instance)

    async def refresh_instances(
        self,
        *,
        preserve_selection: bool = False,
        quiet: bool = False,
        repaint_table: bool = True,
        live_all: bool = False,
    ) -> None:
        if not quiet:
            self.log_line("[primary]Refreshing instances[/]")
        try:
            rows = await asyncio.to_thread(instance_rows)
        except Exception as exc:
            self.log_line(f"[error]instance-list failed:[/] {exc}")
            return

        previous = self.current_instance if preserve_selection else None
        previous_names = [str(row.get("name", "")) for row in self.instances if row.get("name")]
        next_names = [str(row.get("name", "")) for row in rows if row.get("name")]
        self.instances = rows
        next_name_set = set(next_names)
        self.statuses = {name: status for name, status in self.statuses.items() if name in next_name_set}

        if previous and previous in self.statuses:
            self.current_instance = previous
        elif self.current_instance not in self.statuses:
            if previous and previous in next_name_set:
                self.current_instance = previous
            elif self.current_instance in next_name_set:
                pass
            else:
                self.current_instance = None

        new_names = previous_names != next_names
        if repaint_table or new_names:
            self.render_instances(sync_cursor=True)
        if self._list_status_task and not self._list_status_task.done():
            self._list_status_task.cancel()
        # Fill the table with last-known state from one fast snapshot so it shows
        # real state immediately, instead of "loading" every row while each
        # instance is resolved + live-observed (seconds each).
        try:
            snapshot = await asyncio.to_thread(instance_statuses)
            for name, status in snapshot.items():
                if name in next_name_set:
                    self.statuses[name] = status
        except Exception as exc:
            self.log_line(f"[warning]status snapshot failed:[/] {exc}")
        # The snapshot gives real state for every row, so nothing shows as
        # "loading"; the live observe updates the selected instance silently.
        self._status_refreshing = set()
        if repaint_table or new_names:
            self.render_instances(sync_cursor=True)
        self._list_status_task = asyncio.create_task(self.refresh_list_statuses(next_names, live_all=live_all))
        self.background_tasks.add(self._list_status_task)
        self._list_status_task.add_done_callback(self.background_tasks.discard)
        if self.current_instance and self.current_instance not in self.statuses:
            self.render_loading_detail(self.current_instance)
            self.update_action_state()
        await self.refresh_current_status(allow_fetch=False)
        if not self.command_running:
            try:
                counts = await asyncio.to_thread(aggregate_summary)
                self._cached_aggregate = counts
                self.query_one("#summary", Static).update(format_aggregate(counts))
            except Exception as exc:
                self.log_line(f"[warning]aggregate refresh failed:[/] {exc}")

    async def refresh_list_statuses(self, instance_names: list[str], *, live_all: bool = False) -> None:
        # The table already shows last-known state from the fast snapshot. Now
        # live-observe (a provider/network call, seconds each) only the selected
        # instance, so startup doesn't peg a core observing every instance - the
        # cloud ones cost ~8s each. An explicit refresh passes live_all to
        # observe everything. Selected first; applied as each result lands.
        if live_all:
            targets = list(instance_names)
        elif self.current_instance in instance_names:
            targets = [self.current_instance]
        else:
            targets = []
        if self.current_instance in targets:
            targets.remove(self.current_instance)
            targets.insert(0, self.current_instance)
        try:
            for name in targets:
                try:
                    status = await asyncio.to_thread(instance_observe_view, name)
                except Exception as exc:
                    self.log_line(f"[warning]status failed for {name}:[/] {exc}")
                    status = {"instance": {"name": name}, "state": {"last_error": str(exc)}}
                self.statuses[name] = status
                self._status_refreshing.discard(name)
                self.render_instances()
                if self.current_instance == name:
                    self.current_status = status
                    self.render_detail()
                    self.update_action_state()
            if not self.command_running:
                try:
                    counts = await asyncio.to_thread(aggregate_summary)
                    self._cached_aggregate = counts
                    self.query_one("#summary", Static).update(format_aggregate(counts))
                except Exception as exc:
                    self.log_line(f"[warning]aggregate refresh failed:[/] {exc}")
        except asyncio.CancelledError:
            self._status_refreshing.difference_update(instance_names)
            raise

    def focus_instance_list_if_empty(self) -> None:
        if self.current_instance is None:
            self.query_one("#instances", DataTable).focus()

    def _check_first_run(self) -> None:
        try:
            missing = load_missing_fields()
            if missing:
                self.push_screen(FirstRunScreen(missing))
        except Exception:
            pass

    def render_instances(self, *, sync_cursor: bool = False, focus_empty: bool = False) -> None:
        table = self.query_one("#instances", DataTable)
        self._rendering_instances = True
        table.clear()
        table.add_row("+", "<< New Instance >>", "", "", key=NEW_INSTANCE_KEY)
        filter_text = ""  # instance filter removed; keep loop logic inert
        current_row = 0
        current_visible = self.current_instance is None
        row_index = 1
        for row in self.instances:
            name = str(row.get("name", ""))
            os_id = str(row.get("os", ""))
            machine = str(row.get("machine", ""))
            if (
                filter_text
                and filter_text not in name.lower()
                and filter_text not in os_id.lower()
                and filter_text not in machine.lower()
            ):
                continue
            if name == self.current_instance:
                current_row = row_index
                current_visible = True
            status = self.statuses.get(name, {})
            state = status.get("state", {})
            provider_state = str(state.get("effective_provider_state", "unknown"))
            provision_state = str(state.get("provision_state", "unknown"))
            loading = name in self._status_refreshing or not status
            display_state_text = "loading" if loading else (provider_state if provider_state != "unknown" else "")
            if not display_state_text and provision_state != "unknown":
                display_state_text = provision_state
            if not display_state_text:
                display_state_text = "new"
            table.add_row(
                "..." if loading else glyph_for_status(provider_state),
                name,
                display_state_text,
                os_id or "-",
                key=name,
            )
            row_index += 1
        if sync_cursor and current_visible:
            table.move_cursor(row=current_row, column=0, animate=False, scroll=True)
        if focus_empty and self.current_instance is None:
            table.focus()
        self._rendering_instances = False

    async def refresh_current_status(self, *, allow_fetch: bool = True, resolve_ip: bool = True) -> None:
        self._detail_refresh_seq += 1
        refresh_seq = self._detail_refresh_seq
        instance_name = self.current_instance
        focused_id = self.focused.id if self.focused is not None else None
        if not instance_name:
            self.current_status = None
            self.query_one("#title", Static).update("Select an instance.")
            self.render_empty_detail()
            self.update_action_state()
            return
        next_status = self.statuses.get(instance_name)
        if status_instance_name(next_status) not in {None, instance_name}:
            next_status = None
        if allow_fetch:
            try:
                next_status = await asyncio.to_thread(instance_observe_view, instance_name)
                if refresh_seq != self._detail_refresh_seq or instance_name != self.current_instance:
                    return
                if status_instance_name(next_status) != instance_name:
                    self.log_line(
                        f"[error]instance-view returned {status_instance_name(next_status) or 'unknown'} "
                        f"while {instance_name} was selected[/]"
                    )
                    return
                self.statuses[instance_name] = next_status
            except Exception as exc:
                if refresh_seq != self._detail_refresh_seq or instance_name != self.current_instance:
                    return
                self.log_line(f"[error]instance-view failed:[/] {exc}")
                return
        if not next_status:
            self.render_loading_detail(instance_name)
            self.update_action_state()
            return
        if refresh_seq != self._detail_refresh_seq or instance_name != self.current_instance:
            return
        self.current_status = next_status
        provider_state = str(next_status.get("state", {}).get("effective_provider_state", "unknown"))
        if resolve_ip and provider_state == "running":
            try:
                ip = await asyncio.to_thread(instance_ip, instance_name)
                if refresh_seq == self._detail_refresh_seq and instance_name == self.current_instance:
                    self.instance_ips[instance_name] = ip or "-"
            except Exception:
                self.instance_ips[instance_name] = "-"
        elif not resolve_ip:
            observed = next_status.get("observed_state", {})
            if isinstance(observed, dict) and observed.get("ip"):
                self.instance_ips[instance_name] = str(observed.get("ip"))
        else:
            self.instance_ips[instance_name] = "-"
        self.render_detail()
        self.update_action_state()
        self.restore_focus(focused_id)

    async def refresh_status_for(
        self,
        instance_name: str,
        *,
        repaint_table: bool = False,
        resolve_ip: bool = True,
    ) -> None:
        self._status_refreshing.add(instance_name)
        try:
            status = await asyncio.to_thread(instance_observe_view, instance_name)
        except Exception as exc:
            self.log_line(f"[error]instance-view failed for {instance_name}:[/] {exc}")
            self._status_refreshing.discard(instance_name)
            if repaint_table:
                self.render_instances(sync_cursor=True)
            return
        if status_instance_name(status) != instance_name:
            self.log_line(
                f"[error]instance-view returned {status_instance_name(status) or 'unknown'} "
                f"while refreshing {instance_name}[/]"
            )
            self._status_refreshing.discard(instance_name)
            if repaint_table:
                self.render_instances(sync_cursor=True)
            return
        self.statuses[instance_name] = status
        self._status_refreshing.discard(instance_name)
        if repaint_table:
            self.render_instances(sync_cursor=True)
            if not self.command_running:
                try:
                    counts = await asyncio.to_thread(aggregate_summary)
                    self._cached_aggregate = counts
                    self.query_one("#summary", Static).update(format_aggregate(counts))
                except Exception as exc:
                    self.log_line(f"[warning]aggregate refresh failed:[/] {exc}")
        if self.current_instance == instance_name:
            self.current_status = status
            state = status.get("state", {})
            if resolve_ip and isinstance(state, dict) and provider_actions_available(state):
                with suppress(Exception):
                    self.instance_ips[instance_name] = await asyncio.to_thread(instance_ip, instance_name) or "-"
            elif not resolve_ip:
                observed = status.get("observed_state", {})
                if isinstance(observed, dict) and observed.get("ip"):
                    self.instance_ips[instance_name] = str(observed.get("ip"))
            else:
                self.instance_ips[instance_name] = "-"
            self.render_detail()
            self.update_action_state()

    def render_empty_detail(self) -> None:
        self.query_one("#empty-state", Static).display = True
        self.query_one("#instance-detail", Vertical).display = False
        self.render_empty_state()
        self.query_one("#provider-pill", Static).update("Provider\nunknown")
        self.query_one("#state-pill", Static).update("State\nunknown")
        self.query_one("#ip-pill", Static).update("IP\n-")
        self.query_one("#provision-pill", Static).update("Provision\nunknown")
        self.query_one("#packages-pill", Static).update("Packages\nunknown")
        self.query_one("#bundles", DataTable).clear()
        self.query_one("#packages", DataTable).clear()
        self.query_one("#ops", Static).update("No instance selected.")

    def render_loading_detail(self, instance_name: str) -> None:
        self.query_one("#empty-state", Static).display = False
        self.query_one("#instance-detail", Vertical).display = True
        self.query_one("#title", Static).update(f"{instance_name}  loading status...")
        self.query_one("#provider-pill", Static).update("Provider\nloading")
        self.query_one("#state-pill", Static).update("State\nloading")
        self.query_one("#ip-pill", Static).update("IP\nloading")
        self.query_one("#provision-pill", Static).update("Provision\nloading")
        self.query_one("#packages-pill", Static).update("Packages\nloading")
        self.query_one("#bundles", DataTable).clear()
        self.query_one("#packages", DataTable).clear()
        self.query_one("#ops", Static).update("Loading status...")

    def render_detail(self) -> None:
        if status_instance_name(self.current_status) != self.current_instance:
            if self.current_instance:
                self.render_loading_detail(self.current_instance)
            else:
                self.render_empty_detail()
            return
        self.query_one("#empty-state", Static).display = False
        self.query_one("#instance-detail", Vertical).display = True
        status = self.current_status or {}
        instance = status.get("instance", {})
        state = status.get("state", {})
        packages = status.get("packages", {})
        summary = packages.get("summary", {})
        self.query_one("#title", Static).update(
            f"{instance.get('name', '-')}  {instance.get('provider', '-')}  {instance.get('os', '-')}"
        )
        provision_state = str(state.get("provision_state", "unknown"))
        provider_name = str(instance.get("provider") or "-")
        provider_state = str(state.get("effective_provider_state", "unknown"))
        ip_text = self.instance_ips.get(str(instance.get("name") or ""), "-")
        if not provider_actions_available(cast(dict[str, Any], state)):
            ip_text = "-"
        package_text = package_summary_label(cast(dict[str, Any], summary))
        self.query_one("#provider-pill", Static).update(f"Provider\n{provider_name}")
        self.query_one("#state-pill", Static).update(
            f"State\n{markup_for_status(display_state(provider_state))}"
        )
        self.query_one("#ip-pill", Static).update(f"IP\n{ip_text or '-'}")
        self.query_one("#provision-pill", Static).update(
            f"Provision\n{markup_for_status(display_state(provision_state))}"
        )
        self.query_one("#packages-pill", Static).update(f"Packages\n{package_text}")
        self.render_bundles(status)
        self.render_packages(status)
        self.render_ops(status)

    def render_empty_state(self) -> None:
        hair = "#ff8fb1"
        skin = "#f5c8a9"
        brow = "#5a3d5a"
        dress = [
            "#7fd3e3", "#82cde2", "#84c6e0", "#87c0df",
            "#8ab9dd", "#8db3dc", "#8faddb", "#92a6da",
            "#95a0d9", "#9799d8", "#9a93d7", "#9d8cd6",
        ]
        blinking = self._eye_blinking

        container_width = self.query_one("#empty-state", Static).size.width
        if container_width <= 0:
            container_width = self.size.width if self.size else 80
        if container_width >= 60:
            hero_art_rows = self._large_hero_rows(hair, skin, brow, dress, blinking)
        elif container_width >= 32:
            hero_art_rows = self._compact_hero_rows(hair, skin, brow, dress, blinking)
        else:
            hero_art_rows = []

        def render_segment(color: str | None, text: str) -> str:
            return f"[{color}]{text}[/]" if color and text else text

        lines: list[str] = []
        if hero_art_rows:
            lines.append(
                "\n".join(
                    "".join(render_segment(color, text) for color, text in row)
                    for row in hero_art_rows
                )
            )
        lines += [
            f"[b]EVE[/b] [dim]{APP_EXPANSION}[/]",
            "",
            "[b]Please, select an instance[/b]",
            "Highlight an instance to preview and manage it.",
            "Press Enter on << New Instance >> to create a VM.",
        ]
        self.query_one("#empty-state", Static).update("\n".join(lines))

    def _large_hero_rows(
        self,
        hair: str,
        skin: str,
        brow: str,
        dress: list[str],
        blinking: bool,
    ) -> list[list[tuple[str | None, str]]]:
        eye = "#ffffff"
        if blinking:
            eye_8_l: tuple[str, str] = (skin, "      ")
            eye_8_r: tuple[str, str] = (skin, "     ")
            eye_9_l: tuple[str, str] = (brow, "‿‿‿‿‿‿")
            eye_9_r: tuple[str, str] = (brow, "‿‿‿‿‿‿")
            eye_10_l: tuple[str, str] = (skin, "      ")
            eye_10_r: tuple[str, str] = (skin, "   ")
        else:
            eye_8_l = (eye, " ▓ █░░")
            eye_8_r = (eye, "░▓ █ ")
            eye_9_l = (eye, "░▓░▓█ ")
            eye_9_r = (eye, "░█▓ ▓░")
            eye_10_l = (eye, " █▓█  ")
            eye_10_r = (eye, "█▓█")
        return [
            [(hair, "               ████                ")],
            [(hair, "           ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓ ▓▓▓▓▓▓▓▓▓▓▓▓            ")],
            [(hair, "       █ ▓▓▓▓▓▓▒▒▒▒▒▒▒▒▓▒▒▒▒▒▒▓▓▓▓█▓▓▓▒▒▒▒▒▒▓▓█        ")],
            [(hair, "    ▓▓▓▓▓▒▒▒▒░░ ░░ ░ ░░░░░ ░░▒▒░▒▒▓▓▓█▓▓▒░▒▒▓▓▓▓     ░▓")],
            [(hair, "  █▓▓▓▓▓▓▒░  ░▒▒▓▓██▓▓▓▓██▓▒░ ░▒▓▓▓▓█▓▓▓▒░▒▓██▓▓▓▓▓███ ")],
            [(hair, " ▓▓▓▒▒▒░░▒▒▒▓▓▓██▓▓▓▓██▓██▓▒▒░▒▒▓▓▓█▓▓▓▒▒░▒▓██████     ")],
            [(hair, " █▓▓▓▒▒▓▓▓▓▓▓▓▓██▓██▓▒▒▓▓▓██▓▓▓▒▒▓▓▓█▓▓▒▒░▒▒▒▓▓▓▓      ")],
            [(hair, "░  █▓▓▓▓▓"), (brow, "████"), (hair, "▓"), (skin, "▒░░░░  ░░░"), (hair, "▒▓▓▓▓▓▓▓▒▒▓█▓▓▓▒▒░ ▒▒▒▒▓▓▓      ")],
            [(hair, " █▓██ "), eye_8_l, (skin, "       "), eye_8_r, (hair, "███▓██▓▓▓▓█▓▓▒▒░  ░▒▓▓▓█        ")],
            [(hair, " █▓██▓"), eye_9_l, (skin, "        "), eye_9_r, (hair, "▓██▓▓▓▓▓█▓▓▓▒▒░░▒▒▒▓▓█        ")],
            [(hair, " █▓██ "), eye_10_l, (skin, "         "), eye_10_r, (skin, "  "), (hair, "██▓▓▓▒▒▓█▓▓▓▒▒▒▒░▒▒▓▓▓        ")],
            [(hair, " █▓▓█"), (skin, "░░░               ░░"), (hair, "█▓▓▒▒▒▓▓▓█▓▓▓▓▓▓▓▓██           ")],
            [(hair, "   █▓█ █"), (skin, "▒░░        ░░"), (hair, "█▓▓▒▓█▓▓▓▒▒▒▓▓███▓▓▓██             ")],
            [(hair, "    ██  "), (skin, "░░▓▓▒▒░░░▒▒"), (hair, "▓██▓▒▒▓▓█▓▓▓▓▒░▒▓▓▓▓█▓▓▓▓            ")],
            [(None, "            "), (dress[0], "▓▒░▒▓▓▓█▓▓▒▒▓"), (hair, "▓█▓█▓█▓▓▓▒▒▓▓▓█▓▓▓█"), (None, "            ")],
            [(None, "       "), (dress[1], "▓▓▓▓▓▓▓▒▓▓▓▓▓▓▓██▒"), (hair, "█▓█▓▓▒█▓▓▓▓▓▓▓█▓██▓█"), (None, "           ")],
            [(None, "     "), (dress[2], "▓▓▒▒▒▒▓▒▓▓▓▓▒▒▓▓█▓▓▓"), (hair, "█▓▓█▓▓▓▒█▓▓▒▓▓██"), (None, "               ")],
            [(None, "    "), (dress[3], "▓▓▒▒▒▒▒▓▓▓▓▒▓▓▓█▓▓▓██"), (hair, "▓▓▓▓▓▓▓▓██▓▓▓▓▓█░"), (None, "              ")],
            [(None, "    "), (dress[4], "▓▓▒▒▒▓██▓▓▓▓▓▒▒▓▓▓▓▓▓"), (hair, "▓▓██▓▓▓▓▓██"), (None, "   "), (hair, "▓"), (None, "                ")],
            [(None, "     "), (dress[5], "██▓▓▒▒▒▓██▓▓▓▒▓▓▓▓▓█"), (hair, "█▓▓▓▓██"), (None, " "), (hair, "█▓█"), (None, "                    ")],
            [(None, "       "), (dress[6], "▓▒▒▒▒▒██▓▓▓▒▓▓▓▓██"), (None, " "), (hair, "█▓▓▓▓██"), (None, "  "), (hair, "██"), (None, "                   ")],
            [(None, "      "), (dress[7], "▓▓▒▒▒▒▒▓███▓▓▓██▓▓█"), (None, "   "), (skin, "█▓▒▓▓"), (None, "                       ")],
            [(None, "     "), (dress[8], "█▓▓▓▓▓▓▓▓██▓▓▓▓▓▓▓██"), (None, "   "), (skin, "█▓▓▓▓▓"), (None, "                      ")],
            [(None, "     "), (dress[9], "█▓▓▓▓▓▓▓▓██████▓▓██"), (None, "       "), (skin, "██████"), (None, "                   ")],
            [(dress[10], "      █▓▓▓▓▓▓██▓▓▓▓▓██                                  ")],
            [(dress[11], "      ░▓▓▓▒▒▓█▓▓▒▒▓█░                                   ")],
            [(dress[11], "       █▓▓▓▓▓█▓▓▓▓▓█                                    ")],
            [(dress[11], "        █▓▓▓▓█▓▓█▓                                      ")],
            [(dress[11], "         ██▓▓▓▓██                                       ")],
            [(dress[11], "            ███                                         ")],
        ]

    def _compact_hero_rows(
        self,
        hair: str,
        skin: str,
        brow: str,
        dress: list[str],
        blinking: bool,
    ) -> list[list[tuple[str | None, str]]]:
        eye = "#ffffff"
        if blinking:
            eye_4_l: tuple[str, str] = (skin, "    ")
            eye_4_r: tuple[str, str] = (skin, "    ")
            eye_5_l: tuple[str, str] = (brow, "‿‿‿‿")
            eye_5_r: tuple[str, str] = (brow, "‿‿‿‿")
        else:
            eye_4_l = (eye, "██▓▓")
            eye_4_r = (eye, "▓▓██")
            eye_5_l = (eye, "██▒▒")
            eye_5_r = (eye, "▒▒██")
        return [
            [(hair, "            ████            ")],
            [(hair, "         ▓▓▓▓▓▓▓▓▓▓         ")],
            [(hair, "      ▓▓▓▓"), (brow, "▒▒▒▒▒▒▒▒"), (hair, "▓▓▓▓      ")],
            [(hair, "     ▓▓"), (skin, "░░░░░░░░░░░░░░"), (hair, "▓▓     ")],
            [(hair, "     ▓▓"), (skin, "░░"), eye_4_l, (skin, "░░"), eye_4_r, (skin, "░░"), (hair, "▓▓     ")],
            [(hair, "     ▓▓"), (skin, "░░"), eye_5_l, (skin, "░░"), eye_5_r, (skin, "░░"), (hair, "▓▓     ")],
            [(hair, "     ▓▓"), (skin, "▒▒░░░░░░░░░░▒▒"), (hair, "▓▓     ")],
            [(hair, "      ▓▓"), (skin, "░░░░░░░░░░░░"), (hair, "▓▓      ")],
            [(hair, "        ▓▓"), (skin, "░░░░░░░░"), (hair, "▓▓        ")],
            [(hair, "         ▓▓"), (skin, "██████"), (hair, "▓▓         ")],
            [(hair, "    ▓▓"), (dress[2], "████████████████"), (hair, "▓▓    ")],
            [(hair, "     ▓▓"), (dress[8], "██████████████"), (hair, "▓▓     ")],
        ]

    def selected_bundle_ids(self, status: dict[str, Any]) -> set[str]:
        instance = status.get("instance", {})
        bundles = instance.get("bundles", []) if isinstance(instance, dict) else []
        if not isinstance(bundles, list):
            return set()
        return {str(bundle) for bundle in bundles}

    def render_bundles(self, status: dict[str, Any]) -> None:
        table = self.query_one("#bundles", DataTable)
        table_has_focus = self.focused is table
        table.clear()
        selected_bundles = self.selected_bundle_ids(status)
        catalog_bundles = self.catalog_options.get("bundles", [])
        current_seen = False
        first_bundle: str | None = None
        first_selected: str | None = None
        current_row = 0
        row_index = 0
        for bundle in catalog_bundles:
            if not isinstance(bundle, dict):
                continue
            bundle_id = str(bundle.get("id", ""))
            if not bundle_id:
                continue
            includes = bundle.get("includes", [])
            include_text = ", ".join(str(package) for package in includes) if isinstance(includes, list) else ""
            selected = bundle_id in selected_bundles
            if first_bundle is None:
                first_bundle = bundle_id
            if selected and first_selected is None:
                first_selected = bundle_id
            if bundle_id == self.current_bundle:
                current_seen = True
                current_row = row_index
            table.add_row(
                bundle_id,
                "selected" if selected else "available",
                include_text or "-",
                key=bundle_id,
            )
            row_index += 1
        if not current_seen:
            self.current_bundle = first_selected or first_bundle
            if self.current_bundle is not None:
                for index, bundle in enumerate(catalog_bundles):
                    if isinstance(bundle, dict) and bundle.get("id") == self.current_bundle:
                        current_row = index
                        break
        if row_index and table_has_focus:
            table.move_cursor(row=current_row, column=0, animate=False, scroll=True)

    def render_packages(self, status: dict[str, Any]) -> None:
        table = self.query_one("#packages", DataTable)
        table_has_focus = self.focused is table
        table.clear()
        package_rows = status.get("packages", {}).get("all", [])
        current_seen = False
        first_selected: str | None = None
        current_row = 0
        row_index = 0
        for package in package_rows:
            if not isinstance(package, dict):
                continue
            package_id = str(package.get("id", ""))
            if not package_id:
                continue
            supported = bool(package.get("supported"))
            if not supported and not self.show_disabled:
                continue
            selected = bool(package.get("selected"))
            if selected and first_selected is None:
                first_selected = package_id
            if package_id == self.current_package:
                current_seen = True
                current_row = row_index
            state = package.get("state", {}) or {}
            package_status = str(state.get("status") or "unknown")
            if not selected and package_status == "unknown":
                package_status = "-"
            selected_by = package.get("selected_by", [])
            table.add_row(
                package_id,
                "selected" if selected else "available",
                package_status,
                "yes" if supported else "no",
                package_source_label(selected_by),
                key=package_id,
            )
            row_index += 1
        if not current_seen:
            self.current_package = first_selected
            if first_selected is not None:
                for index, package in enumerate(package_rows):
                    if isinstance(package, dict) and package.get("id") == first_selected:
                        current_row = index
                        break
        if row_index and table_has_focus:
            table.move_cursor(row=current_row, column=0, animate=False, scroll=True)

    def render_ops(self, status: dict[str, Any]) -> None:
        state = status.get("state", {})
        history = state.get("operation_history", [])
        if not isinstance(history, list) or not history:
            self.query_one("#ops", Static).update("No operations yet.")
            return
        lines: list[str] = []
        for op in history[-8:]:
            if isinstance(op, dict):
                lines.append(f"{op.get('at', '-')}  {op.get('name', '-')}  {op.get('status', '-')}")
        last_error = state.get("last_error")
        if last_error:
            lines.append("")
            lines.append(f"[error]{last_error}[/]")
        self.query_one("#ops", Static).update("\n".join(lines))

    async def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "instances":
            if self._rendering_instances or self.focused is not event.data_table:
                return
            row_key = str(event.row_key.value)
            next_instance = None if row_key == NEW_INSTANCE_KEY else row_key
            if next_instance != self.current_instance:
                self.current_instance = next_instance
                self.set_detail_tab("overview", focus=False)
                self.current_status = self.statuses.get(next_instance) if next_instance else None
                if next_instance is None:
                    self.render_empty_detail()
                    self.update_action_state()
                elif status_instance_name(self.current_status) == next_instance:
                    self.render_detail()
                    self.update_action_state()
                else:
                    self.render_loading_detail(next_instance)
                    self.update_action_state()
                self.start_task(self.refresh_current_status())
        elif event.data_table.id == "packages":
            self.current_package = str(event.row_key.value)
            self.update_action_state()
        elif event.data_table.id == "bundles":
            self.current_bundle = str(event.row_key.value)
            self.update_action_state()

    async def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = str(event.row_key.value)
        if event.data_table.id == "instances":
            if row_key == NEW_INSTANCE_KEY:
                self.action_new_instance()
                return
            self.current_instance = row_key
            self.set_detail_tab("overview", focus=False)
            self.current_status = self.statuses.get(row_key)
            if status_instance_name(self.current_status) == row_key:
                self.render_detail()
                self.update_action_state()
            else:
                self.render_loading_detail(row_key)
                self.update_action_state()
            self.start_task(self.refresh_current_status())
            self.focus_top_action()
        elif event.data_table.id == "packages":
            self.current_package = row_key
            self.update_action_state()
        elif event.data_table.id == "bundles":
            self.current_bundle = row_key
            self.update_action_state()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("tab-"):
            self.set_detail_tab(button_id.split("-", 1)[1])
        elif button_id == "refresh":
            self.start_task(self.action_refresh(live_all=True))
        elif button_id == "busy-cancel-command":
            self.start_task(self.action_cancel_command())
        elif button_id == "provider-up":
            self.start_task(self.action_provider("up"))
        elif button_id == "provider-stop":
            self.start_task(self.action_provider("stop"))
        elif button_id == "provider-down":
            self.action_down_instance()
        elif button_id.startswith("provider-action-"):
            self.start_task(self.action_provider_manifest(int(button_id.rsplit("-", 1)[1])))
        elif button_id == "reboot":
            self.action_confirm_instance_command("Reboot instance?", "reboot", "reboot")
        elif button_id == "update-tools":
            self.action_confirm_instance_command("Update instance tools?", "update", "update")
        elif button_id == "show-password":
            self.start_task(self.action_instance_command("show-password", "show-password"))
        elif button_id == "upload":
            self.action_upload()
        elif button_id == "instance-recover":
            self.action_confirm_instance_command("Recover local operation state?", "instance.recover", "instance.recover")
        elif button_id == "provision":
            self.start_task(self.action_provision())
        elif button_id == "logs":
            self.start_task(self.action_logs())
        elif button_id == "delete-instance":
            self.action_delete_instance()
        elif button_id == "connect-ssh":
            self.start_task(self.action_connect_ssh())
        elif button_id.startswith("pkg-action-"):
            self.start_task(self.action_package_remote(int(button_id.rsplit("-", 1)[1])))
        elif button_id == "package-status":
            self.start_task(self.action_package("package.status"))
        elif button_id == "package-select":
            self.start_task(self.action_package("package.select"))
        elif button_id == "package-unselect":
            self.start_task(self.action_package("package.unselect"))
        elif button_id == "package-install":
            self.start_task(self.action_package("package.install"))
        elif button_id == "package-reinstall":
            self.action_package_reinstall()
        elif button_id == "package-down":
            self.action_package_down()
        elif button_id == "bundle-select":
            self.start_task(self.action_bundle("bundle.select"))
        elif button_id == "bundle-unselect":
            self.start_task(self.action_bundle("bundle.unselect"))

    async def action_refresh(self, *, live_all: bool = False) -> None:
        if self.command_running:
            self.notify("A command is already running", severity="warning")
            return
        self.command_running = True
        self.current_command_label = "refresh"
        self.update_action_state()
        self.log_line("[primary]Refreshing instances...[/]")
        try:
            await self.refresh_instances(preserve_selection=True, quiet=True, live_all=live_all)
            self.log_line("[success]Refreshing instances finished.[/]")
        finally:
            self.command_running = False
            self.current_command_label = None
            self.update_action_state()

    def action_queue_refresh(self) -> None:
        self.start_task(self.action_refresh())

    def action_open_settings(self) -> None:
        self.push_screen(SettingsScreen())

    def action_open_plugins(self) -> None:
        self.push_screen(PluginSourcesScreen())

    async def action_cancel_command(self) -> None:
        proc = self.current_process
        if not self.command_running or proc is None or proc.returncode is not None:
            if self.command_running:
                self.log_line("[warning]No cancellable subprocess is active yet.[/]")
            return
        self.log_line("[warning]Cancelling current command...[/]")
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except TimeoutError:
            self.log_line("[warning]Command did not stop; killing it.[/]")
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)

    def action_queue_cancel_command(self) -> None:
        self.start_task(self.action_cancel_command())

    def action_new_instance(self) -> None:
        self.push_screen(
            NewInstanceScreen(self.catalog_options),
            self.handle_new_instance,
        )

    def handle_new_instance(self, result: dict[str, str] | None) -> None:
        if not result:
            return
        self.start_task(self.perform_new_instance(result))

    async def perform_new_instance(self, result: dict[str, str]) -> None:
        args = create_instance_args(
            result["name"],
            {
                "machine": result["machine"],
                "os": result["os"],
                "init": result["init"],
                "location": result["location"],
            },
            result["bundles"],
            result["packages"],
            result["disk_gb"],
            result["memory_mb"],
            result.get("provider_ip", ""),
        )
        code = await self.stream_command("instance.create", args)
        if code == 0:
            self.current_instance = result["name"]
            self.set_detail_tab("overview", focus=False)
            await self.refresh_instances(preserve_selection=True)
            self.select_instance_row(result["name"])

    def select_instance_row(self, instance_name: str) -> None:
        table = self.query_one("#instances", DataTable)
        row_index = 1
        filter_text = ""  # instance filter removed; keep loop logic inert
        for row in self.instances:
            name = str(row.get("name", ""))
            os_id = str(row.get("os", ""))
            machine = str(row.get("machine", ""))
            if (
                filter_text
                and filter_text not in name.lower()
                and filter_text not in os_id.lower()
                and filter_text not in machine.lower()
            ):
                continue
            if name == instance_name:
                table.move_cursor(row=row_index, column=0, animate=False, scroll=True)
                return
            row_index += 1

    def action_delete_instance(self) -> None:
        if not self.current_instance:
            return
        instance = self.current_instance
        def on_delete_result(
            result: dict[str, Any] | None,
        ) -> None:
            if result and result.get("confirmed"):
                self.start_task(self.perform_delete_instance(instance, result))

        self.push_screen(DeleteConfirmScreen(instance), on_delete_result)

    async def perform_delete_instance(self, instance: str, options: dict[str, Any] | None = None) -> None:
        opts = options or {}
        args = make_args("instance.delete", instance)
        if opts.get("purge", True):
            args.append("PURGE=1")
        if opts.get("force", False):
            args.append("FORCE=1")
        await self.stream_command("instance.delete", args)
        if self.current_instance == instance:
            self.current_instance = None
        await self.refresh_instances(preserve_selection=True)

    def action_down_instance(self) -> None:
        if not self.current_instance:
            return
        instance = self.current_instance
        self.push_screen(
            ConfirmScreen(
                "Provider down?",
                f"This runs provider down for {instance}. Cloud/local VM resources will be destroyed.",
            ),
            lambda confirmed: self.start_task(self.perform_down_instance(instance)) if confirmed else None,
        )

    async def perform_down_instance(self, instance: str) -> None:
        await self.stream_command("provider.down", make_args("down", instance), refresh_instance=instance)

    def action_confirm_instance_command(self, title: str, label: str, target: str) -> None:
        if not self.current_instance:
            return
        instance = self.current_instance
        self.push_screen(
            ConfirmScreen(title, f"Run {label} for {instance}?"),
            lambda confirmed: self.start_task(self.action_instance_command(label, target)) if confirmed else None,
        )

    async def action_instance_command(self, label: str, target: str) -> None:
        if not self.current_instance:
            return
        instance = self.current_instance
        await self.stream_command(label, make_args(target, instance), refresh_instance=instance)

    def action_upload(self) -> None:
        if not self.current_instance:
            return
        instance = self.current_instance
        folders = upload_folders()
        if not folders:
            self.notify("No direct upload/ subfolders found", severity="warning")
            self.log_line("[warning]No direct upload/ subfolders found.[/]")
            return
        self.push_screen(
            UploadScreen(folders),
            lambda selected: self.start_task(self.perform_upload(instance, selected)) if selected else None,
        )

    async def perform_upload(self, instance: str, selected: list[str]) -> None:
        uploads = ",".join(selected)
        await self.stream_command("upload", make_args("upload", instance, f"UPLOADS={uploads}"), refresh_instance=instance)

    async def action_provider(self, command: str) -> None:
        if not self.current_instance:
            return
        instance = self.current_instance
        if command == "up":
            state = self.current_status.get("state", {}) if self.current_status else {}
            if str(state.get("effective_provider_state", "unknown")) == "stopped":
                command = "start"
        args = (
            provider_dispatch_args(command, instance)
            if command in {"init", "login", "plan", "status"}
            else make_args(command, instance)
        )
        code = await self.stream_command(f"provider.{command}", args, refresh_instance=instance)
        self.keep_instance_selected(instance)
        if code == 0:
            await self.refresh_provider_until(
                instance,
                {"up": "running", "start": "running", "stop": "stopped", "down": "absent"}.get(command),
            )
            self.keep_instance_selected(instance)

    def action_queue_provider(self, command: str) -> None:
        self.start_task(self.action_provider(command))

    def on_provider_pane_action_requested(self, event: ProviderPane.ActionRequested) -> None:
        provider_id = event.provider_id
        action = event.action
        command = str(action.get("target", "")).replace("provider.", "", 1)
        label = str(action.get("label") or command)
        args = provider_dispatch_provider_args(provider_id, command)
        if bool(action.get("interactive")):
            self.start_task(self._run_provider_interactive(label, args))
        else:
            self.start_task(self._run_provider_stream(label, args))

    def on_provider_pane_configure_requested(self, event: ProviderPane.ConfigureRequested) -> None:
        provider_id = event.provider_id
        display_name = provider_id.replace("-", " ").title()
        for provider in self._provider_pane_data:
            if provider.get("id") == provider_id:
                display_name = str(provider.get("display_name", display_name))
                break
        pane = self.query_one("#provider-pane", ProviderPane)
        actions = pane.get_actions(provider_id)
        notes = pane.get_notes(provider_id)
        self.push_screen(ProviderConfigScreen(provider_id, display_name, actions, notes))

    def on_provider_pane_test_connection_requested(self, event: ProviderPane.TestConnectionRequested) -> None:
        provider_id = event.provider_id
        args = provider_dispatch_provider_args(provider_id, "status")

        async def _test() -> None:
            await self.stream_command(f"Test {provider_id}", args)

        self.start_task(_test())

    async def _run_provider_interactive(self, label: str, args: list[str]) -> None:
        self.log_line(f"[primary]Opening {label}. Exit the session to return to the TUI.[/]")
        self.refresh()
        await asyncio.sleep(0.05)
        with self.suspend():
            subprocess.call(args, cwd=ROOT, env=os.environ.copy())
        self.log_line(f"[primary]{label} session closed.[/]")

    async def _run_provider_stream(self, label: str, args: list[str]) -> None:
        await self.stream_command(label, args)

    async def action_provider_manifest(self, index: int) -> None:
        if not self.current_instance or index >= len(self.current_provider_actions):
            return
        instance = self.current_instance
        action = self.current_provider_actions[index]
        target = str(action.get("target") or "")
        label = str(action.get("label") or target or "provider action")
        if target.startswith("provider."):
            command = target.split(".", 1)[1]
            if bool(action.get("interactive")):
                self.log_line(f"[primary]Opening {label} for {instance}. Exit the session to return to the TUI.[/]")
                self.refresh()
                await asyncio.sleep(0.05)
                with self.suspend():
                    code = subprocess.call(provider_dispatch_args(command, instance), cwd=ROOT, env=os.environ.copy())
                if code == 0:
                    self.log_line(f"[success]{label} session closed.[/]")
                else:
                    self.log_line(f"[error]{label} failed with exit {code}.[/]")
                await self.refresh_current_status(resolve_ip=False)
                return
            await self.action_provider(command)
            return
        await self.stream_command(label, make_args(target, instance), refresh_instance=instance)

    def keep_instance_selected(self, instance: str) -> None:
        if not any(str(row.get("name", "")) == instance for row in self.instances):
            return
        self.current_instance = instance
        self.current_status = self.statuses.get(instance)
        if status_instance_name(self.current_status) == instance:
            self.render_detail()
        else:
            self.render_loading_detail(instance)
        self.render_instances(sync_cursor=True)
        self.update_action_state()

    async def refresh_provider_until(self, instance: str, expected_state: str | None) -> bool:
        if not expected_state:
            return True
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            await self.refresh_status_for(instance, repaint_table=True)
            status = self.statuses.get(instance, {})
            state = status.get("state", {})
            if isinstance(state, dict) and str(state.get("effective_provider_state", "unknown")) == expected_state:
                return True
            await asyncio.sleep(2)
        return False

    async def action_provision(self) -> None:
        if self.current_instance:
            instance = self.current_instance
            await self.refresh_status_for(instance, repaint_table=True, resolve_ip=False)
            state = self.current_status.get("state", {}) if self.current_status else {}
            provider_state = str(state.get("effective_provider_state", "unknown"))
            if provider_state != "running":
                command = "start" if provider_state == "stopped" else "up"
                code = await self.stream_command(f"provider.{command}", make_args(command, instance), refresh_instance=instance)
                self.keep_instance_selected(instance)
                if code != 0:
                    return
                if not await self.refresh_provider_until(instance, "running"):
                    self.log_line(
                        "[error]Provider did not report running after the lifecycle command; "
                        "press Refresh and retry Provision.[/]"
                    )
                    return
                self.keep_instance_selected(instance)
            await self.stream_command(
                "instance.provision",
                make_args("instance.provision", instance),
                refresh_instance=instance,
            )

    def action_queue_provision(self) -> None:
        self.start_task(self.action_provision())

    async def action_logs(self) -> None:
        if self.current_instance:
            await self.stream_command("logs", make_args("logs", self.current_instance))

    async def action_package(self, target: str) -> None:
        if not self.current_instance or not self.current_package:
            return
        instance = self.current_instance
        await self.stream_command(
            target,
            package_make_args(target, instance, self.current_package),
            refresh_instance=instance,
        )

    async def action_bundle(self, target: str) -> None:
        if not self.current_instance or not self.current_bundle:
            return
        instance = self.current_instance
        await self.stream_command(
            target,
            bundle_make_args(target, instance, self.current_bundle),
            refresh_instance=instance,
        )

    def action_package_down(self) -> None:
        if not self.current_instance or not self.current_package:
            return
        instance = self.current_instance
        package = self.current_package
        self.push_screen(
            ConfirmScreen(
                "Remove package?",
                f"Uninstall {package} from {instance}. This may remove configs/data.",
            ),
            lambda confirmed: self.start_task(self.perform_package_down(instance, package)) if confirmed else None,
        )

    async def perform_package_down(self, instance: str, package: str) -> None:
        await self.stream_command(
            "package.uninstall",
            package_make_args("package.uninstall", instance, package, "YES=1"),
            refresh_instance=instance,
        )

    def action_package_reinstall(self) -> None:
        if not self.current_instance or not self.current_package:
            return
        instance = self.current_instance
        package = self.current_package
        self.push_screen(
            ConfirmScreen(
                "Reinstall package?",
                f"Reinstall {package} on {instance}. This may remove configs/data first.",
            ),
            lambda confirmed: self.start_task(self.perform_package_reinstall(instance, package)) if confirmed else None,
        )

    async def perform_package_reinstall(self, instance: str, package: str) -> None:
        await self.stream_command(
            "package.reinstall",
            package_make_args("package.reinstall", instance, package, "YES=1"),
            refresh_instance=instance,
        )

    async def action_connect_ssh(self) -> None:
        if not self.current_instance:
            return
        instance = self.current_instance
        self.log_line(f"[primary]Opening inline SSH for {instance}. Exit SSH to return to the TUI.[/]")
        self.refresh()
        await asyncio.sleep(0.05)
        with self.suspend():
            code = subprocess.call(make_args("ssh", instance), cwd=ROOT, env=os.environ.copy())
        if code == 0:
            self.log_line("[success]ssh session closed.[/]")
        else:
            self.log_line(f"[error]ssh failed with exit {code}.[/]")

    async def action_package_remote(self, index: int) -> None:
        if not self.current_instance or index >= len(self.current_remote_actions):
            return
        instance = self.current_instance
        action = self.current_remote_actions[index]
        package = action["package"]
        action_id = action["id"]
        label = action["label"]
        prompt = action.get("prompt")
        if isinstance(prompt, dict):
            choices: list[tuple[str, str, Literal["default", "primary", "success", "warning", "error"]]] = []
            for choice in prompt.get("choices", []):
                if not isinstance(choice, dict):
                    continue
                value = str(choice.get("value") or "")
                choice_label = str(choice.get("label") or "")
                variant = cast(
                    Literal["default", "primary", "success", "warning", "error"],
                    str(choice.get("variant") or "default"),
                )
                if value and choice_label:
                    choices.append((value, choice_label, variant))
            env_name = str(prompt.get("env") or "")
            if not choices or not env_name:
                self.log_line(f"[error]{label} has invalid prompt metadata.[/]")
                return
            self.push_screen(
                ChoiceScreen(
                    str(prompt.get("title") or label),
                    str(prompt.get("message") or "Choose an option."),
                    choices,
                ),
                lambda viewer: self.start_task(
                    self.perform_package_remote(instance, package, action_id, label, {env_name: viewer})
                )
                if viewer
                else None,
            )
            return
        await self.perform_package_remote(instance, package, action_id, label)

    async def perform_package_remote(
        self,
        instance: str,
        package: str,
        action_id: str,
        label: str,
        env: dict[str, str] | None = None,
    ) -> None:
        code = await self.stream_command(
            f"package.action.{package}.{action_id}",
            [
                "make",
                "--no-print-directory",
                "package.action",
                f"INSTANCE={instance}",
                f"PACKAGE={package}",
                f"ACTION={action_id}",
            ],
            refresh_instance=instance,
            env=env,
        )
        if code == 0:
            self.log_line(f"[success]{label} completed.[/]")

    def package_entry(self) -> dict[str, Any] | None:
        if not self.current_status or not self.current_package:
            return None
        packages = self.current_status.get("packages", {}).get("all", [])
        for package in packages:
            if isinstance(package, dict) and package.get("id") == self.current_package:
                return package
        return None

    def bundle_selected(self) -> bool:
        if not self.current_status or not self.current_bundle:
            return False
        return self.current_bundle in self.selected_bundle_ids(self.current_status)

    def installed_package_actions(self) -> list[dict[str, Any]]:
        if not self.current_status:
            return []
        package_rows = self.current_status.get("packages", {}).get("all", [])
        provision_state = str(self.current_status.get("state", {}).get("provision_state", "unknown"))
        os_family = str(self.current_status.get("instance", {}).get("os_family", ""))
        state_doc = self.current_status.get("state", {})
        provider_available = provider_actions_available(cast(dict[str, Any], state_doc)) if isinstance(state_doc, dict) else False
        actions: list[dict[str, Any]] = []
        for package in package_rows:
            if not isinstance(package, dict):
                continue
            package_id = str(package.get("id") or "")
            state = package.get("state", {}) or {}
            status = state.get("status")
            effectively_installed = status in {"installed", "running", "reinstalled"} or (
                status in {None, "unknown"} and bool(package.get("selected")) and provision_state == "provisioned"
            )
            for action in package.get("actions", []):
                if not isinstance(action, dict):
                    continue
                native_action = bool(action.get("native"))
                native_without_install = native_action and os_family == "windows"
                if not effectively_installed and not (native_without_install and provider_available and bool(package.get("supported"))):
                    continue
                if not action_allowed_for_instance(action, package_id, os_family):
                    continue
                action_id = str(action.get("id") or "")
                label = str(action.get("label") or "")
                if package_id and action_id and label:
                    next_action = dict(action)
                    next_action["package"] = package_id
                    next_action["id"] = action_id
                    next_action["label"] = label
                    actions.append(next_action)
        return actions[:PACKAGE_ACTION_BUTTONS]

    def provider_manifest_actions(self) -> list[dict[str, Any]]:
        if not self.current_status:
            return []
        action_rows = self.current_status.get("provider_actions", [])
        actions: list[dict[str, Any]] = []
        if not isinstance(action_rows, list):
            return actions
        for action in action_rows:
            if not isinstance(action, dict):
                continue
            action_id = str(action.get("id") or "")
            label = str(action.get("label") or "")
            target = str(action.get("target") or "")
            if action_id and label and target:
                next_action = dict(action)
                next_action["id"] = action_id
                next_action["label"] = label
                next_action["target"] = target
                actions.append(next_action)
        return actions[:PROVIDER_ACTION_BUTTONS]

    def set_button(self, button_id: str, *, disabled: bool, hide_when_disabled: bool = True) -> None:
        button = self.query_one(f"#{button_id}", Button)
        button.disabled = disabled
        if hide_when_disabled:
            button.display = self.show_disabled or not disabled

    def restore_focus(self, focused_id: str | None) -> None:
        if not focused_id:
            return
        with suppress(Exception):
            widget = self.query_one(f"#{focused_id}")
            if isinstance(widget, Button) and (widget.disabled or not widget.display):
                return
            widget.focus()

    def focus_top_action(self) -> None:
        self.set_detail_tab("overview", focus=False)
        for button_id in (
            "provider-up",
            "provider-stop",
            "reboot",
            "provision",
            "connect-ssh",
            "refresh",
            "update-tools",
            "upload",
            "show-password",
            "logs",
            *(f"provider-action-{index}" for index in range(PROVIDER_ACTION_BUTTONS)),
            *(f"pkg-action-{index}" for index in range(PACKAGE_ACTION_BUTTONS)),
            "bundle-select",
            "bundle-unselect",
            "provider-down",
            "instance-recover",
            "delete-instance",
        ):
            button = self.query_one(f"#{button_id}", Button)
            if not button.disabled and button.display:
                button.focus()
                return

    def set_detail_tab(self, tab: str, *, focus: bool = True) -> None:
        if tab not in {"overview", "packages", "ops"}:
            tab = "overview"
        self.detail_tab = tab
        self.update_detail_tabs()
        if focus:
            first_focus = {
                "overview": "provider-up",
                "packages": "bundles",
                "ops": "provider-down",
            }[tab]
            with suppress(Exception):
                self.query_one(f"#{first_focus}").focus()

    def update_detail_tabs(self) -> None:
        for tab in ("overview", "packages", "ops"):
            active = tab == self.detail_tab
            with suppress(Exception):
                self.query_one(f"#{tab}-tab", Vertical).display = active
            with suppress(Exception):
                button = self.query_one(f"#tab-{tab}", Button)
                button.label = f"[b]{tab.title()}[/b]" if active else tab.title()
                button.variant = "primary" if active else "default"

    def update_action_state(self) -> None:
        focused_id = self.focused.id if self.focused is not None else None
        has_instance = self.current_instance is not None
        state = self.current_status.get("state", {}) if self.current_status else {}
        provision_state = str(state.get("provision_state", "unknown"))
        display_provider_state = str(state.get("effective_provider_state", "unknown"))
        provider_available = provider_actions_available(cast(dict[str, Any], state))
        provider_busy = display_provider_state == "changing"
        self.current_provider_actions = self.provider_manifest_actions()
        self.current_remote_actions = self.installed_package_actions()

        busy = self.command_running
        self.update_busy_layout()
        self.set_button("refresh", disabled=busy)
        self.set_button("busy-cancel-command", disabled=not busy, hide_when_disabled=False)
        for index in range(PROVIDER_ACTION_BUTTONS):
            button = self.query_one(f"#provider-action-{index}", Button)
            if index < len(self.current_provider_actions):
                action = self.current_provider_actions[index]
                target = str(action.get("target") or "")
                button.label = str(action["label"])
                disabled = busy or not has_instance or (provider_busy and target != "provider.status")
                button.display = self.show_disabled or not disabled
                button.disabled = disabled
            else:
                button.label = ""
                button.display = False
                button.disabled = True
        provider_up = self.query_one("#provider-up", Button)
        provider_up.label = "Start" if display_provider_state == "stopped" else "Up"
        self.set_button(
            "provider-up",
            disabled=busy or not has_instance or provider_busy or display_provider_state == "running",
        )
        self.set_button(
            "provider-stop",
            disabled=(
                busy
                or not has_instance
                or provider_busy
                or display_provider_state in {"unknown", "stopped", "absent"}
            ),
        )
        self.set_button(
            "reboot",
            disabled=busy or not has_instance or provider_busy or not provider_available,
        )
        self.set_button(
            "provision",
            disabled=(
                busy
                or not has_instance
                or provider_busy
                or provision_state == "provisioning"
            ),
        )
        self.set_button("logs", disabled=busy or not has_instance or not provider_available)
        self.set_button("update-tools", disabled=busy or not has_instance or not provider_available)
        self.set_button("upload", disabled=busy or not has_instance or not provider_available)
        self.set_button(
            "show-password",
            disabled=busy or not has_instance or not provider_available or not password_supported(self.current_status),
        )
        self.set_button(
            "provider-down",
            disabled=busy or not has_instance or provider_busy or display_provider_state in {"absent", "unknown"},
        )
        self.set_button("instance-recover", disabled=busy or not has_instance)
        self.set_button("delete-instance", disabled=busy or not has_instance)
        self.set_button("connect-ssh", disabled=busy or not has_instance or not provider_available)
        for index in range(PACKAGE_ACTION_BUTTONS):
            button = self.query_one(f"#pkg-action-{index}", Button)
            if index < len(self.current_remote_actions):
                action = self.current_remote_actions[index]
                button.label = action["label"]
                disabled = busy or not has_instance or not provider_available
                button.display = self.show_disabled or not disabled
                button.disabled = disabled
            else:
                button.label = ""
                button.display = False
                button.disabled = True

        package = self.package_entry()
        has_package = package is not None
        supported = bool(package.get("supported")) if package else False
        installable = bool(package.get("installable")) if package else False
        selected = bool(package.get("selected")) if package else False
        selected_by = package.get("selected_by", []) if package else []
        directly_selected = isinstance(selected_by, list) and "direct" in selected_by
        package_disabled = busy or not has_instance or not has_package or not supported or not installable

        self.set_button("package-status", disabled=package_disabled)
        self.set_button("package-select", disabled=package_disabled or selected)
        self.set_button(
            "package-unselect",
            disabled=busy or not has_instance or not has_package or not directly_selected,
        )
        self.set_button("package-install", disabled=package_disabled)
        self.set_button("package-reinstall", disabled=package_disabled)
        self.set_button("package-down", disabled=package_disabled)

        has_bundle = self.current_bundle is not None
        bundle_selected = self.bundle_selected()
        self.set_button("bundle-select", disabled=busy or not has_instance or not has_bundle or bundle_selected)
        self.set_button(
            "bundle-unselect",
            disabled=busy or not has_instance or not has_bundle or not bundle_selected,
            )
        self.restore_focus(focused_id)

    def action_toggle_hidden(self) -> None:
        self.show_disabled = not self.show_disabled
        self.render_detail()
        self.update_action_state()
        self.notify("Showing disabled controls and packages" if self.show_disabled else "Hiding disabled controls and packages")

    def update_busy_layout(self) -> None:
        root = self.query_one("#root", Container)
        summary = self.query_one("#summary", Static)
        output_help = self.query_one("#output-help", Static)
        cancel_button = self.query_one("#busy-cancel-command", Button)
        cancel_button.display = self.command_running
        if self.command_running:
            root.add_class("busy")
            label = self.current_command_label or "command"
            summary.update(f"[warning]Running {label}[/]  [dim]press Ctrl-C or c to cancel; y copies output[/dim]")
            output_help.update(
                "Output is expanded while the command runs.\n"
                "Press Ctrl-C or c to cancel, l to focus/scroll, y to copy selected/all log text."
            )
        else:
            root.remove_class("busy")
            summary.update(format_aggregate(self._cached_aggregate))
            output_help.update(
                "Output  |  press l to focus, arrows/PageUp/PageDown to scroll, y to copy selected/all log text"
            )

    def action_focus_log(self) -> None:
        output = self.query_one("#output", TextArea)
        output.focus()
        output.scroll_end(animate=False, force=True)

    def _write_clipboard(self, text: str) -> None:
        self.copy_to_clipboard(text)
        if sys.platform == "darwin" and shutil.which("pbcopy"):
            subprocess.run(["pbcopy"], input=text, text=True, check=False)

    def action_copy_log(self) -> None:
        output = self.query_one("#output", TextArea)
        selected_text = getattr(output, "selected_text", "") or ""
        text = selected_text if selected_text else output.text
        label = "selected log text" if selected_text else "log output"
        self._write_clipboard(text)
        self.notify(f"Copied {label}")

    def on_text_area_selection_changed(self, event: TextArea.SelectionChanged) -> None:
        if event.text_area.id != "output":
            return
        if getattr(event.text_area, "selected_text", ""):
            # Debounce: copy + notify once the selection settles (i.e. the mouse
            # is released), not on every intermediate drag step.
            if self._copy_selection_timer is not None:
                self._copy_selection_timer.stop()
            self._copy_selection_timer = self.set_timer(0.3, self._copy_selected_output)

    def _copy_selected_output(self) -> None:
        self._copy_selection_timer = None
        output = self.query_one("#output", TextArea)
        selected_text = getattr(output, "selected_text", "") or ""
        if not selected_text:
            return
        self._write_clipboard(selected_text)
        self.notify("Copied selected log text")

    def focus_button_relative(self, key: str) -> bool:
        if not isinstance(self.focused, Button):
            return False
        parent = self.focused.parent
        if parent is None:
            return False
        buttons = [
            child
            for child in parent.children
            if isinstance(child, Button) and child.display and not child.disabled
        ]
        if len(buttons) < 2 or self.focused not in buttons:
            return False
        current = buttons.index(self.focused)
        columns = 5 if parent.id == "remote-strip" else (
            4 if parent.id in {"lifecycle-strip", "utility-strip", "provider-debug-strip"} else 3 if parent.id in {
                "package-actions",
                "bundle-actions",
                "danger-strip",
            } else len(buttons)
        )
        delta = {
            "left": -1,
            "right": 1,
            "up": -columns,
            "down": columns,
        }.get(key)
        if delta is None:
            return False
        target = max(0, min(len(buttons) - 1, current + delta))
        if target == current:
            return False
        buttons[target].focus()
        return True

    def on_key(self, event: Any) -> None:
        if event.key in {"ctrl+c", "c"} and self.command_running:
            event.stop()
            self.start_task(self.action_cancel_command())
            return
        if isinstance(self.focused, Input):
            return
        if event.key in {"left", "right", "up", "down"} and self.focus_button_relative(event.key):
            event.stop()
            return
        if event.key == "l":
            event.stop()
            self.action_focus_log()
        elif event.key == "y":
            event.stop()
            self.action_copy_log()

    async def action_help(self) -> None:
        self.log_line(
            "[b]Keys[/b] / filter, h show/hide disabled, l log, y copy log, r refresh, u up, t stop, "
            "p provision, d delete, q quit. "
            "Select << New Instance >> to create an instance."
        )


def run() -> int:
    EveTui().run()
    return 0
