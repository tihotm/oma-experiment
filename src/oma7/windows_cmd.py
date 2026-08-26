from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence


def windows_cmd_executable() -> str:
    return str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe")


def join_windows_arguments(arguments: Sequence[str]) -> str:
    rendered: list[str] = []
    for argument in arguments:
        if any(character in argument for character in (' ', '"')):
            rendered.append('"' + argument.replace('"', '\\"') + '"')
        else:
            rendered.append(argument)
    return " ".join(rendered)


def build_windows_cmd_invocation(codex: str, arguments: Sequence[str]) -> list[str]:
    argument_list = join_windows_arguments(arguments)
    if argument_list:
        command_line = f'""{codex}" {argument_list}"'
    else:
        command_line = f'""{codex}""'
    return [windows_cmd_executable(), "/d", "/s", "/c", command_line]
