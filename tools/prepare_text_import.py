"""Convert the reviewed 74-line source layout without printing credential values.

This is a one-file conversion, not an automatic parser for arbitrary text.
Source and destination are supplied explicitly; neither is overwritten.
"""
import sys
from pathlib import Path

from app.core.models import Account, Field, Service, Snapshot
from app.services.exchange import read_exchange, write_exchange


def convert(path):
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    if len(lines) != 74:
        raise ValueError("Source layout changed; review required")
    state = Snapshot()
    covered = set()

    def add(service, heading, values, kind="api", comment_lines=()):
        s = next((s for s in state.services if s.name == service), None)
        if s is None:
            s = Service(str(len(state.services)), service)
            state.services.append(s)
        covered.update([heading, *values, *comment_lines])
        title = lines[heading - 1].strip()
        comments = [lines[i - 1] for i in comment_lines]
        a = Account(service_id=s.id, service=s.name, title=title, kind=kind, notes="\n".join(comments))
        if kind == "account":
            a.login = lines[values[0] - 1].strip()
            a.fields = [Field("Пароль", lines[values[1] - 1]), Field("Секрет 2FA", "")]
        elif kind == "api":
            a.fields = [Field("API-ключ", lines[values[0] - 1])]
        else:
            a.fields = [Field("Переменная профиля", lines[values[0] - 1], False)]
        state.accounts.append(a)

    add("Suno AI", 1, [2, 3], "account")
    for h, value in [(5, 6), (8, 9), (11, 12), (14, 15)]:
        add("Google", h, [value])
    add("ChatGPT", 17, [18, 19], "account")
    add("Deepgram", 21, [22])
    add("TimeWeb cloud", 27, [28], comment_lines=[26])
    for h, value in [(30, 31), (33, 34), (36, 37), (39, 40), (42, 43)]:
        add("Polza.ai", h, [value])
    add("B.AI", 45, [46])
    add("TimeWeb cloud", 51, [52])
    add("TimeWeb cloud", 55, [56], comment_lines=[54])
    add("TimeWeb cloud", 57, [58])
    add("Яндекс ОРД", 60, [61])
    add("Telegram", 63, [64])
    add("Claude Code", 66, [67], "legacy")
    add("OpenCode", 69, [70], "legacy")
    add("OpenRouter", 72, [73])
    # Two lines excluded explicitly by the owner.
    excluded = {48, 49}
    nonempty = {i for i, line in enumerate(lines, 1) if line.strip()}
    if covered | excluded != nonempty:
        raise ValueError("Unmapped source lines; review required")
    return state


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python -m tools.prepare_text_import SOURCE DESTINATION")
    try:
        state = convert(sys.argv[1])
        write_exchange(sys.argv[2], state)
        verified = read_exchange(sys.argv[2])
        if len(verified.accounts) != len(state.accounts):
            raise ValueError
    except Exception:
        raise SystemExit("Conversion failed; no credential values logged") from None
    counts = {kind: sum(a.kind == kind for a in state.accounts) for kind in ("api", "account", "legacy")}
    print(f"Converted: services={len(state.services)}, records={len(state.accounts)}, counts={counts}; source unchanged")


if __name__ == "__main__":
    main()
