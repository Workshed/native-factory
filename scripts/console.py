#!/usr/bin/env python3
"""The Native Factory console.

    python3 scripts/console.py            # then open http://127.0.0.1:8765

A single-user web front end over `supervise.sh`. Stdlib only, loopback only, no auth —
there is no second user and no second machine, and a credential guarding a loopback
socket is theatre. See docs/design-console.md.

It holds no state of its own. Everything rendered is read from `state.json`,
`runs.jsonl`, `targets/` and the filesystem, and every action shells out to
`supervise.sh`. That means the CLI and the console can be used interchangeably, and the
console being down never blocks anything.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "targets"
OUTPUT = ROOT / "output"
PORT = 8765
CANVAS = "http://localhost:8000"

STAGE_ICON = {"done": "✓", "current": "▶", "todo": "·"}


# ---------------------------------------------------------------- reading state


def target_names() -> list[str]:
    if not TARGETS.is_dir():
        return []
    return sorted(p.name for p in TARGETS.iterdir() if (p / "target.yaml").is_file())


def safe_target(name: str) -> str | None:
    """Only ever accept a name that is already a directory we own."""
    return name if name in target_names() else None


def cfg(target: str, key: str) -> str:
    path = TARGETS / target / "target.yaml"
    if not path.is_file():
        return ""
    for line in path.read_text().splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def state(target: str) -> dict:
    path = OUTPUT / target / "state.json"
    if not path.is_file():
        return {"target": target, "status": "new", "stage": "", "plan": [], "completed": []}
    try:
        return json.loads(path.read_text())
    except ValueError:
        return {"target": target, "status": "unreadable", "stage": "", "plan": [], "completed": []}


def runs(target: str, limit: int = 12) -> list[dict]:
    path = OUTPUT / target / "runs.jsonl"
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows[-limit:][::-1]


def git_log(target: str, limit: int = 8) -> list[str]:
    repo = OUTPUT / target
    if not (repo / ".git").is_dir():
        return []
    out = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline", f"-{limit}"],
        capture_output=True, text=True,
    )
    return out.stdout.splitlines()


def screenshots(target: str) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    for platform in ("ios", "android"):
        d = OUTPUT / target / "screenshots" / platform
        if d.is_dir():
            shots = sorted(d.glob("*.png"))
            if shots:
                found[platform] = shots
    return found


def review_doc(target: str) -> Path | None:
    """Whatever this target produced for a human to read at the gate."""
    for candidate in ("reference/journey.md", "reference/site.md"):
        p = OUTPUT / target / candidate
        if p.is_file():
            return p
    return None


def any_running() -> str | None:
    for name in target_names():
        if state(name).get("status") == "running":
            return name
    return None


# ---------------------------------------------------------------- actions


def supervise(target: str, *args: str) -> None:
    """Run supervise.sh detached, logging where the console can tail it."""
    log = OUTPUT / target / "console.log"
    log.parent.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        with log.open("a") as fh:
            fh.write(f"\n$ supervise.sh {target} {' '.join(args)}  [{datetime.now(timezone.utc):%H:%M:%S}]\n")
            fh.flush()
            subprocess.run(
                [str(ROOT / "scripts" / "supervise.sh"), target, *args],
                cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT,
            )

    threading.Thread(target=run, daemon=True).start()


def tail(target: str, lines: int = 40) -> str:
    log = OUTPUT / target / "console.log"
    if not log.is_file():
        return ""
    return "\n".join(log.read_text(errors="replace").splitlines()[-lines:])


def create_target(name: str, url: str) -> str | None:
    slug = re.sub(r"[^a-z0-9-]+", "-", name.strip().lower()).strip("-")
    if not slug:
        return None
    d = TARGETS / slug
    if d.exists():
        return slug
    d.mkdir(parents=True)
    (d / "target.yaml").write_text(f"name: {name.strip()}\nurl: {url.strip()}\nmax_routes: 10\n")
    (d / "brief.md").write_text(
        f"# Target: {name.strip()}\n\n"
        f"Source: `{url.strip()}`\n\n"
        "Reference material is in `reference/` — start with `reference/site.md`.\n\n"
        "## Scope\n\n"
        "_Describe what to build, and what to leave out._\n\n"
        "## Branding\n\n"
        "Do not reproduce the source site's identity: no company name, logo or brand\n"
        "colours. Use the platform's own default styling.\n"
    )
    return slug


def write_brief(target: str, text: str) -> str:
    """Write brief.md and return a unified diff of what changed."""
    path = TARGETS / target / "brief.md"
    old = path.read_text() if path.is_file() else ""
    new = text.replace("\r\n", "\n")
    if old == new:
        return ""
    import difflib

    path.write_text(new)
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile="brief.md (before)", tofile="brief.md (after)",
    ))


# ---------------------------------------------------------------- markdown


def markdown(text: str) -> str:
    """A deliberately small subset: headings, tables, lists, code, quotes, emphasis.

    Enough to make journey.md readable at the gate, which is the only reason the console
    is a web page rather than a terminal. Not a markdown implementation.
    """
    def inline(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        return s

    out: list[str] = []
    in_code = in_list = in_table = False
    for line in text.splitlines():
        if line.startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(line))
            continue

        if line.startswith("|") and line.count("|") >= 2:
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False

        if m := re.match(r"^(#{1,4})\s+(.*)", line):
            out.append(f"<h{len(m[1])}>{inline(m[2])}</h{len(m[1])}>")
        elif m := re.match(r"^\s*[-*]\s+(.*)", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(m[1])}</li>")
        elif line.startswith(">"):
            out.append(f"<blockquote>{inline(line.lstrip('> '))}</blockquote>")
        elif not line.strip():
            if in_list:
                out.append("</ul>")
                in_list = False
        else:
            out.append(f"<p>{inline(line)}</p>")

    for open_tag, close in ((in_list, "</ul>"), (in_table, "</table>"), (in_code, "</pre>")):
        if open_tag:
            out.append(close)
    return "\n".join(out)


# ---------------------------------------------------------------- html

CSS = """
:root { color-scheme: light dark; --edge:#8883; --dim:#8889; }
* { box-sizing: border-box; }
body { font: 15px/1.55 ui-sans-serif, -apple-system, system-ui, sans-serif;
       margin: 0 auto; padding: 24px 20px 80px; max-width: 900px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 17px; margin: 32px 0 10px; }
h3 { font-size: 15px; margin: 20px 0 6px; }
a { color: inherit; }
code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
pre { background: #8881; padding: 10px 12px; border-radius: 6px; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; }
td, th { border-bottom: 1px solid var(--edge); padding: 6px 8px; text-align: left;
         vertical-align: top; font-size: 14px; }
blockquote { border-left: 3px solid var(--edge); margin: 10px 0; padding: 2px 0 2px 12px;
             color: var(--dim); }
.muted { color: var(--dim); }
.card { border: 1px solid var(--edge); border-radius: 10px; padding: 14px 16px; margin: 12px 0; }
.row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.badge { font-size: 12px; padding: 2px 9px; border-radius: 99px; border: 1px solid var(--edge); }
.running { background: #f5a62333; } .done { background: #2ea04333; }
.awaiting-approval { background: #d29d0033; } .failed, .rejected { background: #cf222e33; }
.new { background: #8881; }
button, .btn { font: inherit; padding: 7px 14px; border-radius: 7px; cursor: pointer;
               border: 1px solid var(--edge); background: #8881; text-decoration: none;
               display: inline-block; }
button.primary { background: #2ea043; color: #fff; border-color: transparent; }
button.danger  { background: #cf222e; color: #fff; border-color: transparent; }
input, textarea { font: inherit; width: 100%; padding: 8px 10px; border-radius: 7px;
                  border: 1px solid var(--edge); background: transparent; color: inherit; }
textarea { font-family: ui-monospace, Menlo, monospace; font-size: 13px; min-height: 340px; }
.shots { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; }
.shots img { width: 100%; border: 1px solid var(--edge); border-radius: 8px; }
.stage { display: inline-block; margin-right: 14px; }
.stage .i { display: inline-block; width: 14px; }
.review { max-height: 520px; overflow-y: auto; border: 1px solid var(--edge);
          border-radius: 10px; padding: 4px 16px; }
"""


def page(title: str, body: str, refresh: bool = False) -> bytes:
    meta = '<meta http-equiv="refresh" content="5">' if refresh else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>{meta}<style>{CSS}</style></head><body>
<div class="row" style="justify-content:space-between;margin-bottom:18px">
  <a href="/" style="text-decoration:none"><strong>Native Factory</strong></a>
  <a class="muted" href="{CANVAS}" target="_blank">Agent Canvas ↗</a>
</div>
{body}</body></html>""".encode()


def badge(status: str) -> str:
    return f'<span class="badge {html.escape(status)}">{html.escape(status)}</span>'


def stage_strip(s: dict) -> str:
    done, current = set(s.get("completed", [])), s.get("stage")
    bits = []
    for stage in s.get("plan", []):
        kind = "done" if stage in done else ("current" if stage == current else "todo")
        colour = "" if kind == "todo" else ' style="font-weight:600"'
        bits.append(f'<span class="stage"{colour}><span class="i">{STAGE_ICON[kind]}</span>{html.escape(stage)}</span>')
    return "".join(bits) or '<span class="muted">no plan yet</span>'


def dashboard() -> bytes:
    busy = any_running()
    rows = []
    for name in target_names():
        s = state(name)
        rows.append(
            f'<tr><td><a href="/t/{name}"><strong>{html.escape(name)}</strong></a><br>'
            f'<span class="muted">{html.escape(cfg(name, "url")[:70])}</span></td>'
            f"<td>{badge(s.get('status','new'))}</td>"
            f"<td class='muted'>{html.escape(s.get('stage') or '')}</td></tr>"
        )
    table = f"<table>{''.join(rows)}</table>" if rows else '<p class="muted">No targets yet.</p>'
    note = f'<p class="muted">{html.escape(busy)} is running; one job at a time.</p>' if busy else ""

    return page("Native Factory", f"""
<h1>Targets</h1>{note}{table}
<h2>New target</h2>
<form method="post" action="/targets" class="card">
  <p><label>Name<br><input name="name" placeholder="Acme checkout" required></label></p>
  <p><label>Running site<br><input name="url" placeholder="https://… or http://localhost:3000" required></label></p>
  <p class="muted">Creates <code>targets/&lt;slug&gt;/</code> with a starter brief to edit.</p>
  <button class="primary" type="submit">Create</button>
</form>""")


def target_page(name: str, flash: str = "") -> bytes:
    s = state(name)
    status = s.get("status", "new")
    busy = any_running()
    can_run = status not in ("running",) and (busy is None or busy == name)

    actions = []
    if status == "awaiting-approval":
        actions.append('<form method="post" action="/t/%s/approve" style="display:inline">'
                       '<button class="primary">Approve</button></form>' % name)
    elif can_run:
        label = "Run" if status in ("new", "done") else "Resume"
        actions.append('<form method="post" action="/t/%s/run" style="display:inline">'
                       '<button class="primary">%s</button></form>' % (name, label))
    if status not in ("new",):
        actions.append('<form method="post" action="/t/%s/reset" style="display:inline">'
                       '<button>Reset</button></form>' % name)

    body = [
        f"<h1>{html.escape(name)}</h1>",
        f'<p class="muted">{html.escape(cfg(name, "url"))}</p>',
        f'<div class="card"><div class="row" style="justify-content:space-between">'
        f"<div>{badge(status)}</div><div class='row'>{''.join(actions)}</div></div>"
        f'<p style="margin:12px 0 0">{stage_strip(s)}</p>'
        + (f'<p class="muted" style="margin:8px 0 0">{html.escape(s["message"])}</p>' if s.get("message") else "")
        + "</div>",
    ]
    if flash:
        body.append(f'<div class="card">{flash}</div>')

    # The gate: the reason this is a web page at all.
    if status == "awaiting-approval":
        doc = review_doc(name)
        body.append("<h2>Review before building</h2>")
        if doc:
            body.append(f'<div class="review">{markdown(doc.read_text(errors="replace"))}</div>')
        shots = sorted((OUTPUT / name / "reference").glob("**/*.png"))[:12]
        if shots:
            body.append('<div class="shots" style="margin-top:14px">' + "".join(
                f'<a href="/files/{name}/{s.relative_to(OUTPUT / name)}" target="_blank">'
                f'<img src="/files/{name}/{s.relative_to(OUTPUT / name)}"></a>' for s in shots
            ) + "</div>")
        body.append(f"""
<div class="card"><div class="row">
  <form method="post" action="/t/{name}/approve"><button class="primary">Approve and build</button></form>
</div>
<form method="post" action="/t/{name}/reject" style="margin-top:12px">
  <p><label>Reject, with a reason<br><input name="reason" required
     placeholder="explored the wrong branch — wanted the checkout flow"></label></p>
  <button class="danger">Reject</button>
  <span class="muted">&nbsp;Stops and waits for you to edit the brief. Nothing is re-run.</span>
</form></div>""")

    shots = screenshots(name)
    if shots:
        body.append("<h2>The apps</h2>")
        for platform, files in shots.items():
            body.append(f"<h3>{platform}</h3><div class='shots'>" + "".join(
                f'<a href="/files/{name}/{f.relative_to(OUTPUT / name)}" target="_blank">'
                f'<img src="/files/{name}/{f.relative_to(OUTPUT / name)}"></a>' for f in files
            ) + "</div>")

    log = git_log(name)
    if log:
        body.append("<h2>Code</h2><div class='card'>"
                    f"<p class='muted'>Its own git repository — clone or browse it:</p>"
                    f"<pre>git -C output/{html.escape(name)} log</pre>"
                    "<pre>" + html.escape("\n".join(log)) + "</pre></div>")

    body.append('<h2>Brief</h2><form method="post" action="/t/%s/brief" class="card">' % name)
    brief = TARGETS / name / "brief.md"
    body.append(f'<textarea name="text">{html.escape(brief.read_text() if brief.is_file() else "")}</textarea>')
    body.append('<p class="muted">Written to <code>targets/%s/brief.md</code>, which is what is '
                'versioned. The diff is shown after saving.</p>'
                '<button>Save brief</button></form>' % name)

    history = runs(name)
    if history:
        body.append("<h2>History</h2><table>" + "".join(
            f"<tr><td>{html.escape(r['stage'])}</td><td>{html.escape(r['outcome'])}</td>"
            f"<td class='muted'>{html.escape((r.get('conversation') or '')[:8])}</td>"
            f"<td class='muted'>{html.escape(r['ts'][:19])}</td></tr>" for r in history
        ) + "</table>")

    if t := tail(name):
        body.append("<h2>Log</h2><pre>" + html.escape(t) + "</pre>")

    return page(name, "\n".join(body), refresh=(status == "running"))


# ---------------------------------------------------------------- http


class Handler(BaseHTTPRequestHandler):
    server_version = "NativeFactoryConsole/1"

    def log_message(self, fmt: str, *args) -> None:  # quieter than the default
        pass

    def send(self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, where: str) -> None:
        self.send_response(303)
        self.send_header("Location", where)
        self.end_headers()

    def form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    # -- GET ---------------------------------------------------------------

    def do_GET(self) -> None:
        path = unquote(urlparse(self.path).path)

        if path == "/":
            return self.send(dashboard())

        if path == "/api/state":
            payload = {n: state(n) for n in target_names()}
            return self.send(json.dumps(payload, indent=2).encode(), ctype="application/json")

        if m := re.fullmatch(r"/t/([^/]+)", path):
            name = safe_target(m[1])
            return self.send(target_page(name)) if name else self.send(b"unknown target", 404, "text/plain")

        # Artefacts. Confined to output/<target>/ and resolved before serving, so a
        # crafted path cannot climb out of the directory it names.
        if m := re.fullmatch(r"/files/([^/]+)/(.+)", path):
            name = safe_target(m[1])
            if not name:
                return self.send(b"unknown target", 404, "text/plain")
            base = (OUTPUT / name).resolve()
            target_file = (base / m[2]).resolve()
            if not target_file.is_file() or base not in target_file.parents:
                return self.send(b"not found", 404, "text/plain")
            ctype = {
                ".png": "image/png", ".jpg": "image/jpeg", ".json": "application/json",
                ".md": "text/plain; charset=utf-8", ".yaml": "text/plain; charset=utf-8",
            }.get(target_file.suffix, "application/octet-stream")
            return self.send(target_file.read_bytes(), ctype=ctype)

        self.send(b"not found", 404, "text/plain")

    # -- POST --------------------------------------------------------------

    def do_POST(self) -> None:
        path = unquote(urlparse(self.path).path)

        if path == "/targets":
            data = self.form()
            slug = create_target(data.get("name", ""), data.get("url", ""))
            return self.redirect(f"/t/{slug}" if slug else "/")

        m = re.fullmatch(r"/t/([^/]+)/(run|approve|reject|reset|brief)", path)
        if not m:
            return self.send(b"not found", 404, "text/plain")
        name, action = safe_target(m[1]), m[2]
        if not name:
            return self.send(b"unknown target", 404, "text/plain")

        data = self.form()

        if action == "run":
            if (busy := any_running()) and busy != name:
                return self.send(page(name, f"<p>{html.escape(busy)} is already running. "
                                            "One job at a time — the VM ceiling is two guests "
                                            f'and they are shared.</p><p><a href="/t/{name}">Back</a></p>'))
            supervise(name)
        elif action == "approve":
            subprocess.run([str(ROOT / "scripts" / "supervise.sh"), name, "approve"], cwd=ROOT,
                           capture_output=True)
            supervise(name)          # release the gate, then carry straight on
        elif action == "reject":
            subprocess.run([str(ROOT / "scripts" / "supervise.sh"), name, "reject",
                            data.get("reason", "rejected")], cwd=ROOT, capture_output=True)
        elif action == "reset":
            subprocess.run([str(ROOT / "scripts" / "supervise.sh"), name, "reset"], cwd=ROOT,
                           capture_output=True)
        elif action == "brief":
            diff = write_brief(name, data.get("text", ""))
            flash = (f"<p><strong>Brief updated.</strong></p><pre>{html.escape(diff)}</pre>"
                     if diff else '<p class="muted">No change.</p>')
            return self.send(target_page(name, flash))

        self.redirect(f"/t/{name}")


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"console on http://127.0.0.1:{PORT}  (loopback only; ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
