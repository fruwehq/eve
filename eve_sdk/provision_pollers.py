"""Probe-script builders + status classifier for the wait-for-provision poller.

The remote status / log probes are constructed here as plain strings (with the
embedded bash / PowerShell snippets preserved byte-exact from the original
``scripts/wait-for-provision`` bash implementation) so they can be parity-
checked without a live SSH connection.

``classify_status_json`` mirrors the jq schema validation + DONE / FAILED /
RUNNING classification the bash ``parse_status_json`` performed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

# ============================ probe-script builders ======================== #
# Each builder returns the exact remote command string the bash poller sent
# through ``instance-ssh``. Literal ``\t`` / ``\n`` inside remote ``printf``
# single-quotes and the ``\./`` awk regex are preserved as backslash-sequences
# for the remote shell to interpret; paths use single backslashes for PowerShell.

# ---- status-file probe ---------------------------------------------------- #
_UBUNTU_STATUS_PROBE = """\
sf="$HOME/provision/state/provision-status.json"
if [ ! -f "$sf" ]; then
  printf 'STATUS_FILE\\tABSENT\\n'
  exit 0
fi
if ! cat "$sf" | jq empty 2>/dev/null; then
  printf 'STATUS_FILE\\tMALFORMED\\n'
  exit 0
fi
cat "$sf"
"""

_WINDOWS_STATUS_PROBE = """\
$sf = "C:\\Users\\Administrator\\provision\\state\\provision-status.json"
if (-not (Test-Path $sf)) {
  "STATUS_FILE`tABSENT"
  exit 0
}
try {
  $null = Get-Content $sf | ConvertFrom-Json
} catch {
  "STATUS_FILE`tMALFORMED"
  exit 0
}
Get-Content $sf
"""

# ---- log probe (body after the offset header line) ----------------------- #
_UBUNTU_LOG_PROBE_BODY = """\
log="$HOME/provision/logs/provision.log"
if [ ! -f "$log" ]; then
  printf 'STATE\\tMISSING\\nLINES\\t0\\nLAST\\t\\n__EVE_LOG_BEGIN__\\n'
  exit 0
fi
line_count=$(wc -l < "$log" | tr -d ' ')
last_step=$(awk "/Running step / {n=NR} END {print n+0}" "$log")
last_done=$(awk "/Provisioning complete\\./ {n=NR} END {print n+0}" "$log")
last_error=$(awk "/ERROR: / {n=NR} END {print n+0}" "$log")
if [ "$last_done" -gt "$last_step" ] && [ "$last_done" -gt 0 ]; then
  state=DONE
elif systemctl is-failed --quiet ephemeral-provision.service 2>/dev/null; then
  state=FAILED
elif [ "$last_error" -gt "$last_step" ] && [ "$last_error" -gt "$last_done" ]; then
  state=FAILED
else
  state=RUNNING
fi
last_line=$(grep -E "Running step |ERROR: " "$log" | tail -n 1 || true)
printf 'STATE\\t%s\\n' "$state"
printf 'LINES\\t%s\\n' "$line_count"
printf 'LAST\\t%s\\n' "$last_line"
printf '__EVE_LOG_BEGIN__\\n'
if [ "$line_count" -gt "$offset" ]; then
  start=$((offset + 1))
  sed -n "${start},${line_count}p" "$log"
fi
"""

_WINDOWS_LOG_PROBE_BODY = """\
$tab = [char]9
$log = "C:\\Users\\Administrator\\provision\\logs\\provision.log"
if (-not (Test-Path $log)) {
  "STATE${tab}MISSING"
  "LINES${tab}0"
  "LAST${tab}"
  "__EVE_LOG_BEGIN__"
  exit 0
}
$lines = @(Get-Content $log)
$lineCount = $lines.Count
$lastStep = -1
$lastDone = -1
$lastError = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
  if ($lines[$i] -match "Running step ") { $lastStep = $i }
  if ($lines[$i] -match "Provisioning complete\\.") { $lastDone = $i }
  if ($lines[$i] -match "ERROR: ") { $lastError = $i }
}
if ($lastDone -gt $lastStep -and $lastDone -ge 0) {
  $state = "DONE"
} elseif ($lastError -gt $lastStep -and $lastError -gt $lastDone) {
  $state = "FAILED"
} else {
  $state = "RUNNING"
}
$last = $lines | Select-String -Pattern "Running step|ERROR: " | Select-Object -Last 1
if ($last) { $lastLine = $last.Line } else { $lastLine = "" }
"STATE${tab}$state"
"LINES${tab}$lineCount"
"LAST${tab}$lastLine"
"__EVE_LOG_BEGIN__"
if ($lineCount -gt $offset) {
  $start = [Math]::Max($offset, 0)
  for ($i = $start; $i -lt $lineCount; $i++) { $lines[$i] }
}
"""


def build_status_probe(os_family: str) -> str:
    """Return the remote status-file probe script for ``os_family``.

    Mirrors the bash ``build_status_probe`` ``case``: a fixed bash (ubuntu) or
    PowerShell (windows) snippet. Raises ``ValueError`` for an unknown family
    (the bash ``case`` default echoes to stderr and exits 2).
    """
    if os_family == "ubuntu":
        return _UBUNTU_STATUS_PROBE
    if os_family == "windows":
        return _WINDOWS_STATUS_PROBE
    raise ValueError(f"wait-for-provision: unknown os_family: {os_family}")


def build_log_probe(os_family: str, offset: int) -> str:
    """Return the remote log probe script for ``os_family`` seeded with ``offset``.

    Mirrors the bash ``build_probe``: ubuntu interpolates ``offset=<n>`` as the
    first line (unquoted heredoc), windows interpolates ``$offset = <n>`` (via
    ``printf '%s = %s\\n' "\\$offset" "$offset"``) then a literal PowerShell body.
    Raises ``ValueError`` for an unknown family.
    """
    if os_family == "ubuntu":
        return f"offset={offset}\n" + _UBUNTU_LOG_PROBE_BODY
    if os_family == "windows":
        return f"$offset = {offset}\n" + _WINDOWS_LOG_PROBE_BODY
    raise ValueError(f"wait-for-provision: unknown os_family: {os_family}")


# ============================ log-line cleanup ============================= #
# Mirrors ``clean_step() { sed -E -e 's/^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]+ //'
# -e 's/^Running step //'; }`` — strip a leading ``YYYY-MM-DD HH:MM:SS `` stamp
# then a leading ``Running step `` prefix.
_TIMESTAMP_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]+ ")


def clean_step(line: str) -> str:
    """Strip the leading timestamp and ``Running step `` prefix from a log line."""
    cleaned = _TIMESTAMP_RE.sub("", line, count=1)
    if cleaned.startswith("Running step "):
        cleaned = cleaned[len("Running step "):]
    return cleaned


# ============================ probe-result parsing ======================== #
@dataclass
class ProbeResult:
    """Parsed fields from a log-probe response (the STATE/LINES/LAST header)."""

    state: str
    line_count: int | None
    step_line: str
    new_log: str


def parse_probe_result(result: str) -> ProbeResult:
    """Parse a log-probe response into state / line_count / step_line / new_log.

    Mirrors three independent ``awk -F '\\t' '$1 == "..." {...; exit}'`` passes
    (first match per field) and the ``sed -n '/^__EVE_LOG_BEGIN__$/,$p' | sed
    '1d'`` new-log slice. ``line_count`` is None when the LINES field is absent
    or non-integer.
    """
    state = ""
    state_found = False
    line_count: int | None = None
    lines_found = False
    step_line = ""
    step_found = False
    lines = result.split("\n")
    for line in lines:
        first, sep, rest = line.partition("\t")
        # awk ``$1 == "STATE"`` matches with or without a trailing tab.
        if not state_found and first == "STATE":
            state = rest
            state_found = True
        if not lines_found and first == "LINES":
            try:
                line_count = int(rest)
            except ValueError:
                line_count = None
            lines_found = True
        if not step_found and first == "LAST":
            # awk substr($0, index($0,"\t")+1): everything after the first tab;
            # when there is no tab the whole line is returned.
            step_line = rest if sep else line
            step_found = True
    new_log = _extract_new_log(lines)
    return ProbeResult(state=state, line_count=line_count, step_line=step_line, new_log=new_log)


def _extract_new_log(lines: list[str]) -> str:
    """Return the log slice after the ``__EVE_LOG_BEGIN__`` marker line.

    Mirrors ``sed -n '/^__EVE_LOG_BEGIN__$/,$p' | sed '1d'`` followed by the
    trailing-newline stripping of the enclosing ``$(...)``.
    """
    for idx, line in enumerate(lines):
        if line == "__EVE_LOG_BEGIN__":
            return "\n".join(lines[idx + 1:]).rstrip("\n")
    return ""


# ============================ status-json classification ================== #
def _jq_type(value: object) -> str:
    """Return the jq ``type`` name for a JSON-decoded Python value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _is_str_or_null(value: object) -> bool:
    return _jq_type(value) in ("string", "null")


def _valid_step(step: object) -> bool:
    """Mirror the jq per-step schema guard."""
    if not isinstance(step, dict):
        return False
    name = step.get("step")
    if not (isinstance(name, str) and len(name) > 0):
        return False
    if step.get("phase") not in ("pending", "running", "succeeded", "failed", "skipped"):
        return False
    for key in ("started_at", "ended_at", "exit_code"):
        if key not in step:
            return False
    if not _is_str_or_null(step.get("started_at")):
        return False
    if not _is_str_or_null(step.get("ended_at")):
        return False
    exit_code = step.get("exit_code")
    if _jq_type(exit_code) not in ("number", "null"):
        return False
    # jq ``. == floor`` — reject non-integer floats; ints always pass.
    return not (isinstance(exit_code, float) and not exit_code.is_integer())


def _valid_status_schema(data: object) -> bool:
    """Mirror the jq ``-e`` schema validation in ``parse_status_json``."""
    if not isinstance(data, dict):
        return False
    if data.get("api_version") != 1 or isinstance(data.get("api_version"), bool):
        return False
    if data.get("os_family") not in ("ubuntu", "windows"):
        return False
    if "started_at" not in data or not _is_str_or_null(data.get("started_at")):
        return False
    if data.get("status") not in ("running", "done", "failed"):
        return False
    steps = data.get("steps")
    if not isinstance(steps, list):
        return False
    return all(_valid_step(step) for step in steps)


def classify_status_json(raw: str) -> str:
    """Classify a status-probe response into a tab-separated result line.

    Mirrors the bash ``parse_status_json``. Returns one of:

    - ``NOT_PRESENT``     — remote reported ``STATUS_FILE\\tABSENT``
    - ``MALFORMED``       — remote reported MALFORMED, or JSON / schema invalid
    - ``DONE\\t<s>\\t<d>/<n>``    — overall ``done``
    - ``FAILED\\t<s>\\t<d>/<n>``  — overall ``failed``
    - ``RUNNING\\t<s>\\t<d>/<n>`` — overall ``running``
    """
    file_status = ""
    for line in raw.split("\n"):
        if line.startswith("STATUS_FILE"):
            parts = line.split("\t")
            file_status = parts[1] if len(parts) >= 2 else ""
            break
    if file_status == "ABSENT":
        return "NOT_PRESENT"
    if file_status == "MALFORMED":
        return "MALFORMED"
    json_str = (
        "\n".join(line for line in raw.split("\n") if not line.startswith("STATUS_FILE"))
        if file_status
        else raw
    )
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError):
        return "MALFORMED"
    if not _valid_status_schema(data):
        return "MALFORMED"
    overall = data["status"]
    steps = data["steps"]
    last_running = ""
    for step in steps:
        if step.get("phase") in ("running", "succeeded", "failed"):
            last_running = step.get("step", "") or ""
    total_done = sum(1 for step in steps if step.get("phase") == "succeeded")
    total_steps = len(steps)
    progress = f"{total_done}/{total_steps}"
    if overall == "done":
        return f"DONE\t{last_running}\t{progress}"
    if overall == "failed":
        failed_step = ""
        for step in steps:
            if step.get("phase") == "failed":
                failed_step = step.get("step", "") or ""
        return f"FAILED\t{failed_step}\t{progress}"
    return f"RUNNING\t{last_running}\t{progress}"
