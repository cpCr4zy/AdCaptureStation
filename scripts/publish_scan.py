#!/usr/bin/env python3
"""Pre-publication audit: nothing personal, secret or borrowed may leak into the repository.

    bash scripts/publish_scan.sh              # or: python3 scripts/publish_scan.py
    python3 scripts/publish_scan.py --no-git  # local dry run before `git init` (downgrades check 6)

Exit codes: 0 clean, 1 findings, 2 the scan could not complete (unreadable file, git failure, no
repository) — treat 2 as failure, never as "clean".

Rules this scanner follows, each learned from a false CLEAN:
  * every file is decoded and scanned regardless of extension; undecodable content and NUL bytes are
    reported, never skipped;
  * allowlists apply to the matched text, per check, and are anchored — a substring match on a whole
    line silences everything else on that line;
  * files that are gitignored (private/, *.generated) are reported as INFO and never fail the run;
  * IPv4 and IPv6 are both checked; allowed: the container NAT, loopback, unspecified, link-local and
    ULA;
  * the scanner scans itself; only its own pattern literals are exempt.
Limitation stated rather than hidden: detection is line-based with no entropy analysis, so a secret
split across lines or a bare base64 blob is not caught. `gitleaks` covers that — see
SECURITY-AND-PRIVACY.md, section 5.
"""
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = os.path.basename(os.path.abspath(__file__))
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
NO_GIT = "--no-git" in sys.argv
KEY_FILE = re.compile(r"(\.pem|\.key|\.p12|\.pfx|\.crt|\.cer|\.der|\.jks|\.keystore|\.sqlite3?|\.db"
                      r"|\.kdbx)$|^mitmproxy-ca|^adbkey|^id_rsa|^id_ed25519|^\.env", re.I)
PLACEHOLDER = re.compile(r"<[A-Za-z][\w-]*>")        # <redacted>, <ca-hash>, <guest-ip>, <user> …

CHECKS = [
    ("PEM / certificate blocks",
     re.compile(r"-----BEGIN [A-Z ]*(PRIVATE KEY|CERTIFICATE)-----"), []),
    ("credential-shaped strings",
     re.compile(r"(?i)[\w.-]*(api[_-]?key|api[_-]?secret|client[_-]?secret|access[_-]?token"
                r"|refresh[_-]?token|token|secret|passwd|password|pwd|dsn|credentials?)"
                r"[\"']?\s*[=:]\s*[\"']?\S+"
                r"|\bbearer\s+[A-Za-z0-9._-]{8,}"
                r"|\b(pass(word|wd)?|secret|token|api[_-]?key)\s+(?!-)(?=[^\s]*\d)"
                r"[A-Za-z0-9!@#$%^&*._-]{6,}"
                r"|\b[a-z][a-z0-9+.-]*://[^\s:@/]+:[^\s@/]+@[^\s/]+"),
     [re.compile(r"(?i)[=:]\s*[\"']?\[?REDACTED\]?[\"']?$"),
      re.compile(r"(?i)[=:]\s*[\"']?<[A-Za-z][\w-]*>[\"']?$"),
      re.compile(r"\$\{\{\s*(secrets|env|vars|github)\."),
      re.compile(r"(?i)NOPASSWD:\s*\S+"),
      re.compile(r"(?i)GITHUB_TOKEN")]),
    ("signed URL parameters",
     re.compile(r"(X-Amz-Signature|X-Goog-Signature|Signature=|Policy=|Key-Pair-Id=)"), []),
    ("device identifiers",
     re.compile(r"(android_id\s*[=:]?\s*[0-9a-f]{8,}|advertising_id\s*[=:]\s*[0-9a-f-]{8,}"
                r"|imei\s*[=:]\s*[0-9]{10,})"), []),
    ("device serial values",
     re.compile(r"(?i)(ro\.serialno\s*[=:]\s*[A-Za-z0-9]{6,}|serialno\s*[=:]\s*[A-Za-z0-9]{6,}"
                r"|adb\s+-s\s+(?!\$|<)([A-Za-z0-9]{6,}))"),
     [re.compile(r"emulator-\d+"), re.compile(r"\$\{?SERIAL")]),
    ("MAC addresses",
     re.compile(r"(?i)\b([0-9a-f]{2}:){5}[0-9a-f]{2}\b"), []),
    ("local domain names", re.compile(r"\b[A-Za-z0-9_-]+\.local\b"), []),
    ("hardcoded home paths",
     re.compile(r"(?i)(?<![$\w])/(home|Users)/[A-Za-z0-9][\w.-]*"
                r"|(?<![$\w])/root/"
                r"|[A-Za-z]:\\\\?Users\\\\?[^\\\s]+"),
     [re.compile(r"(?i)/(home|Users)/<"), re.compile(r"(?i)/(home|Users)/\$\{?[A-Za-z]")]),
    ("e-mail addresses",
     re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
     [re.compile(r"(?i)@example\.(com|org|net)$"), re.compile(r"(?i)@[^@\s]*\.invalid$"),
      re.compile(r"(?i)^noreply@[A-Za-z0-9.-]+$|@users\.noreply\.github\.com$")]),
]
IPV4 = re.compile(r"\b([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\b")
IPV4_OK = re.compile(r"^(192\.168\.240\.(1|0)$|127\.0\.0\.1$|0\.0\.0\.0$)")
IPV6 = re.compile(r"(?i)(?<![0-9a-f:])((?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}|(?:[0-9a-f]{1,4}:){1,7}:)(?![0-9a-f:])")
IPV6_OK = re.compile(r"(?i)^(::1?$|fe80:|fc[0-9a-f]{2}:|fd[0-9a-f]{2}:)")
# a four-part number is a version only in explicit version syntax, and only that number is skipped
VERSION_CTX = re.compile(r"(?i)(version|==|~=|>=|<=)\s*[=:]?\s*$")
# deliberate, documented exception: the connectivity ping in the device health check
KNOWN_ADDRESS_LINES = [re.compile(r"ping -c1 -W2 8\.8\.8\.8")]
# exact quads that are tool versions, not addresses (documented in docs/01 toolchain table)
KNOWN_VERSION_QUADS = {"5.1.0.95"}

fail = 0
info = []
GIT_SKIPPED = False


def git_toplevel():
    """The work tree that contains ROOT, or None. A repository rooted *above* the station (e.g. a
    stray `git init` in $HOME) must not count: its index, ignore rules and history are not the ones
    that will be pushed, and `git add -A` there would stage the whole home directory."""
    if not shutil.which("git"):
        return None
    res = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
                         capture_output=True, text=True)
    return os.path.realpath(res.stdout.strip()) if res.returncode == 0 else None


GIT_TOP = git_toplevel()
HAS_GIT = GIT_TOP is not None and GIT_TOP == os.path.realpath(ROOT)


def row(label, ok, detail=""):
    global fail
    print(f"{label:<46} {'ok' if ok else 'FAIL  ' + detail}")
    if not ok:
        fail = 1


def is_tracked(rel):
    """True when git already tracks the file — tracked wins over every ignore rule."""
    if not HAS_GIT:
        return False
    return subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=ROOT,
                          capture_output=True).returncode == 0


def is_local(rel):
    """True for files that are never published: ignored AND untracked (or private/, *.generated)."""
    if is_tracked(rel):
        return False
    if rel.startswith("private/") or rel.endswith(".generated"):
        return True
    if HAS_GIT:
        return subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT,
                              capture_output=True).returncode == 0
    return False


def walk():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


texts, binaries = [], []
for path in walk():
    rel = os.path.relpath(path, ROOT)
    entry = None
    try:
        size = os.path.getsize(path)
        if size > 4 * 1024 * 1024:
            entry = f"{rel} (too large: {size // 1024} KB)"
        else:
            with open(path, "rb") as fh:
                raw = fh.read()
            if b"\x00" in raw:
                entry = f"{rel} (binary content, {len(raw) // 1024} KB)"
            else:
                texts.append((rel, raw.decode("utf-8")))
    except (OSError, UnicodeDecodeError) as exc:
        entry = f"{rel} (unreadable: {type(exc).__name__})"
    if entry:
        (info if is_local(rel) else binaries).append(entry)

print("== 1. text patterns (every file, every extension; gitignored files reported separately)")
for label, rx, allows in CHECKS:
    hits = []
    for rel, text in texts:
        self_scan = os.path.basename(rel) == SELF
        for no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if self_scan and (stripped.startswith("#") or "re.compile(" in line
                              or stripped.startswith(('r"', "r'")) or 'r"' in line and "(?" in line):
                continue                                     # the scanner's own pattern literals
            if label.startswith("credential") and "{{\u0020secrets." in line.replace(" ", " ") and "${{" in line:
                if "${{" in line and ("secrets." in line or "env." in line or "vars." in line):
                    continue
            flagged = [m.group(0) for m in rx.finditer(line)
                       if not any(a.search(m.group(0)) for a in allows)]
            if not flagged:
                continue
            entry = f"{rel}:{no}: {stripped[:110]}  <- {', '.join(flagged[:3])}"
            (info if is_local(rel) else hits).append(entry)
    row(label, not hits, f"{len(hits)} line(s)")
    for h in hits[:8]:
        print("     " + h)

print("== 2. addresses outside the container NAT")
hits = []
for rel, text in texts:
    for no, line in enumerate(text.splitlines(), 1):
        allowed_spans = [m.span() for p in KNOWN_ADDRESS_LINES for m in p.finditer(line)]
        for m in IPV4.finditer(line):
            if any(a <= m.start() and m.end() <= b for a, b in allowed_spans):
                continue
            quad = m.group(0)
            if quad in KNOWN_VERSION_QUADS or IPV4_OK.match(quad) \
                    or VERSION_CTX.search(line[:m.start()]):
                continue
            (info if is_local(rel) else hits).append(f"{rel}:{no}: {quad}")
        for m in IPV6.finditer(line):
            if re.fullmatch(r"(\d{1,2}:){3}\d{1,2}", m.group(1)):
                continue                                       # hh:mm:ss:ff is not an address
            if any(a <= m.start() and m.end() <= b for a, b in allowed_spans):
                continue
            if not IPV6_OK.match(m.group(1)):
                (info if is_local(rel) else hits).append(f"{rel}:{no}: {m.group(1)} (IPv6)")
row("public IPv4 / IPv6 addresses", not hits, f"{len(hits)} line(s)")
for h in hits[:8]:
    print("     " + h)

print("== 3. files that must not exist")
keyhits = [rel for rel, _ in texts if KEY_FILE.search(os.path.basename(rel))]
keyhits += [b for b in binaries if KEY_FILE.search(os.path.basename(b.split(" (")[0]))]
row("key / cert / db / env files", not keyhits, f"{len(keyhits)} file(s)")
for h in keyhits[:8]:
    print("     " + h)
row("binary / unreadable files", not binaries, f"{len(binaries)} file(s)")
for h in binaries[:8]:
    print("     " + h)
big = [f"{rel} ({os.path.getsize(os.path.join(ROOT, rel)) // 1024} KB)"
       for rel, _ in texts if os.path.getsize(os.path.join(ROOT, rel)) > 200 * 1024]
row("files over 200 KB", not big, f"{len(big)} file(s)")
for h in big[:5]:
    print("     " + h)

print("== 4. sudoers rule carries a placeholder")
SUDOERS_RULE = re.compile(r"^\s*(?!#|%)([A-Za-z0-9_.-]+)\s+ALL\s*[=:]")
hits, template_ok = [], False
for rel, text in texts:
    for no, line in enumerate(text.splitlines(), 1):
        if rel.endswith("config/sudoers-waydroid-lxc.txt") and re.match(r"^\s*__USER__\s+ALL\s*=", line):
            template_ok = True
        m = SUDOERS_RULE.match(line)
        if m and m.group(1) != "__USER__":
            entry = f"{rel}:{no}: {line.strip()[:80]}"
            (info if is_local(rel) else hits).append(entry)
row("rule names a placeholder", not hits, f"{len(hits)} line(s)")
for h in hits[:5]:
    print("     " + h)
row("placeholder survives in the template", template_ok)

print("== 5. reviews/ holds only the summary")
reviews = os.path.join(ROOT, "reviews")
row("reviews/README.md present", os.path.isfile(os.path.join(reviews, "README.md")))
strays = [f for f in os.listdir(reviews) if f != "README.md"] if os.path.isdir(reviews) else []
row("reviews/ holds only README.md", not strays, ", ".join(strays[:5]))

print("== 6. repository state")
if HAS_GIT and not NO_GIT:
    def git(*args, strict=True):
        res = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        if strict and res.returncode > 1:
            print(f"     git {' '.join(args)} failed: {res.stderr.strip()[:120]}")
            sys.exit(2)
        return res

    row("private/ ignored", git("check-ignore", "-q", "private").returncode == 0)
    row("private/**/ ignored", git("check-ignore", "-q", "private/templates/x.png").returncode == 0)
    row("reviews/ published", git("check-ignore", "-q", "reviews/README.md").returncode != 0)
    blocked = ("private/", "captured/", "adcapture/", "playable/", "mitmconf/", "all/",
               "century/", "flows/")
    tracked = [f for f in git("ls-files").stdout.split() if f.startswith(blocked)]
    row("no rig paths tracked", not tracked, f"{len(tracked)} tracked")
    for h in tracked[:5]:
        print("     " + h)
    ignored_tracked = []
    for rel in git("ls-files").stdout.split():
        if git("check-ignore", "--no-index", "-q", rel, strict=False).returncode == 0:
            ignored_tracked.append(rel)
    row("no tracked file matches an ignore rule", not ignored_tracked, ", ".join(ignored_tracked[:3]))
    authors = sorted({a for a in git("log", "--format=%an <%ae>", strict=False).stdout.splitlines()
                      if a})
    bad_auth = [a for a in authors if "noreply" not in a and "example.com" not in a]
    row("commit author is public-safe", not bad_auth, ", ".join(bad_auth[:3]))
    # history may be empty: also check the identity the *next* commit would be written with
    ident = git("var", "GIT_AUTHOR_IDENT", strict=False)
    who = ident.stdout.rsplit(">", 1)[0] + ">" if ident.returncode == 0 else ""
    row("next commit identity is public-safe",
        ident.returncode == 0 and ("noreply" in who or "example.com" in who),
        f"'{who or 'unset'}' — set git config user.name / user.email (see SECURITY-AND-PRIVACY.md §5)")
    print(f"{'tracked files':<46} {len(git('ls-files').stdout.split())}")
elif NO_GIT:
    print(f"{'git repository':<46} checked out, git checks skipped on request (--no-git)")
    GIT_SKIPPED = True
elif GIT_TOP is not None:
    row("git repository rooted at the station", False,
        f"the enclosing repository starts at {GIT_TOP} — run 'git init' in this directory")
else:
    row("git repository", False, "absent — run 'git init', or pass --no-git for a local dry run")

if info:
    print(f"\n== local-only hits (gitignored, never published: {len(info)} line(s))")
    for h in info[:8]:
        print("     " + h)

print()
if fail:
    print("BLOCKED — see FAIL lines above")
elif GIT_SKIPPED:
    print("CLEAN for the working tree — git checks were skipped (--no-git)")
else:
    print("CLEAN — nothing blocking a public push")
sys.exit(1 if fail else 0)
