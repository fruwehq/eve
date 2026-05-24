# Auto-extracted from scripts/eve-tui during v3.1 Part 2 §2.3.
"""Modal screen widgets used by the Eve TUI."""

from __future__ import annotations

from typing import Any, Literal, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    SelectionList,
    Static,
    TextArea,
)
from textual.widgets.selection_list import Selection

from textual.message import Message

from tui.commands import (
    catalog_options,
    create_instance_args,
    provider_has_capability,
)
from tui.render import (
    command_label,
    package_summary_label,
)
from tui.settings import (
    CONFIG_SECTIONS,
    field_label,
    load_provider_schema,
    load_provider_secrets,
    load_structured,
    save_provider_secret,
    save_value,
    unset_value,
)


class ProviderPane(Static):
    DEFAULT_CSS = """
    ProviderPane {
        height: auto;
        margin-bottom: 1;
    }

    .provider-row {
        height: 3;
        layout: horizontal;
        margin-bottom: 0;
    }

    .provider-name {
        width: 12;
        height: 3;
        content-align: left middle;
        padding-left: 1;
    }

    .provider-reachability {
        width: 4;
        height: 3;
        content-align: center middle;
    }

    .provider-actions-row {
        height: 3;
    }

    .provider-actions-row Button {
        height: 3;
        min-width: 10;
    }
    """

    class ActionRequested(Message):
        def __init__(self, provider_id: str, action: dict[str, Any]) -> None:
            super().__init__()
            self.provider_id = provider_id
            self.action = action

    class ConfigureRequested(Message):
        def __init__(self, provider_id: str) -> None:
            super().__init__()
            self.provider_id = provider_id

    class TestConnectionRequested(Message):
        def __init__(self, provider_id: str) -> None:
            super().__init__()
            self.provider_id = provider_id

    def __init__(
        self,
        providers: list[dict[str, Any]],
        reachability: dict[str, bool] | None = None,
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.providers = providers
        self.reachability = reachability or {}
        self._provider_ids: list[str] = []

    def compose(self) -> ComposeResult:
        self._provider_ids = []
        for provider in self.providers:
            provider_id = str(provider.get("id", ""))
            self._provider_ids.append(provider_id)
            display_name = str(provider.get("display_name", provider_id))
            actions = provider.get("actions", [])
            reachable = self.reachability.get(provider_id)
            if reachable is True:
                reach_text = "[success]●[/]"
            elif reachable is False:
                reach_text = "[warning]○[/]"
            else:
                reach_text = "[dim]?[/]"
            with Horizontal(classes="provider-row"):
                yield Static(display_name, classes="provider-name")
                yield Static(reach_text, classes="provider-reachability")
                with Horizontal(classes="provider-actions-row"):
                    for action in actions:
                        label = str(action.get("label") or action.get("id", ""))
                        button = Button(label, id=f"ppa-{provider_id}-{action.get('id', '')}")
                        button.variant = "primary" if bool(action.get("interactive")) else "default"
                        yield button
                    yield Button("Configure", id=f"ppc-{provider_id}", variant="success")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("ppc-"):
            provider_id = button_id[4:]
            event.stop()
            self.post_message(self.ConfigureRequested(provider_id))
            return
        if not button_id.startswith("ppa-"):
            return
        rest = button_id[4:]
        for provider in self.providers:
            provider_id = str(provider.get("id", ""))
            prefix = f"{provider_id}-"
            if rest.startswith(prefix):
                action_id = rest[len(prefix):]
                for action in provider.get("actions", []):
                    if str(action.get("id")) == action_id:
                        event.stop()
                        self.post_message(self.ActionRequested(provider_id, action))
                        return

    def update_reachability(self, reachability: dict[str, bool]) -> None:
        self.reachability = reachability
        rows = self.query(".provider-row")
        for idx, row in enumerate(rows):
            if idx >= len(self._provider_ids):
                break
            provider_id = self._provider_ids[idx]
            reach_widget = row.query_one(".provider-reachability", Static)
            reachable = reachability.get(provider_id)
            if reachable is True:
                reach_widget.update("[success]●[/]")
            elif reachable is False:
                reach_widget.update("[warning]○[/]")
            else:
                reach_widget.update("[dim]?[/]")


class ConfirmScreen(ModalScreen[bool]):
    CSS = """
    ConfirmScreen {
        align: center middle;
    }

    #confirm-dialog {
        width: 72;
        height: 12;
        border: round $error;
        background: $surface;
        padding: 1 2;
    }

    #confirm-message {
        margin-bottom: 1;
    }

    #confirm-actions {
        height: 3;
        width: 28;
        background: transparent;
    }

    #confirm-actions Button {
        width: 12;
        min-width: 12;
    }
    """

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self.dialog_title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog"):
            yield Label(f"[b]{self.dialog_title}[/b]")
            yield Static(self.message, id="confirm-message")
            with Horizontal(id="confirm-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Confirm", id="confirm", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "confirm")

class ChoiceScreen(ModalScreen[str | None]):
    CSS = """
    ChoiceScreen {
        align: center middle;
    }

    #choice-dialog {
        width: 72;
        height: 13;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    #choice-message {
        margin-bottom: 1;
    }

    #choice-actions {
        height: 3;
        background: transparent;
    }

    #choice-actions Button {
        width: 1fr;
        min-width: 14;
    }
    """

    def __init__(
        self,
        title: str,
        message: str,
        choices: list[tuple[str, str, Literal["default", "primary", "success", "warning", "error"]]],
    ) -> None:
        super().__init__()
        self.dialog_title = title
        self.message = message
        self.choices = choices

    def compose(self) -> ComposeResult:
        with Vertical(id="choice-dialog"):
            yield Label(f"[b]{self.dialog_title}[/b]")
            yield Static(self.message, id="choice-message")
            with Horizontal(id="choice-actions"):
                for choice_id, label, variant in self.choices:
                    yield Button(label, id=choice_id, variant=variant)
                yield Button("Cancel", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        self.dismiss(None if button_id == "cancel" else button_id)

class UploadScreen(ModalScreen[list[str] | None]):
    CSS = """
    UploadScreen {
        align: center middle;
    }

    #upload-dialog {
        width: 72;
        height: 20;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    #upload-list {
        height: 10;
        margin: 1 0;
    }

    #upload-actions {
        height: 3;
        width: 40;
        background: transparent;
    }

    #upload-actions Button {
        width: 1fr;
        min-width: 12;
    }
    """

    def __init__(self, folders: list[str]) -> None:
        super().__init__()
        self.folders = folders

    def compose(self) -> ComposeResult:
        with Vertical(id="upload-dialog"):
            yield Label("[b]Upload folders[/b]")
            yield Static("Choose direct subfolders from upload/. Space toggles, Enter starts upload.")
            yield SelectionList(
                *[Selection(folder, folder, False) for folder in self.folders],
                id="upload-list",
            )
            with Horizontal(id="upload-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Upload", id="confirm", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#upload-list", SelectionList).focus()

    def on_key(self, event: Any) -> None:
        if event.key != "enter":
            return
        event.stop()
        self.dismiss(list(self.query_one("#upload-list", SelectionList).selected))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        self.dismiss(list(self.query_one("#upload-list", SelectionList).selected))

class NewInstanceScreen(ModalScreen[dict[str, str] | None]):
    CSS = """
    NewInstanceScreen {
        align: center middle;
    }

    #new-dialog {
        width: 118;
        max-width: 96%;
        height: auto;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    Input,
    SelectionList {
        margin-bottom: 1;
    }

    Horizontal {
        background: transparent;
    }

    #override-row Input {
        width: 1fr;
        margin-right: 1;
    }

    #provider-ip {
        margin-bottom: 1;
    }

    #content-selects {
        height: 18;
        margin-bottom: 1;
    }

    .content-column {
        width: 1fr;
        margin-right: 1;
    }

    #platform-cards {
        height: 16;
        margin-bottom: 1;
    }

    #bundle-select {
        height: 10;
    }

    #package-select {
        height: 14;
    }

    #bundle-preview {
        height: 4;
        margin-bottom: 1;
    }

    #included-packages {
        height: 2;
        margin-bottom: 1;
    }

    #wizard-actions {
        height: 3;
        width: 52;
        background: transparent;
    }

    #wizard-actions Button {
        width: 12;
        min-width: 12;
    }

    .wizard-hidden {
        display: none;
    }

    .muted {
        color: $text-muted;
    }

    #wizard-steps {
        height: 1;
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        options: dict[str, Any],
    ) -> None:
        super().__init__()
        self.platforms = [
            cast(dict[str, Any], platform)
            for platform in options.get("platforms", [])
            if isinstance(platform, dict)
        ]
        self.bundles = [
            cast(dict[str, Any], bundle) for bundle in options.get("bundles", []) if isinstance(bundle, dict)
        ]
        self.bundle_map = {str(bundle.get("id")): bundle for bundle in self.bundles if bundle.get("id")}
        self.packages = [
            cast(dict[str, Any], package)
            for package in options.get("packages", [])
            if isinstance(package, dict) and package.get("id")
        ]
        self.package_map = {str(package.get("id")): package for package in self.packages if package.get("id")}
        self.package_ids = sorted(self.package_map)
        self.step = 0
        self.selected_platform_id = ""
        self.highlighted_bundle_id = ""
        self.highlighted_package_id = ""
        self.rendered_bundle_signature: tuple[Any, ...] | None = None
        self.rendered_bundled_package_ids: set[str] = set()
        self.rendered_package_signature: tuple[Any, ...] | None = None
        self.platform_by_id = {
            str(platform_choice.get("id")): platform_choice
            for platform_choice in self.platforms
            if platform_choice.get("id")
        }

    def compose(self) -> ComposeResult:
        with Vertical(id="new-dialog"):
            yield Label("", id="wizard-steps")
            with Vertical(id="step-name"):
                yield Input(placeholder="instance name", id="new-name")
                yield Static("Use a short lowercase name, for example dev-a or windows-test.", classes="muted")
            with Vertical(id="step-platform"):
                yield Static("Choose a supported provider / machine / OS / location combination.", classes="muted")
                yield DataTable(id="platform-cards")
                yield Static("", id="platform-defaults")
            with Vertical(id="step-content"):
                yield Input(placeholder="Provider IP address", id="provider-ip")
                yield Static("Required for metal instances that need a provider IP. The shared SSH key remains global.", id="provider-ip-help", classes="muted")
                with Horizontal(id="content-selects"):
                    with Vertical(classes="content-column"):
                        yield Static("Bundles", classes="muted")
                        yield SelectionList(id="bundle-select", disabled=not self.bundles)
                        yield Static("", id="bundle-preview", classes="muted")
                    with Vertical(classes="content-column"):
                        yield Static("Additional packages", classes="muted")
                        yield SelectionList(id="package-select", disabled=not self.package_ids)
                        yield Static("", id="package-compatibility", classes="muted")
                yield Static("", id="included-packages", classes="muted")
                yield Static("", id="resource-defaults")
                with Horizontal(id="override-row"):
                    yield Input(placeholder="disk GB override", id="new-disk")
                    yield Input(placeholder="memory MB override", id="new-memory")
            with Vertical(id="step-review"):
                yield Static("", id="review")
            with Horizontal(id="wizard-actions"):
                yield Button("Back", id="back")
                yield Button("Cancel", id="cancel")
                yield Button("Next", id="next", variant="primary")
                yield Button("Create", id="create", variant="success")

    def on_mount(self) -> None:
        self.populate_platform_cards()
        self.update_wizard()

    def bundle_label(self, bundle: dict[str, Any]) -> str:
        includes = bundle.get("includes", [])
        include_text = ", ".join(str(package) for package in includes) if isinstance(includes, list) else ""
        return f"{bundle.get('id')}\n  {include_text}" if include_text else str(bundle.get("id"))

    def wizard_step_label(self) -> str:
        parts = []
        for index, label in enumerate(("1 Name", "2 Platform", "3 Content", "4 Review")):
            if index == self.step:
                parts.append(f"[b][primary]▶ {label}[/][/b]")
            elif index < self.step:
                parts.append(f"[success]{label}[/]")
            else:
                parts.append(f"[dim]{label}[/]")
        return "[b]New Instance[/b]  " + " [dim]->[/] ".join(parts)

    def populate_platform_cards(self) -> None:
        table = self.query_one("#platform-cards", DataTable)
        table.cursor_type = "row"
        table.clear(columns=True)
        table.add_columns("Provider", "Machine", "OS", "Location", "Defaults")
        for platform_choice in self.platforms:
            defaults = (
                platform_choice.get("defaults", {}) if isinstance(platform_choice.get("defaults"), dict) else {}
            )
            default_parts = []
            if defaults.get("plan"):
                default_parts.append(str(defaults.get("plan")))
            if defaults.get("instance_type"):
                default_parts.append(str(defaults.get("instance_type")))
            if defaults.get("disk_gb"):
                default_parts.append(f"{defaults.get('disk_gb')} GB")
            memory = defaults.get("memory_mb")
            if memory:
                default_parts.append(f"{memory} MB")
            table.add_row(
                str(platform_choice.get("provider") or "-"),
                str(platform_choice.get("machine") or "-"),
                str(platform_choice.get("os") or "-"),
                str(platform_choice.get("location") or "-"),
                ", ".join(default_parts) if default_parts else "-",
                key=str(platform_choice.get("id")),
            )
        if self.platforms:
            self.selected_platform_id = str(self.platforms[0].get("id"))
            table.move_cursor(row=0, column=0, animate=False)
        else:
            self.selected_platform_id = ""

    def selected_platform(self) -> dict[str, Any]:
        return self.platform_by_id.get(self.selected_platform_id, {})

    def support_values(self, package_id: str, key: str) -> list[str]:
        package = self.package_map.get(package_id, {})
        supports = package.get("supports", {}) if isinstance(package.get("supports"), dict) else {}
        values = supports.get(key, [])
        if isinstance(values, list):
            return [str(value) for value in values]
        return []

    def support_reason(self, package_id: str) -> str | None:
        platform_choice = self.selected_platform()
        if not platform_choice:
            return None

        checks = [
            ("os_families", str(platform_choice.get("os_family") or ""), "OS family"),
            ("arches", str(platform_choice.get("arch") or ""), "architecture"),
            ("os_ids", str(platform_choice.get("os") or ""), "OS"),
            ("os_versions", str(platform_choice.get("os_version") or ""), "OS version"),
        ]
        os_family = str(platform_choice.get("os_family") or "")
        os_version = str(platform_choice.get("os_version") or "")
        if os_family and os_version:
            checks.append((f"{os_family}_versions", os_version, f"{os_family} version"))

        for key, actual, label in checks:
            allowed = self.support_values(package_id, key)
            if allowed and actual and actual not in allowed:
                return f"requires {label} {'/'.join(allowed)}"
        return None

    def package_supported(self, package_id: str) -> bool:
        return self.support_reason(package_id) is None

    def package_installable_on_platform(self, package_id: str) -> bool:
        platform_choice = self.selected_platform()
        os_family = str(platform_choice.get("os_family") or "")
        package = self.package_map.get(package_id, {})
        installable_os_families = package.get("installable_os_families", [])
        if isinstance(installable_os_families, list):
            return os_family in [str(value) for value in installable_os_families]
        return False

    def package_select_reason(self, package_id: str) -> str | None:
        reason = self.support_reason(package_id)
        if reason:
            return reason
        conflict_reason = self.package_conflict_reason(
            package_id,
            self.content_package_ids(extra_package_id=package_id),
        )
        if conflict_reason:
            return conflict_reason
        if not self.package_installable_on_platform(package_id):
            return "native action only on this OS"
        compatibility_reason = self.package_compatibility_reason(
            package_id,
            self.content_package_ids(extra_package_id=package_id),
        )
        if compatibility_reason:
            return compatibility_reason
        return None

    def bundle_support_reason(self, bundle_id: str) -> str | None:
        prospective_packages = self.content_package_ids(extra_bundle_id=bundle_id)
        for package_id in self.bundle_includes(bundle_id):
            reason = self.support_reason(package_id)
            if reason:
                return f"{package_id}: {reason}"
            conflict_reason = self.package_conflict_reason(package_id, prospective_packages)
            if conflict_reason:
                return f"{package_id}: {conflict_reason}"
            compatibility_reason = self.package_compatibility_reason(package_id, prospective_packages)
            if compatibility_reason:
                return f"{package_id}: {compatibility_reason}"
        return None

    def supported_selected_bundles(self) -> list[str]:
        return [bundle_id for bundle_id in self.selected_bundles() if not self.bundle_support_reason(bundle_id)]

    def raw_selected_bundles(self) -> list[str]:
        selected = self.query_one("#bundle-select", SelectionList).selected
        return [str(bundle) for bundle in selected]

    def raw_selected_packages(self) -> list[str]:
        selected = self.query_one("#package-select", SelectionList).selected
        return [str(package) for package in selected]

    def content_package_ids(self, extra_bundle_id: str = "", extra_package_id: str = "") -> set[str]:
        packages = set(self.raw_selected_packages())
        if extra_package_id:
            packages.add(extra_package_id)
        bundle_ids = set(self.raw_selected_bundles())
        if extra_bundle_id:
            bundle_ids.add(extra_bundle_id)
        for bundle_id in bundle_ids:
            packages.update(self.bundle_includes(bundle_id))
        return packages

    def compatibility_target(self, package_ids: set[str]) -> dict[str, str]:
        platform_choice = self.selected_platform()
        os_family = str(platform_choice.get("os_family") or "")
        if os_family == "windows":
            return {"platform": "windows", "desktop": "Windows", "session": "Native"}
        if os_family == "ubuntu" and "gnome-desktop-headless" in package_ids:
            return {"platform": "ubuntu", "desktop": "GNOME Headless", "session": "Wayland"}
        if os_family == "ubuntu" and "gnome-desktop" in package_ids:
            return {"platform": "ubuntu", "desktop": "GNOME", "session": "Wayland"}
        if os_family == "ubuntu" and "kde-desktop-headless" in package_ids:
            return {"platform": "ubuntu", "desktop": "KDE Plasma Headless", "session": "Wayland"}
        if os_family == "ubuntu" and "kde-desktop" in package_ids:
            return {"platform": "ubuntu", "desktop": "KDE Plasma", "session": "Wayland"}
        if os_family == "ubuntu" and "xfce-desktop-headless" in package_ids:
            return {"platform": "ubuntu", "desktop": "XFCE Headless", "session": "X11"}
        if os_family == "ubuntu":
            return {"platform": "ubuntu", "desktop": "XFCE", "session": "X11"}
        return {"platform": os_family, "desktop": "", "session": ""}

    def package_conflict_reason(self, package_id: str, package_ids: set[str]) -> str | None:
        package = self.package_map.get(package_id, {})
        conflicts = package.get("conflicts_with", [])
        if not isinstance(conflicts, list):
            return None
        for conflict in [str(value) for value in conflicts]:
            if conflict in package_ids and conflict != package_id:
                return f"conflicts with {conflict}"
        return None

    def package_compatibility_reason(self, package_id: str, package_ids: set[str]) -> str | None:
        package = self.package_map.get(package_id, {})
        if package.get("compatibility_enforced") is not True:
            return None
        entries = package.get("compatibility", [])
        if not isinstance(entries, list):
            return "no supported compatibility matrix"

        target = self.compatibility_target(package_ids)
        for entry in entries:
            if not isinstance(entry, dict) or str(entry.get("status") or "") != "supported":
                continue
            if str(entry.get("platform") or "") != target["platform"]:
                continue
            desktop = str(entry.get("desktop") or "")
            session = str(entry.get("session") or "")
            if desktop and desktop != target["desktop"]:
                continue
            if session and session != target["session"]:
                continue
            return None

        target_label = " / ".join(value for value in (target["platform"], target["desktop"], target["session"]) if value)
        return f"no supported {target_label} row"

    def selected_packages(self) -> list[str]:
        selected = self.query_one("#package-select", SelectionList).selected
        return [
            str(package)
            for package in selected
            if self.package_installable_on_platform(str(package)) and self.package_select_reason(str(package)) is None
        ]

    def selected_bundles(self) -> list[str]:
        selected = self.query_one("#bundle-select", SelectionList).selected
        return [str(bundle) for bundle in selected if not self.bundle_support_reason(str(bundle))]

    def bundled_packages(self) -> list[str]:
        packages: list[str] = []
        for bundle_id in self.supported_selected_bundles():
            bundle = self.bundle_map.get(bundle_id, {})
            includes = bundle.get("includes", [])
            if isinstance(includes, list):
                packages.extend(str(package) for package in includes)
        return sorted(set(packages))

    def bundle_includes(self, bundle_id: str) -> list[str]:
        bundle = self.bundle_map.get(bundle_id, {})
        includes = bundle.get("includes", [])
        if isinstance(includes, list):
            return [str(package) for package in includes]
        return []

    def bundle_option_label(self, bundle: dict[str, Any], reason: str | None) -> str:
        label = self.bundle_label(bundle)
        if reason:
            return f"{label}\n  unsupported on this platform: {reason}"
        return label

    def package_option_label(self, package_id: str, reason: str | None) -> str:
        if reason:
            return f"{package_id}  ({reason})"
        return package_id

    def sync_bundle_options(self) -> None:
        bundle_list = self.query_one("#bundle-select", SelectionList)
        selected = set(self.selected_bundles())
        reasons = {str(bundle.get("id")): self.bundle_support_reason(str(bundle.get("id"))) for bundle in self.bundles}
        signature = (
            self.selected_platform_id,
            tuple(sorted((bundle_id, reason or "") for bundle_id, reason in reasons.items())),
        )
        if signature == self.rendered_bundle_signature and bundle_list.option_count:
            return

        highlighted = bundle_list.highlighted
        bundle_options: list[Any] = []
        for bundle in self.bundles:
            bundle_id = str(bundle.get("id") or "")
            if not bundle_id:
                continue
            reason = reasons.get(bundle_id)
            bundle_options.append(
                Selection(
                    self.bundle_option_label(bundle, reason),
                    bundle_id,
                    bundle_id in selected and reason is None,
                    disabled=reason is not None,
                )
            )
        bundle_list.set_options(bundle_options)
        if isinstance(highlighted, int) and bundle_options:
            bundle_list.highlighted = min(highlighted, len(bundle_options) - 1)
        bundle_list.disabled = bundle_list.option_count == 0
        self.rendered_bundle_signature = signature

    def sync_package_options(self) -> None:
        package_list = self.query_one("#package-select", SelectionList)
        bundled = set(self.bundled_packages())
        selected = set(self.selected_packages())
        reasons = {package_id: self.package_select_reason(package_id) for package_id in self.package_ids}
        signature = (
            self.selected_platform_id,
            tuple(sorted(bundled)),
            tuple(sorted((package_id, reason or "") for package_id, reason in reasons.items())),
        )
        if (
            bundled == self.rendered_bundled_package_ids
            and signature == self.rendered_package_signature
            and package_list.option_count
        ):
            return

        highlighted = package_list.highlighted
        package_options: list[Any] = [
            Selection(
                self.package_option_label(package, reasons.get(package)),
                package,
                package in selected and reasons.get(package) is None,
                disabled=reasons.get(package) is not None,
            )
            for package in self.package_ids
            if package not in bundled
        ]
        option_values = [str(option.value) for option in package_options]
        package_list.set_options(package_options)
        if isinstance(highlighted, int) and package_options:
            package_list.highlighted = min(highlighted, len(package_options) - 1)
        if self.highlighted_package_id not in option_values:
            self.highlighted_package_id = option_values[0] if option_values else ""
        package_list.disabled = package_list.option_count == 0
        self.rendered_bundled_package_ids = bundled
        self.rendered_package_signature = signature

    def package_compatibility_text(self, package_id: str) -> str:
        if not package_id:
            return "Highlight a package to see desktop/session compatibility."

        package = self.package_map.get(package_id, {})
        entries = package.get("compatibility", [])
        display_name = str(package.get("display_name") or package_id)
        if not isinstance(entries, list) or not entries:
            return f"{display_name}: no compatibility matrix yet."

        platform_choice = self.selected_platform()
        current_family = str(platform_choice.get("os_family") or platform_choice.get("provider") or "")
        typed_entries = [entry for entry in entries if isinstance(entry, dict)]
        matching = [entry for entry in typed_entries if str(entry.get("platform") or "") == current_family]
        other = [entry for entry in typed_entries if entry not in matching]
        ordered = matching + other

        status_labels = {
            "supported": "SUPPORTED",
            "wip": "WIP",
            "unsupported": "NO",
            "legacy": "LEGACY",
        }
        lines = [f"{display_name} compatibility:"]
        for entry in ordered[:4]:
            status = status_labels.get(str(entry.get("status") or ""), str(entry.get("status") or "-").upper())
            platform = str(entry.get("platform") or "-")
            desktop = str(entry.get("desktop") or "-")
            session = str(entry.get("session") or "-")
            notes = str(entry.get("notes") or "")
            current = " (selected platform)" if platform == current_family else ""
            lines.append(f"{status}: {platform} / {desktop} / {session}{current} - {notes}")
        if len(ordered) > 4:
            lines.append(f"... {len(ordered) - 4} more rows in docs.")
        return "\n".join(lines)

    def platform_default_lines(self, platform_choice: dict[str, Any]) -> list[str]:
        defaults = platform_choice.get("defaults", {}) if isinstance(platform_choice.get("defaults"), dict) else {}
        return [
            f"Provider: {platform_choice.get('provider') or '-'}",
            f"Machine: {platform_choice.get('machine') or '-'}",
            f"OS: {platform_choice.get('os') or '-'}",
            f"Init: {platform_choice.get('init') or '-'}",
            f"Location: {platform_choice.get('location') or '-'}",
            f"Defaults: disk {defaults.get('disk_gb') or '-'} GB, "
            f"memory {defaults.get('memory_mb') or '-'} MB, "
            f"CPU {defaults.get('cpus') or defaults.get('cpu_cores') or defaults.get('vcpus') or '-'}.",
        ]

    def update_wizard(self) -> None:
        self.query_one("#wizard-steps", Label).update(self.wizard_step_label())
        for index, widget_id in enumerate(("step-name", "step-platform", "step-content", "step-review")):
            self.query_one(f"#{widget_id}", Vertical).display = index == self.step

        platform_choice = self.selected_platform()
        provider = str(platform_choice.get("provider") or "")
        provider_ip_widget = self.query_one("#provider-ip", Input)
        provider_ip_help = self.query_one("#provider-ip-help", Static)
        provider_ip_required = provider_has_capability(provider, "needs-provider-ip")
        provider_ip_widget.display = provider_ip_required
        provider_ip_help.display = provider_ip_required
        defaults = platform_choice.get("defaults", {}) if isinstance(platform_choice.get("defaults"), dict) else {}
        self.sync_bundle_options()
        self.sync_package_options()
        self.query_one("#platform-defaults", Static).update("\n".join(self.platform_default_lines(platform_choice)))
        self.query_one("#resource-defaults", Static).update(
            "Leave overrides empty to use platform defaults: "
            f"disk {defaults.get('disk_gb') or '-'} GB, "
            f"memory {defaults.get('memory_mb') or '-'} MB, "
            f"CPU {defaults.get('cpus') or defaults.get('cpu_cores') or defaults.get('vcpus') or '-'}."
        )

        name = self.query_one("#new-name", Input).value.strip() or "<instance>"
        provider_ip = provider_ip_widget.value.strip()
        disk = self.query_one("#new-disk", Input).value.strip()
        memory = self.query_one("#new-memory", Input).value.strip()
        selected_bundles = self.selected_bundles()
        bundled_packages = self.bundled_packages()
        selected_packages = self.selected_packages()
        highlighted_bundle_id = self.highlighted_bundle_id or (selected_bundles[0] if selected_bundles else "")
        highlighted_includes = self.bundle_includes(highlighted_bundle_id)
        package_text = ", ".join(selected_packages) if selected_packages else "(none)"
        bundled_text = ", ".join(bundled_packages) if bundled_packages else "(none)"
        bundle_text = ", ".join(selected_bundles) if selected_bundles else "(none)"
        if highlighted_bundle_id:
            support_note = self.bundle_support_reason(highlighted_bundle_id)
            preview_text = (
                f"Highlighted bundle: {highlighted_bundle_id}\n"
                f"Includes: {', '.join(highlighted_includes) if highlighted_includes else '(none)'}"
            )
            if support_note:
                preview_text += f"\nUnsupported on this platform: {support_note}"
        else:
            preview_text = "Highlight a bundle to preview included packages before selecting it."
        self.query_one("#bundle-preview", Static).update(preview_text)
        highlighted_package_id = self.highlighted_package_id or (selected_packages[0] if selected_packages else "")
        self.query_one("#package-compatibility", Static).update(
            self.package_compatibility_text(highlighted_package_id)
        )
        self.query_one("#included-packages", Static).update(
            "Included by selected bundles (locked): " + bundled_text
        )
        command = create_instance_args(
            name,
            platform_choice,
            ",".join(selected_bundles),
            ",".join(selected_packages),
            disk,
            memory,
            provider_ip if provider_ip_required else "",
        )
        self.query_one("#review", Static).update(
            "\n".join(
                [
                    f"Instance: {name}",
                    *self.platform_default_lines(platform_choice),
                    *([f"Provider IP: {provider_ip or '(required)'}"] if provider_ip_required else []),
                    f"Bundles: {bundle_text}",
                    f"Bundle packages: {bundled_text}",
                    f"Disk override: {disk or '(use platform default)'}",
                    f"Memory override: {memory or '(use platform default)'}",
                    f"Additional packages: {package_text}",
                    "",
                    command_label(command),
                ]
            )
        )

        self.query_one("#back", Button).disabled = self.step == 0
        self.query_one("#next", Button).display = self.step < 3
        self.query_one("#create", Button).display = self.step == 3

    def focus_current_step(self) -> None:
        if self.step == 0:
            self.query_one("#new-name", Input).focus()
        elif self.step == 1:
            self.query_one("#platform-cards", DataTable).focus()
        elif self.step == 2:
            self.query_one("#bundle-select", SelectionList).focus()
        else:
            self.query_one("#create", Button).focus()

    def set_step(self, step: int) -> None:
        self.step = max(0, min(3, step))
        self.update_wizard()
        self.focus_current_step()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "platform-cards":
            self.selected_platform_id = str(event.row_key.value)
            self.update_wizard()

    def on_selection_list_selection_highlighted(self, event: SelectionList.SelectionHighlighted[Any]) -> None:
        if event.selection_list.id == "bundle-select":
            self.highlighted_bundle_id = str(event.selection.value)
            self.update_wizard()
        elif event.selection_list.id == "package-select":
            self.highlighted_package_id = str(event.selection.value)
            self.update_wizard()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "platform-cards":
            self.selected_platform_id = str(event.row_key.value)
            self.set_step(2)

    def on_selection_list_selected_changed(self, event: Any) -> None:
        self.update_wizard()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"new-name", "new-disk", "new-memory", "provider-ip"}:
            self.update_wizard()

    def on_key(self, event: Any) -> None:
        if event.key != "enter":
            return
        if self.step == 0 and self.query_one("#new-name", Input).has_focus:
            event.stop()
            name = self.query_one("#new-name", Input).value.strip()
            if not name:
                self.notify("Name is required", severity="error")
                return
            self.set_step(1)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        if event.button.id == "back":
            self.set_step(self.step - 1)
            return
        if event.button.id == "next":
            name = self.query_one("#new-name", Input).value.strip()
            if self.step == 0 and not name:
                self.notify("Name is required", severity="error")
                return
            if self.step == 1 and not self.selected_platform():
                self.notify("Platform is required", severity="error")
                return
            if (
                self.step == 2
                and provider_has_capability(
                    str(self.selected_platform().get("provider") or ""), "needs-provider-ip"
                )
                and not self.query_one("#provider-ip", Input).value.strip()
            ):
                self.notify("Provider IP address is required", severity="error")
                return
            self.set_step(self.step + 1)
            return
        if event.button.id != "create":
            return
        name = self.query_one("#new-name", Input).value.strip()
        platform_choice = self.selected_platform()
        if not name or not platform_choice:
            self.notify("Name and platform are required", severity="error")
            return
        provider_ip = self.query_one("#provider-ip", Input).value.strip()
        if provider_has_capability(str(platform_choice.get("provider") or ""), "needs-provider-ip") and not provider_ip:
            self.notify("Provider IP address is required", severity="error")
            return
        packages = ",".join(self.selected_packages())
        bundles = ",".join(self.selected_bundles())
        self.dismiss(
            {
                "name": name,
                "machine": str(platform_choice.get("machine") or ""),
                "os": str(platform_choice.get("os") or ""),
                "init": str(platform_choice.get("init") or ""),
                "location": str(platform_choice.get("location") or ""),
                "bundles": bundles,
                "packages": packages,
                "disk_gb": self.query_one("#new-disk", Input).value.strip(),
                "memory_mb": self.query_one("#new-memory", Input).value.strip(),
                "provider_ip": provider_ip if provider_has_capability(str(platform_choice.get("provider") or ""), "needs-provider-ip") else "",
            }
        )


class EditFieldScreen(ModalScreen[str | None]):
    CSS = """
    EditFieldScreen {
        align: center middle;
    }

    #edit-dialog {
        width: 64;
        height: 11;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    #edit-label {
        margin-bottom: 1;
    }

    #edit-input {
        margin-bottom: 1;
    }

    #edit-actions {
        height: 3;
        width: 36;
        background: transparent;
    }

    #edit-actions Button {
        width: 14;
        min-width: 14;
    }
    """

    def __init__(self, label: str, current: str) -> None:
        super().__init__()
        self.field_label_text = label
        self.current_value = current

    def compose(self) -> ComposeResult:
        with Vertical(id="edit-dialog"):
            yield Label(f"[b]{self.field_label_text}[/b]", id="edit-label")
            yield Input(value=self.current_value, id="edit-input")
            with Horizontal(id="edit-actions"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="save", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.dismiss(self.query_one("#edit-input", Input).value.strip())
        else:
            self.dismiss(None)

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss(None)


class SettingsScreen(ModalScreen[None]):
    CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 80;
        height: 32;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    #settings-title {
        text-align: center;
        margin-bottom: 1;
    }

    #settings-table {
        height: 22;
    }

    #settings-actions {
        height: 3;
        width: 24;
        background: transparent;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._structured: dict[str, dict[str, dict[str, Any]]] = {}
        self._row_keys: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-dialog"):
            yield Label("[b]Settings[/b]", id="settings-title")
            table: DataTable[Any] = DataTable(id="settings-table")
            table.add_columns("Section", "Field", "Value", "Source")
            yield table
            with Horizontal(id="settings-actions"):
                yield Button("Reset", id="settings-reset", variant="warning")
                yield Button("Close", id="close")

    BINDINGS = [
        Binding("r", "reset_field", "Reset"),
    ]

    def on_mount(self) -> None:
        self._load_values()

    def _load_values(self) -> None:
        try:
            self._structured = load_structured()
        except Exception:
            self._structured = {}

        table = self.query_one("#settings-table", DataTable)
        table.clear()
        self._row_keys = []

        for section_info in CONFIG_SECTIONS:
            section_id = section_info["id"]
            section_label = section_info["label"]
            fields = self._structured.get(section_id, {})
            if not fields:
                continue
            for field_id in sorted(fields.keys()):
                info = fields[field_id]
                value = info.get("value") or ""
                source = info.get("source") or "unset"
                label = field_label(section_id, field_id)
                source_display = f"[{source}]"
                key = f"{section_id}.{field_id}"
                self._row_keys.append(key)
                table.add_row(section_label, label, value or "\u2014", source_display, key=key)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = str(event.row_key.value)
        section, field = row_key.split(".", 1)
        label = field_label(section, field)
        fields = self._structured.get(section, {})
        info = fields.get(field, {})
        current = info.get("value") or ""

        def handle_edit(result: str | None) -> None:
            if result is not None:
                try:
                    save_value(section, field, result)
                    self._load_values()
                    self.notify(f"Saved {label}")
                except Exception as e:
                    self.notify(f"Save failed: {e}", severity="error")

        self.push_screen(EditFieldScreen(label, current), handle_edit)  # type: ignore[attr-defined]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(None)
        elif event.button.id == "settings-reset":
            self._reset_selected_field()

    def action_reset_field(self) -> None:
        self._reset_selected_field()

    def _reset_selected_field(self) -> None:
        table = self.query_one("#settings-table", DataTable)
        row = table.cursor_row
        if row is None or row < 0 or row >= len(self._row_keys):
            return
        key = self._row_keys[row]
        section, field = key.split(".", 1)
        info = self._structured.get(section, {}).get(field, {})
        if info.get("source") == "config.yaml":
            try:
                unset_value(section, field)
                self._load_values()
                self.notify(f"Reset {field_label(section, field)}")
            except Exception as e:
                self.notify(f"Reset failed: {e}", severity="error")
        else:
            self.notify("Field is not overridden in config.yaml")

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss(None)


class ProviderConfigScreen(ModalScreen[None]):
    CSS = """
    ProviderConfigScreen {
        align: center middle;
    }

    #pc-dialog {
        width: 80;
        height: 34;
        border: round $success;
        background: $surface;
        padding: 1 2;
    }

    #pc-title {
        text-align: center;
        margin-bottom: 1;
    }

    #pc-table {
        height: 22;
    }

    #pc-actions {
        height: 3;
        width: 48;
        background: transparent;
    }

    #pc-actions Button {
        width: 16;
        min-width: 16;
    }
    """

    def __init__(self, provider_id: str, provider_name: str) -> None:
        super().__init__()
        self.provider_id = provider_id
        self.provider_name = provider_name
        self._schema: dict[str, Any] = {}
        self._secrets: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        with Vertical(id="pc-dialog"):
            yield Label(f"[b]Configure {self.provider_name}[/b]", id="pc-title")
            table: DataTable[Any] = DataTable(id="pc-table")
            table.add_columns("Field", "Value", "Type")
            yield table
            with Horizontal(id="pc-actions"):
                yield Button("Test", id="pc-test", variant="primary")
                yield Button("Close", id="pc-close")

    def on_mount(self) -> None:
        self._load()

    def _load(self) -> None:
        self._schema = load_provider_schema(self.provider_id)
        self._secrets = load_provider_secrets(self.provider_id)

        structured: dict[str, dict[str, dict[str, Any]]] = {}
        try:
            structured = load_structured()
        except Exception:
            pass

        table = self.query_one("#pc-table", DataTable)
        table.clear()

        config_fields = self._schema.get("config", {})
        for field_id in sorted(config_fields.keys()):
            spec = config_fields[field_id]
            label = spec.get("description") or field_label(self.provider_id, field_id)
            section_data = structured.get(self.provider_id.replace("-", "_"), {})
            value = section_data.get(field_id, {}).get("value") or ""
            ftype = spec.get("type", "string")
            if spec.get("required"):
                ftype += " *"
            table.add_row(label, value or "\u2014", ftype, key=f"config.{field_id}")

        secret_fields = self._schema.get("secrets", {})
        for field_id in sorted(secret_fields.keys()):
            spec = secret_fields[field_id]
            label = spec.get("description") or field_label(self.provider_id, field_id)
            value = self._secrets.get(field_id, "")
            display = "\u25cf\u25cf\u25cf\u25cf\u25cf\u25cf\u25cf\u25cf" if value else "\u2014"
            ftype = "secret"
            if spec.get("required"):
                ftype += " *"
            table.add_row(label, display, ftype, key=f"secret.{field_id}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        row_key = str(event.row_key.value)
        scope, field = row_key.split(".", 1)
        fields = self._schema.get(scope, {})
        spec = fields.get(field, {})
        label = spec.get("description") or field_label(self.provider_id, field)

        current = ""
        if scope == "secret":
            current = self._secrets.get(field, "")
        else:
            try:
                structured = load_structured()
                section_data = structured.get(self.provider_id.replace("-", "_"), {})
                current = section_data.get(field, {}).get("value") or ""
            except Exception:
                pass

        def handle_edit(result: str | None) -> None:
            if result is not None:
                try:
                    if scope == "secret":
                        save_provider_secret(self.provider_id, field, result)
                        self._secrets[field] = result
                    else:
                        save_value(self.provider_id.replace("-", "_"), field, result)
                    self._load()
                    self.notify(f"Saved {label}")
                except Exception as e:
                    self.notify(f"Save failed: {e}", severity="error")

        self.push_screen(EditFieldScreen(label, current), handle_edit)  # type: ignore[attr-defined]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "pc-close":
            self.dismiss(None)
        elif event.button.id == "pc-test":
            parent = self.app.query_one("#provider-pane", ProviderPane)
            parent.post_message(ProviderPane.TestConnectionRequested(self.provider_id))
            self.notify("Testing connection...")
            self.dismiss(None)

    def on_key(self, event: Any) -> None:
        if event.key == "escape":
            self.dismiss(None)
