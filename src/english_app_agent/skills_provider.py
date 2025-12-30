from __future__ import annotations

import dataclasses
import os
import re
import math
import subprocess
import time
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Protocol, Union


# =============================================================================
# Types
# =============================================================================

@dataclasses.dataclass(frozen=True)
class SkillMeta:
    """
    Metadata loaded at startup (progressive disclosure level 1).

    Mirrors the Agent Skills spec frontmatter fields:
      - name (required)
      - description (required)
      - license (optional)
      - compatibility (optional)
      - metadata (optional mapping)
      - allowed-tools (optional, experimental; space-delimited list)

    For filesystem-based skills, root_dir/entry_path are populated.
    For tool-based/API skills, location is populated (tool://... or https://...),
    and root_dir/entry_path may be None.
    """
    name: str
    description: str

    # Filesystem-based
    root_dir: Optional[Path] = None
    entry_path: Optional[Path] = None

    # Tool-based
    location: Optional[str] = None

    # Optional fields
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: Optional[Dict[str, str]] = None
    allowed_tools: Optional[List[str]] = None  # normalized from allowed-tools


@dataclasses.dataclass(frozen=True)
class Skill:
    meta: SkillMeta
    body_markdown: str  # SKILL.md content without frontmatter


@dataclasses.dataclass
class Selection:
    skill_name: str
    score: float
    reason: str = ""


@dataclasses.dataclass
class ToolPolicy:
    """Optional tool allowlist that can change when a skill is active."""
    allowed_tools: Optional[List[str]] = None

    def is_allowed(self, tool_name: str) -> bool:
        if self.allowed_tools is None:
            return True
        return tool_name in self.allowed_tools


# =============================================================================
# Parsing + validation (filesystem-based)
# =============================================================================

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.S)

# Spec-ish name constraints: 1-64, lowercase letters/numbers/hyphen, no leading/trailing '-', no consecutive '--'
_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class SkillSpecError(ValueError):
    pass


def _yaml_safe_load(yaml_text: str) -> Dict[str, Any]:
    """
    Prefer PyYAML if present, fallback to a minimal parser (supports only scalars + lists).
    """
    try:
        import yaml  # type: ignore
        obj = yaml.safe_load(yaml_text) or {}
        if not isinstance(obj, dict):
            raise SkillSpecError("Frontmatter must be a YAML mapping (dict).")
        return obj
    except ModuleNotFoundError:
        data: Dict[str, Any] = {}
        lines = [ln.rstrip("\n") for ln in yaml_text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(r"^\s", line):
                i += 1
                continue

            if ":" not in line:
                i += 1
                continue

            key, rest = line.split(":", 1)
            key = key.strip()
            rest = rest.strip()

            if rest:
                v = rest.strip().strip('"').strip("'")
                data[key] = v
                i += 1
                continue

            items: List[str] = []
            i += 1
            while i < len(lines) and re.match(r"^\s*-\s+", lines[i]):
                item = re.sub(r"^\s*-\s+", "", lines[i]).strip()
                items.append(item.strip('"').strip("'"))
                i += 1
            data[key] = items

        return data


def parse_skill_md(text: str) -> Tuple[Dict[str, Any], str]:
    """
    Returns (frontmatter_dict, body_markdown).

    Per spec, SKILL.md must contain YAML frontmatter followed by Markdown body.
    If frontmatter is missing, this function raises SkillSpecError so callers can skip invalid skills.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SkillSpecError("SKILL.md is missing required YAML frontmatter (--- ... ---).")
    fm_raw, body = m.group(1), m.group(2)
    fm = _yaml_safe_load(fm_raw)
    return fm, body


def _normalize_allowed_tools(fm: Dict[str, Any]) -> Optional[List[str]]:
    """
    Spec: 'allowed-tools' is a space-delimited string (experimental).
    We also accept a YAML list for compatibility with earlier drafts/implementations.
    """
    val = None
    if "allowed-tools" in fm:
        val = fm.get("allowed-tools")
    elif "allowed_tools" in fm:
        val = fm.get("allowed_tools")

    if val is None:
        return None

    if isinstance(val, str):
        toks = [t for t in val.split() if t]
        return toks or None

    if isinstance(val, list):
        toks = [str(x).strip() for x in val if str(x).strip()]
        return toks or None

    return None


def _normalize_metadata(fm: Dict[str, Any]) -> Optional[Dict[str, str]]:
    md = fm.get("metadata")
    if md is None:
        return None
    if not isinstance(md, dict):
        return {"value": str(md)}
    out: Dict[str, str] = {}
    for k, v in md.items():
        out[str(k)] = str(v)
    return out or None


def validate_frontmatter(fm: Dict[str, Any], *, dir_name: str) -> None:
    name = str(fm.get("name") or "").strip()
    desc = str(fm.get("description") or "").strip()

    if not name:
        raise SkillSpecError("Missing required frontmatter field: name")
    if not desc:
        raise SkillSpecError("Missing required frontmatter field: description")

    if not (1 <= len(name) <= 64):
        raise SkillSpecError("Field 'name' must be 1-64 characters.")
    if not _NAME_RE.match(name):
        raise SkillSpecError(
            "Field 'name' must be lowercase letters/numbers with hyphens (kebab-case), "
            "no leading/trailing hyphen, and no consecutive hyphens."
        )
    if name != dir_name:
        raise SkillSpecError(f"Field 'name' must match the parent directory name ('{dir_name}').")

    if not (1 <= len(desc) <= 1024):
        raise SkillSpecError("Field 'description' must be 1-1024 characters (non-empty).")

    compat = fm.get("compatibility")
    if compat is not None:
        compat_s = str(compat).strip()
        if not (1 <= len(compat_s) <= 500):
            raise SkillSpecError("Field 'compatibility' must be 1-500 characters if provided.")


# =============================================================================
# Provider Abstractions (NEW)
# =============================================================================

class SkillProvider(Protocol):
    """
    Progressive disclosure provider:

    - refresh(): discover skills + preload metadata only
    - list_metas(): return metadata for selection
    - load_skill(name): load full SKILL.md body for activation
    - list_errors(): optional diagnostics
    """
    def refresh(self) -> None: ...
    def list_metas(self) -> List[SkillMeta]: ...
    def load_skill(self, name: str) -> Optional[Skill]: ...
    def list_errors(self) -> Dict[str, str]: ...


class ExecutionBackend(Protocol):
    """Tool-based or filesystem-based execution substrate."""
    def read_file(self, skill: SkillMeta, rel_path: str, max_bytes: int = 200_000) -> str: ...
    def run_script(self, skill: SkillMeta, command: List[str], timeout_s: Optional[int] = None,
                   env: Optional[Dict[str, str]] = None) -> Dict[str, Any]: ...


# =============================================================================
# Filesystem Provider (existing functionality, wrapped)
# =============================================================================

class SkillRegistry:
    """
    Filesystem discovery + metadata preload.
    (Kept mostly identical to your previous implementation.)
    """
    def __init__(self, skills_root: Path):
        self.skills_root = skills_root
        self._metas: Dict[str, SkillMeta] = {}
        self._errors: Dict[Path, str] = {}

    def refresh(self) -> None:
        self._metas.clear()
        self._errors.clear()
        root = self.skills_root
        if not root.exists():
            return

        for dirpath, dirnames, filenames in os.walk(root):
            if "SKILL.md" not in filenames:
                continue

            # Don't recurse into children once we've found a skill root
            dirnames[:] = []

            entry = Path(dirpath) / "SKILL.md"
            try:
                text = entry.read_text(encoding="utf-8")
                fm, _body = parse_skill_md(text)
                validate_frontmatter(fm, dir_name=Path(dirpath).name)
            except Exception as e:
                self._errors[entry] = f"{type(e).__name__}: {e}"
                continue

            name = str(fm["name"]).strip()
            desc = str(fm["description"]).strip()

            meta = SkillMeta(
                name=name,
                description=desc,
                license=str(fm.get("license")).strip() if fm.get("license") is not None else None,
                compatibility=str(fm.get("compatibility")).strip() if fm.get("compatibility") is not None else None,
                metadata=_normalize_metadata(fm),
                allowed_tools=_normalize_allowed_tools(fm),
                root_dir=Path(dirpath),
                entry_path=entry,
                location=str(entry.resolve()),
            )
            self._metas[name] = meta

    def list_metas(self) -> List[SkillMeta]:
        return list(self._metas.values())

    def get_meta(self, name: str) -> Optional[SkillMeta]:
        return self._metas.get(name)

    def list_errors(self) -> Dict[Path, str]:
        return dict(self._errors)

    def load_skill(self, name: str) -> Optional[Skill]:
        meta = self.get_meta(name)
        if not meta or not meta.entry_path or not meta.root_dir:
            return None

        text = meta.entry_path.read_text(encoding="utf-8")
        fm, body = parse_skill_md(text)
        validate_frontmatter(fm, dir_name=meta.root_dir.name)

        meta2 = dataclasses.replace(
            meta,
            name=str(fm["name"]).strip(),
            description=str(fm["description"]).strip(),
            license=str(fm.get("license")).strip() if fm.get("license") is not None else None,
            compatibility=str(fm.get("compatibility")).strip() if fm.get("compatibility") is not None else None,
            metadata=_normalize_metadata(fm),
            allowed_tools=_normalize_allowed_tools(fm),
        )
        return Skill(meta=meta2, body_markdown=body.strip())


class FileSystemSkillProvider:
    """Adapter: exposes SkillRegistry via the SkillProvider protocol."""
    def __init__(self, skills_root: Path):
        self.registry = SkillRegistry(skills_root)

    def refresh(self) -> None:
        self.registry.refresh()

    def list_metas(self) -> List[SkillMeta]:
        return self.registry.list_metas()

    def load_skill(self, name: str) -> Optional[Skill]:
        return self.registry.load_skill(name)

    def list_errors(self) -> Dict[str, str]:
        return {str(p): err for p, err in self.registry.list_errors().items()}


# =============================================================================
# Tool/API Provider (NEW): works without local filesystem
# =============================================================================

class SkillGateway(Protocol):
    """
    Contract for a tool-based integration. Implement these four methods against:
      - HTTP service
      - plugin/tool calls
      - internal RPC

    Keep them fast and cache-friendly:
      - list_skills(): metadata only
      - get_skill(): full SKILL.md body
      - read_file(): file content
      - run(): run scripts/commands in a sandbox
    """
    def list_skills(self) -> List[Dict[str, Any]]: ...
    def get_skill(self, name: str) -> Dict[str, Any]: ...
    def read_file(self, name: str, path: str, max_bytes: int = 200_000) -> str: ...
    def run(self, name: str, command: List[str], timeout_s: int = 30,
            env: Optional[Dict[str, str]] = None) -> Dict[str, Any]: ...


class SimpleTTLCache:
    """Tiny TTL cache for API integrations."""
    def __init__(self, ttl_s: int = 60):
        self.ttl_s = ttl_s
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        v = self._store.get(key)
        if not v:
            return None
        ts, obj = v
        if time.time() - ts > self.ttl_s:
            self._store.pop(key, None)
            return None
        return obj

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()


class ApiSkillProvider:
    """
    SkillProvider using a SkillGateway (HTTP/tool calls).

    Expected shapes:
      list_skills() -> [{name, description, license?, compatibility?, metadata?, allowed_tools?}]
      get_skill(name) -> {name, description?, body_markdown, license?, compatibility?, metadata?, allowed_tools?, version?}
    """
    def __init__(self, gateway: SkillGateway, cache_ttl_s: int = 60):
        self.gateway = gateway
        self._metas: Dict[str, SkillMeta] = {}
        self._errors: Dict[str, str] = {}
        self._cache = SimpleTTLCache(ttl_s=cache_ttl_s)

    def refresh(self) -> None:
        self._errors.clear()
        self._metas.clear()

        cached = self._cache.get("list_skills")
        if cached is None:
            try:
                cached = self.gateway.list_skills()
                self._cache.set("list_skills", cached)
            except Exception as e:
                self._errors["list_skills"] = f"{type(e).__name__}: {e}"
                return

        for x in cached:
            try:
                name = str(x["name"]).strip()
                desc = str(x["description"]).strip()
                meta = SkillMeta(
                    name=name,
                    description=desc,
                    license=x.get("license"),
                    compatibility=x.get("compatibility"),
                    metadata=x.get("metadata"),
                    allowed_tools=x.get("allowed_tools") or x.get("allowed-tools"),
                    location=x.get("location") or f"tool://skills/{name}",
                    root_dir=None,
                    entry_path=None,
                )
                self._metas[name] = meta
            except Exception as e:
                self._errors[f"skill:{x!r}"] = f"{type(e).__name__}: {e}"

    def list_metas(self) -> List[SkillMeta]:
        return list(self._metas.values())

    def load_skill(self, name: str) -> Optional[Skill]:
        key = f"skill:{name}"
        cached = self._cache.get(key)
        if cached is None:
            try:
                cached = self.gateway.get_skill(name)
                self._cache.set(key, cached)
            except Exception as e:
                self._errors[f"get_skill:{name}"] = f"{type(e).__name__}: {e}"
                return None

        try:
            body = str(cached.get("body_markdown") or cached.get("body") or "").strip()
            if not body:
                raise ValueError("Empty body_markdown returned from gateway.get_skill()")

            meta = self._metas.get(name) or SkillMeta(
                name=str(cached.get("name") or name).strip(),
                description=str(cached.get("description") or "").strip(),
                location=f"tool://skills/{name}",
            )

            # Allow get_skill() to override/extend meta fields
            meta2 = dataclasses.replace(
                meta,
                description=str(cached.get("description") or meta.description or "").strip(),
                license=cached.get("license", meta.license),
                compatibility=cached.get("compatibility", meta.compatibility),
                metadata=cached.get("metadata", meta.metadata),
                allowed_tools=cached.get("allowed_tools") or cached.get("allowed-tools") or meta.allowed_tools,
                location=cached.get("location") or meta.location,
            )
            return Skill(meta=meta2, body_markdown=body)
        except Exception as e:
            self._errors[f"parse_skill:{name}"] = f"{type(e).__name__}: {e}"
            return None

    def list_errors(self) -> Dict[str, str]:
        return dict(self._errors)


# -----------------------------------------------------------------------------
# Reference HTTP gateway (optional): implement SkillGateway over REST
# -----------------------------------------------------------------------------

class HttpSkillGateway:
    """
    Optional reference implementation of SkillGateway over HTTP.

    Endpoints (suggested):
      GET  /skills
      GET  /skills/{name}
      GET  /skills/{name}/files?path=...&max_bytes=...
      POST /skills/{name}/run   {"command":[...], "timeout_s":30, "env":{...}}
    """
    def __init__(self, base_url: str, api_key: Optional[str] = None, timeout_s: int = 15):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def list_skills(self) -> List[Dict[str, Any]]:
        return self._get("/skills")

    def get_skill(self, name: str) -> Dict[str, Any]:
        return self._get(f"/skills/{urllib.parse.quote(name)}")

    def read_file(self, name: str, path: str, max_bytes: int = 200_000) -> str:
        q = urllib.parse.urlencode({"path": path, "max_bytes": str(max_bytes)})
        x = self._get(f"/skills/{urllib.parse.quote(name)}/files?{q}")
        return x["content"]

    def run(self, name: str, command: List[str], timeout_s: int = 30,
            env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        payload = {"command": command, "timeout_s": timeout_s, "env": env or {}}
        return self._post(f"/skills/{urllib.parse.quote(name)}/run", payload)


# =============================================================================
# Selector (unchanged, pluggable)
# =============================================================================

class SkillSelector(Protocol):
    def select(self, task: str, metas: List[SkillMeta], k: int = 3) -> List[Selection]:
        ...


class KeywordBM25Selector:
    """Lightweight selector: BM25-ish scoring on (name + description)."""
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b

    @staticmethod
    def _tokenize(s: str) -> List[str]:
        s = s.lower()
        s = re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", " ", s)
        toks = [t for t in s.split() if len(t) >= 2]
        return toks

    def select(self, task: str, metas: List[SkillMeta], k: int = 3) -> List[Selection]:
        docs = [(m.name, f"{m.name} {m.description}".strip()) for m in metas]
        q = self._tokenize(task)
        if not q or not docs:
            return []

        df: Dict[str, int] = {}
        doc_tokens: Dict[str, List[str]] = {}
        doc_lens: Dict[str, int] = {}
        for name, text in docs:
            toks = self._tokenize(text)
            doc_tokens[name] = toks
            doc_lens[name] = len(toks)
            for t in set(toks):
                df[t] = df.get(t, 0) + 1

        N = len(docs)
        avgdl = sum(doc_lens.values()) / max(N, 1)

        def idf(t: str) -> float:
            n = df.get(t, 0)
            return math.log(1 + (N - n + 0.5) / (n + 0.5))

        selections: List[Selection] = []
        for name, _text in docs:
            toks = doc_tokens[name]
            tf: Dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1

            score = 0.0
            for t in q:
                if t not in tf:
                    continue
                freq = tf[t]
                denom = freq + self.k1 * (1 - self.b + self.b * (doc_lens[name] / max(avgdl, 1e-9)))
                score += idf(t) * (freq * (self.k1 + 1)) / denom

            if score > 0:
                selections.append(Selection(skill_name=name, score=score, reason="BM25 match"))

        selections.sort(key=lambda x: x.score, reverse=True)
        return selections[:k]


# =============================================================================
# Loader (updated: handles tool-based locations)
# =============================================================================

@dataclasses.dataclass
class LoaderConfig:
    include_all_skill_metadata: bool = True
    max_selected_skills: int = 2  # limit token use
    inject_skill_body_as: str = "system"  # "system" | "developer" | "assistant" | "user"
    metadata_format: str = "xml"  # "xml" or "list"
    include_location: bool = True  # filesystem-based: path; tool-based: location string


class SkillLoader:
    def __init__(self, provider: SkillProvider, config: LoaderConfig = LoaderConfig()):
        self.provider = provider
        self.config = config

    def _escape_xml(self, s: str) -> str:
        return (
            s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;")
        )

    def build_metadata_block(self, metas: List[SkillMeta]) -> str:
        if not metas:
            return ""

        if self.config.metadata_format == "xml":
            lines = ["<available_skills>"]
            for m in sorted(metas, key=lambda x: x.name):
                lines.append("  <skill>")
                lines.append(f"    <name>{self._escape_xml(m.name)}</name>")
                lines.append(f"    <description>{self._escape_xml(m.description.strip().replace(chr(10), ' '))}</description>")
                if self.config.include_location:
                    loc = None
                    if m.entry_path is not None:
                        try:
                            loc = str(m.entry_path.resolve())
                        except Exception:
                            loc = str(m.entry_path)
                    if loc is None:
                        loc = m.location or ""
                    lines.append(f"    <location>{self._escape_xml(loc)}</location>")
                lines.append("  </skill>")
            lines.append("</available_skills>")
            return "\n".join(lines).strip()

        lines = ["Available skills (name: description):"]
        for m in sorted(metas, key=lambda x: x.name):
            desc = m.description.strip().replace("\n", " ")
            lines.append(f"- {m.name}: {desc}")
        return "\n".join(lines).strip()

    def inject(
        self,
        base_messages: List[Dict[str, str]],
        selected: List[Selection],
        metas: List[SkillMeta],
    ) -> Tuple[List[Dict[str, str]], List[Skill], ToolPolicy]:
        injected: List[Dict[str, str]] = []
        loaded: List[Skill] = []

        if self.config.include_all_skill_metadata and metas:
            block = self.build_metadata_block(metas)
            if block:
                injected.append({"role": "system", "content": block})

        chosen = selected[: self.config.max_selected_skills]

        allowed: Optional[List[str]] = None

        role = self.config.inject_skill_body_as
        if role not in ("system", "developer", "assistant", "user"):
            role = "system"

        for sel in chosen:
            skill = self.provider.load_skill(sel.skill_name)
            if not skill:
                continue
            loaded.append(skill)

            injection = f"[Skill: {skill.meta.name}]\n{skill.body_markdown}".strip()
            injected.append({"role": role, "content": injection})

            if skill.meta.allowed_tools is not None:
                if allowed is None:
                    allowed = list(skill.meta.allowed_tools)
                else:
                    allowed = [t for t in allowed if t in skill.meta.allowed_tools]

        policy = ToolPolicy(allowed_tools=allowed)
        return injected + list(base_messages), loaded, policy


# =============================================================================
# Execution backends
# =============================================================================

class SkillExecutionError(RuntimeError):
    pass


class LocalExecutionBackend:
    """
    Filesystem-based backend. For real security, run inside a container/VM/no-network sandbox.
    """
    def __init__(self, command_allowlist: Optional[List[str]] = None, default_timeout_s: int = 30):
        self.command_allowlist = command_allowlist
        self.default_timeout_s = default_timeout_s

    def _confine_path(self, root: Path, rel_path: str) -> Path:
        p = (root / rel_path).resolve()
        r = root.resolve()
        if not str(p).startswith(str(r) + os.sep) and p != r:
            raise SkillExecutionError(f"Path escapes skill root: {rel_path}")
        return p

    def read_file(self, skill: SkillMeta, rel_path: str, max_bytes: int = 200_000) -> str:
        if not skill.root_dir:
            raise SkillExecutionError("LocalExecutionBackend requires skill.root_dir")
        p = self._confine_path(skill.root_dir, rel_path)
        data = p.read_bytes()
        if len(data) > max_bytes:
            data = data[:max_bytes]
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="replace")

    def run_script(
        self,
        skill: SkillMeta,
        command: List[str],
        timeout_s: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        if not skill.root_dir:
            raise SkillExecutionError("LocalExecutionBackend requires skill.root_dir")
        if not command:
            raise SkillExecutionError("Empty command")

        exe = command[0]
        if self.command_allowlist is not None and exe not in self.command_allowlist:
            raise SkillExecutionError(f"Command not allowed: {exe}")

        confined_cmd: List[str] = [exe]
        for arg in command[1:]:
            if arg.startswith("-"):
                confined_cmd.append(arg)
                continue

            if not os.path.isabs(arg):
                candidate = (skill.root_dir / arg)
                if candidate.exists():
                    confined_cmd.append(str(self._confine_path(skill.root_dir, arg)))
                else:
                    confined_cmd.append(arg)
            else:
                raise SkillExecutionError(f"Absolute path arg not allowed: {arg}")

        to = timeout_s or self.default_timeout_s
        try:
            proc = subprocess.run(
                confined_cmd,
                cwd=str(skill.root_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=to,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise SkillExecutionError(f"Timeout after {to}s: {confined_cmd}") from e

        return {
            "command": confined_cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }


class ApiExecutionBackend:
    """Tool-based backend that delegates file/script operations to a SkillGateway."""
    def __init__(self, gateway: SkillGateway):
        self.gateway = gateway

    def read_file(self, skill: SkillMeta, rel_path: str, max_bytes: int = 200_000) -> str:
        return self.gateway.read_file(skill.name, rel_path, max_bytes=max_bytes)

    def run_script(
        self,
        skill: SkillMeta,
        command: List[str],
        timeout_s: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        return self.gateway.run(skill.name, command, timeout_s=timeout_s or 30, env=env)


# =============================================================================
# SkillManager (patched): provider + backend are swappable
# =============================================================================

class SkillManager:
    """
    Convenience façade:
      - provider.refresh()
      - selector.select()
      - loader.inject()
      - execution backend for tools
    """
    def __init__(
        self,
        skills_root: Optional[Path] = None,
        *,
        provider: Optional[SkillProvider] = None,
        selector: Optional[SkillSelector] = None,
        loader: Optional[SkillLoader] = None,
        execution: Optional[ExecutionBackend] = None,
    ):
        if provider is None:
            if skills_root is None:
                raise ValueError("Provide either skills_root (filesystem) or provider (tool-based).")
            provider = FileSystemSkillProvider(skills_root)

        self.provider = provider
        self.selector = selector or KeywordBM25Selector()
        self.loader = loader or SkillLoader(self.provider)
        self.execution = execution or LocalExecutionBackend(command_allowlist=["python", "node", "bash"])

    def refresh(self) -> None:
        self.provider.refresh()

    def prepare_turn(
        self,
        base_messages: List[Dict[str, str]],
        task: str,
        k: int = 3,
    ) -> Tuple[List[Dict[str, str]], List[Skill], ToolPolicy, List[Selection]]:
        metas = self.provider.list_metas()
        selections = self.selector.select(task=task, metas=metas, k=k)
        msgs, loaded, policy = self.loader.inject(base_messages, selections, metas)
        return msgs, loaded, policy, selections

    def list_errors(self) -> Dict[str, str]:
        return self.provider.list_errors()

    # Expose generic "tools"
    def tool_read_file(self, active_skill: SkillMeta, rel_path: str) -> str:
        return self.execution.read_file(active_skill, rel_path)

    def tool_run_script(self, active_skill: SkillMeta, command: List[str]) -> Dict[str, Any]:
        return self.execution.run_script(active_skill, command)


# # =============================================================================
# # Example usage
# # =============================================================================

# def example_filesystem():
#     mgr = SkillManager(Path("./skills"))
#     mgr.refresh()

#     user_task = "Please process this PDF file for me and generate a summary report."
#     base_messages = [
#         {"role": "system", "content": "You are a helpful agent."},
#         {"role": "user", "content": user_task},
#     ]

#     messages, loaded_skills, tool_policy, selections = mgr.prepare_turn(base_messages, task=user_task)
#     print("Selected:", selections)
#     print("Active tool policy:", tool_policy.allowed_tools)
#     print("Injected messages count:", len(messages))
#     # print("Errors:", mgr.list_errors())


# def example_tool_based():
#     # Example only (won't run unless you have a service):
#     gateway = HttpSkillGateway("https://your-skill-service.example.com", api_key=None)
#     provider = ApiSkillProvider(gateway)
#     execution = ApiExecutionBackend(gateway)

#     mgr = SkillManager(provider=provider, execution=execution)
#     mgr.refresh()

#     user_task = "Analyze this dataset and create a summary report with charts."
#     base_messages = [
#         {"role": "system", "content": "You are a helpful agent."},
#         {"role": "user", "content": user_task},
#     ]
#     messages, loaded_skills, tool_policy, selections = mgr.prepare_turn(base_messages, task=user_task)
#     print("Selected:", selections)
#     print("Active tool policy:", tool_policy.allowed_tools)
#     print("Injected messages count:", len(messages))


# if __name__ == "__main__":
#     example_filesystem()
