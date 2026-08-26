@echo off
set "OMA7_EPHEMERAL_CODEX_HOME=C:\Users\IGORB~1\AppData\Local\Temp\oma7-ephemeral-codex-home"
set "CODEX_HOME=%OMA7_EPHEMERAL_CODEX_HOME%"
python scripts\oma7-release-candidate-run.py --json
