"""Consumo real de tokens nas sessões do Claude Code, por projeto (RAGX-0205).

O painel mostrava "tokens economizados" como arquivos inteiros − entregue: um contrafactual que
superestima, porque o agente quase nunca lê o arquivo inteiro. O Claude Code já grava, por
resposta do modelo, os tokens de entrada (normais, lidos do cache, gravados no cache) e de saída,
e cada chamada de ferramenta com o seu resultado. Este módulo lê isso e devolve, por sessão:

- **turnos**: respostas do modelo (ids de mensagem distintos; o mesmo id aparece em vários
  registros, um por bloco, e o uso dele conta UMA vez);
- **tokens**: entrada, cache lido, cache gravado e saída, somados por mensagem;
- **chamadas por tipo**: busca (Grep, Glob e `grep`/`rg`/`find`/`ls`... pelo Bash ou PowerShell),
  leitura (Read e `cat`/`head`/`Get-Content`...), RAGX (`mcp__ragx__*`) e outras;
- **tamanho dos resultados** de busca, leitura e RAGX, em caracteres. Leitura de imagem ou PDF
  conta à parte (`image_reads`): o resultado é base64, enorme e não comparável a texto;
- **adoção**: se a sessão chamou o RAGX, se recebeu a dica de início e o lembrete do primeiro
  Grep/Glob, e se chamou o RAGX depois do lembrete. Vem do transcript, então não depende de o
  servidor MCP saber a sessão.

Privacidade (regra sem exceção): daqui não sai, nem para o cache em disco, texto de prompt, de
resposta, comando, caminho de arquivo ou entrada de ferramenta. O comando do Bash é classificado
em memória e descartado; a pasta de trabalho da sessão (`cwd`) vira hashes da pasta e das pastas
acima dela, comparados com o hash da raiz de cada projeto registrado. O único caminho que sai é o
do próprio projeto, que vem do registro do RAGX (ou do `--project`), não do transcript.

Com e sem RAGX são grupos diferentes de tarefas: o resultado é observação, não experimento.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import statistics
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ragx.perf import RAGX_PREFIX, _blocks, _parse_ts, iter_records

#: Sobe quando a contagem muda: invalida o cache inteiro.
VERSAO_CACHE = 1

#: Cache de uma entrada que não foi revista nesta leitura fica até isto (pela data do arquivo).
CACHE_TTL_S = 120 * 24 * 3600

#: Para mostrar caracteres de resultado como tokens: a mesma aproximação do `ragx perf`.
CHARS_POR_TOKEN = 4

_TIPOS = ("user", "assistant", "attachment")

#: Leitura destes tipos devolve imagem ou documento em base64: conta como `image_reads`.
_IMAGENS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tif", ".tiff", ".pdf"})

_BUSCA = frozenset({
    "grep", "egrep", "fgrep", "rg", "ag", "ack", "find", "fd", "ls", "tree", "findstr",
    "select-string", "sls", "get-childitem", "gci", "dir",
})
_LEITURA = frozenset({"cat", "head", "tail", "less", "more", "bat", "get-content", "gc", "type"})
#: Prefixos que não são o comando em si: `sudo grep`, `xargs rg`, `time find`.
_PREFIXOS = frozenset({"sudo", "xargs", "time", "env", "nice", "command", "exec", "&"})
_SEPARADORES = re.compile(r"\|\||&&|[|;\n]")
_ATRIBUICAO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

#: (campo nosso, chave em `message.usage`)
_USO = (
    ("input_tokens", "input_tokens"),
    ("cache_read_tokens", "cache_read_input_tokens"),
    ("cache_creation_tokens", "cache_creation_input_tokens"),
    ("output_tokens", "output_tokens"),
)


@dataclass(slots=True)
class Uso:
    """Os números de uma sessão (ou de um arquivo dela). Só contagens."""

    turns: int = 0
    prompts: int = 0
    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    output_tokens: int = 0
    search_calls: int = 0
    read_calls: int = 0
    ragx_calls: int = 0
    other_calls: int = 0
    image_reads: int = 0
    search_result_chars: int = 0
    read_result_chars: int = 0
    ragx_result_chars: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_creation_tokens + self.output_tokens

    def somar(self, outro: Uso) -> None:
        for f in fields(self):
            setattr(self, f.name, getattr(self, f.name) + getattr(outro, f.name))

    def valores(self) -> dict[str, int]:
        d = asdict(self)
        d["total_tokens"] = self.total_tokens
        return d


#: As métricas que o relatório resume (medianas e totais), na ordem do JSON.
METRICAS: tuple[str, ...] = (*(f.name for f in fields(Uso)), "total_tokens")


@dataclass(slots=True)
class Arquivo:
    """O que se guarda de UM transcript (a sessão ou um subagente dela): números, datas e hashes."""

    session: str
    sub: bool
    started: str | None
    ended: str | None
    keys: list[str]
    uso: Uso
    hinted: bool = False
    reminded_at: str | None = None
    ragx_last_at: str | None = None

    def para_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_json(cls, d: dict[str, Any]) -> Arquivo:
        dados = dict(d)
        dados["uso"] = Uso(**dados["uso"])
        return cls(**dados)


@dataclass(slots=True)
class Sessao:
    session: str
    profile: str
    started: datetime
    ended: datetime
    keys: frozenset[str]
    uso: Uso = field(default_factory=Uso)
    hinted: bool = False
    reminded: bool = False
    ragx_after_reminder: bool = False


# ── classificação ───────────────────────────────────────────────────────
def _cabeca(segmento: str) -> list[str]:
    """As palavras do segmento a partir do comando: sem `VAR=x`, `sudo`, `xargs`, aspas e parênteses."""
    palavras = [p.strip("\"'`()${}") for p in segmento.split()]
    palavras = [p for p in palavras if p]
    while palavras and (_ATRIBUICAO.match(palavras[0]) or palavras[0].lower() in _PREFIXOS):
        palavras.pop(0)
        # `xargs -0 grep`: as opções do prefixo também saem
        while palavras and palavras[0].startswith("-"):
            palavras.pop(0)
    return palavras


def _nome_comando(palavra: str) -> str:
    nome = re.split(r"[\\/]", palavra)[-1].lower()
    return nome.removesuffix(".exe")


def categoria_comando(comando: str) -> str:
    """`search`, `read` ou `other` para uma linha de shell. O texto não sai daqui."""
    leitura = False
    for segmento in _SEPARADORES.split(comando):
        palavras = _cabeca(segmento)
        if not palavras:
            continue
        nome = _nome_comando(palavras[0])
        if nome in _BUSCA:
            return "search"
        if nome == "git" and len(palavras) > 1 and palavras[1].lower() in ("grep", "ls-files"):
            return "search"
        if nome in _LEITURA or (nome == "sed" and "-n" in palavras[1:]):
            leitura = True
    return "read" if leitura else "other"


def categoria(nome: str, entrada: Any) -> str:
    """Tipo de uma chamada de ferramenta: `ragx`, `search`, `read`, `image` ou `other`."""
    if nome.startswith(RAGX_PREFIX):
        return "ragx"
    if nome in ("Grep", "Glob", "LS"):
        return "search"
    dados = entrada if isinstance(entrada, dict) else {}
    if nome in ("Read", "NotebookRead"):
        alvo = dados.get("file_path") or dados.get("notebook_path") or ""
        sufixo = os.path.splitext(str(alvo))[1].lower()
        return "image" if sufixo in _IMAGENS else "read"
    if nome in ("Bash", "PowerShell"):
        comando = dados.get("command")
        return categoria_comando(comando) if isinstance(comando, str) else "other"
    return "other"


_CONTADOR = {
    "search": "search_calls", "read": "read_calls", "ragx": "ragx_calls",
    "image": "image_reads", "other": "other_calls",
}
_TAMANHO = {"search": "search_result_chars", "read": "read_result_chars", "ragx": "ragx_result_chars"}


def _tamanho(conteudo: Any) -> tuple[int, bool]:
    """(caracteres de texto, tem imagem/documento) do conteúdo de um `tool_result`."""
    if isinstance(conteudo, str):
        return len(conteudo), False
    if not isinstance(conteudo, list):
        return 0, False
    chars, imagem = 0, False
    for b in conteudo:
        if not isinstance(b, dict):
            continue
        if b.get("type") in ("image", "document"):
            imagem = True
        elif isinstance(b.get("text"), str):
            chars += len(b["text"])
    return chars, imagem


def _menciona_ragx(texto: Any) -> bool:
    return isinstance(texto, str) and ("mcp__ragx__" in texto or texto.lstrip().startswith("RAGX"))


def _hook_do_ragx(rec: dict[str, Any]) -> str | None:
    """`hint` (dica de início), `reminder` (lembrete do Grep/Glob) ou `None` para um registro de hook."""
    anexo = rec.get("attachment")
    if not isinstance(anexo, dict):
        return None
    conteudo = anexo.get("content")
    textos = [*conteudo] if isinstance(conteudo, list) else [conteudo]
    textos.append(anexo.get("stdout"))
    if not any(_menciona_ragx(t) for t in textos):
        return None
    evento = anexo.get("hookEvent")
    if evento == "SessionStart":
        return "hint"
    if evento == "PreToolUse":
        return "reminder"
    return None


# ── pasta de trabalho → hashes ──────────────────────────────────────────
def _norm(caminho: str) -> str:
    return os.path.normcase(os.path.normpath(caminho))


def chave(caminho: str | Path) -> str:
    """Hash de uma pasta, para comparar a da sessão com a de um projeto sem guardar nenhuma das duas."""
    return hashlib.sha256(_norm(str(caminho)).encode("utf-8")).hexdigest()[:16]


def _worktree_principal(pasta: Path) -> Path | None:
    """A raiz do repositório principal quando `pasta` está numa worktree do git fora dele."""
    for p in (pasta, *pasta.parents):
        git = p / ".git"
        try:
            if git.is_dir():
                return None
            if not git.is_file():
                continue
            linha = git.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return None
        if not linha.startswith("gitdir:"):
            return None
        alvo = Path(linha.removeprefix("gitdir:").strip())
        if not alvo.is_absolute():
            alvo = p / alvo
        partes = alvo.parts
        if ".git" in partes and "worktrees" in partes:
            return Path(*partes[: partes.index(".git")])
        return None
    return None


def _chaves(cwd: str | None) -> list[str]:
    """Hashes da pasta da sessão e de todas acima dela (e das do repositório principal, numa
    worktree externa). A sessão é de um projeto quando o hash da raiz dele está aqui."""
    if not cwd:
        return []
    alvos = [Path(cwd)]
    with contextlib.suppress(OSError, ValueError):
        principal = _worktree_principal(Path(cwd))
        if principal is not None:
            alvos.append(principal)
    return sorted({chave(p) for a in alvos for p in (a, *a.parents)})


# ── um arquivo ──────────────────────────────────────────────────────────
def analisar_arquivo(path: Path, session: str | None = None, sub: bool = False) -> Arquivo:
    """Lê um transcript e devolve só números. Linha inválida é ignorada."""
    uso = Uso()
    mensagens: dict[str, dict[str, int]] = {}
    ferramentas: dict[str, str] = {}
    respondidas: set[str] = set()
    primeiro: str | None = None
    ultimo: str | None = None
    cwd: str | None = None
    hinted = False
    lembrete: str | None = None
    ragx_ultimo: str | None = None

    for rec in iter_records(path, _TIPOS):
        ts = rec.get("timestamp") if _parse_ts(rec.get("timestamp")) else None
        if ts:
            primeiro = primeiro or ts
            ultimo = ts
        if cwd is None and isinstance(rec.get("cwd"), str):
            cwd = rec["cwd"]
        tipo = rec["type"]

        if tipo == "attachment":
            hook = _hook_do_ragx(rec)
            if hook == "hint":
                hinted = True
            elif hook == "reminder" and ts and (lembrete is None or ts < lembrete):
                lembrete = ts
            continue

        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue

        if tipo == "assistant":
            if msg.get("model") == "<synthetic>":
                continue  # aviso do próprio Claude Code (erro de API), não uma resposta do modelo
            mid = str(msg.get("id") or rec.get("uuid") or "")
            atual = mensagens.setdefault(mid, {})
            bruto = msg.get("usage")
            if isinstance(bruto, dict):
                # Registros repetidos da mesma mensagem trazem o mesmo uso (ou um parcial): o maior vale.
                for campo, origem in _USO:
                    valor = bruto.get(origem)
                    if isinstance(valor, int) and valor > atual.get(campo, 0):
                        atual[campo] = valor
            for b in _blocks(rec):
                if b.get("type") != "tool_use":
                    continue
                tid = str(b.get("id") or "")
                if tid in ferramentas:
                    continue
                cat = categoria(str(b.get("name", "")), b.get("input"))
                ferramentas[tid] = cat
                campo = _CONTADOR[cat]
                setattr(uso, campo, getattr(uso, campo) + 1)
                if cat == "ragx" and ts and (ragx_ultimo is None or ts > ragx_ultimo):
                    ragx_ultimo = ts
            continue

        # user
        if rec.get("isMeta") or rec.get("isCompactSummary"):
            continue
        resultados = [b for b in _blocks(rec) if b.get("type") == "tool_result"]
        if not resultados:
            conteudo = msg.get("content")
            tem_texto = (isinstance(conteudo, str) and bool(conteudo.strip())) or (
                isinstance(conteudo, list) and bool(conteudo)
            )
            if not sub and tem_texto:
                uso.prompts += 1
            continue
        for b in resultados:
            tid = str(b.get("tool_use_id") or "")
            if tid in respondidas:
                continue
            respondidas.add(tid)
            de_quem = ferramentas.get(tid, "")
            chars, imagem = _tamanho(b.get("content"))
            if de_quem == "read" and imagem:
                # Read de um arquivo sem extensão de imagem que devolveu imagem: não é leitura de texto.
                uso.read_calls -= 1
                uso.image_reads += 1
                ferramentas[tid] = "image"
                continue
            if de_quem in _TAMANHO:
                campo = _TAMANHO[de_quem]
                setattr(uso, campo, getattr(uso, campo) + chars)

    uso.turns = len(mensagens)
    for valores in mensagens.values():
        for campo, _ in _USO:
            setattr(uso, campo, getattr(uso, campo) + valores.get(campo, 0))
    return Arquivo(
        session=session or path.stem, sub=sub, started=primeiro, ended=ultimo, keys=_chaves(cwd),
        uso=uso, hinted=hinted, reminded_at=lembrete, ragx_last_at=ragx_ultimo,
    )


# ── cache ───────────────────────────────────────────────────────────────
def cache_padrao() -> Path:
    return Path(os.path.expanduser("~")) / ".ragx" / "cache" / "usage-claude.json"


class _Cache:
    """Números por transcript, válidos enquanto o arquivo não muda (tamanho e data).

    Uma sessão longa tem centenas de MB: reler tudo a cada consulta do painel custaria ~20 s de
    CPU. A chave é o hash do caminho do transcript, e o conteúdo é o `Arquivo` (só números).
    """

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.entradas: dict[str, dict[str, Any]] = {}
        self.vistas: set[str] = set()
        self.mudou = False
        if path is None:
            return
        try:
            dados = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(dados, dict) and dados.get("v") == VERSAO_CACHE and isinstance(dados.get("files"), dict):
            self.entradas = dados["files"]

    @staticmethod
    def _id(arquivo: Path) -> str:
        return hashlib.sha256(_norm(str(arquivo)).encode("utf-8")).hexdigest()[:24]

    def ler(self, arquivo: Path, st: os.stat_result) -> Arquivo | None:
        ident = self._id(arquivo)
        self.vistas.add(ident)
        e = self.entradas.get(ident)
        if not e or e.get("size") != st.st_size or e.get("mtime_ns") != st.st_mtime_ns:
            return None
        try:
            return Arquivo.de_json(e["data"])
        except (KeyError, TypeError):
            return None

    def gravar(self, arquivo: Path, st: os.stat_result, dados: Arquivo) -> None:
        self.entradas[self._id(arquivo)] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "data": dados.para_json()}
        self.mudou = True

    def salvar(self) -> None:
        if self.path is None or not self.mudou:
            return
        limite = (time.time() - CACHE_TTL_S) * 1e9
        manter = {
            k: v for k, v in self.entradas.items() if k in self.vistas or v.get("mtime_ns", 0) >= limite
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"v": VERSAO_CACHE, "files": manter}, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass


# ── sessões ─────────────────────────────────────────────────────────────
def perfis_claude() -> list[tuple[str, Path]]:
    """(nome, pasta) de cada perfil do Claude Code, pela mesma descoberta de `ragx claude status`."""
    from ragx.clients.registry import claude_profile_dir, claude_profile_name, claude_profiles

    return [(claude_profile_name(c), claude_profile_dir(c)) for c in claude_profiles()]


def _transcripts(pasta_projects: Path) -> list[tuple[Path, str, bool]]:
    """(arquivo, sessão, é subagente) sob a pasta `projects` de um perfil."""
    achados: list[tuple[Path, str, bool]] = []
    try:
        pastas = [p for p in pasta_projects.iterdir() if p.is_dir()]
    except OSError:
        return achados
    for pasta in pastas:
        with contextlib.suppress(OSError):
            achados.extend((f, f.stem, False) for f in pasta.glob("*.jsonl"))
            achados.extend((f, f.parent.parent.name, True) for f in pasta.glob("*/subagents/*.jsonl"))
    return achados


def coletar(
    since: datetime,
    perfis: list[tuple[str, Path]] | None = None,
    cache: Path | None = None,
) -> list[Sessao]:
    """Toda sessão do Claude Code iniciada desde `since`, em todos os perfis, com os subagentes somados.

    Arquivo não modificado desde `since` nem é aberto: não pode ter começado depois.
    """
    perfis = perfis_claude() if perfis is None else perfis
    memo = _Cache(cache)
    limite = since.timestamp()
    por_sessao: dict[tuple[str, str], list[Arquivo]] = {}
    for nome, pasta in perfis:
        for arquivo, sessao, sub in _transcripts(pasta / "projects"):
            try:
                st = arquivo.stat()
            except OSError:
                continue
            if st.st_mtime < limite:
                continue
            dados = memo.ler(arquivo, st)
            if dados is None:
                try:
                    dados = analisar_arquivo(arquivo, sessao, sub)
                except OSError:
                    continue
                memo.gravar(arquivo, st, dados)
            por_sessao.setdefault((nome, sessao), []).append(dados)
    memo.salvar()

    sessoes: list[Sessao] = []
    for (perfil, sessao), arquivos in por_sessao.items():
        principal = next((a for a in arquivos if not a.sub), None)
        if principal is None or principal.started is None:
            continue  # subagente sem a sessão: a sessão começou antes da janela
        inicio = _parse_ts(principal.started)
        if inicio is None or inicio < since:
            continue
        fins = [t for t in (_parse_ts(a.ended) for a in arquivos) if t is not None]
        s = Sessao(
            session=sessao, profile=perfil, started=inicio, ended=max(fins, default=inicio),
            keys=frozenset(principal.keys),
        )
        lembrete: str | None = None
        ragx_ultimo: str | None = None
        for a in arquivos:
            s.uso.somar(a.uso)
            s.hinted = s.hinted or a.hinted
            if a.reminded_at and (lembrete is None or a.reminded_at < lembrete):
                lembrete = a.reminded_at
            if a.ragx_last_at and (ragx_ultimo is None or a.ragx_last_at > ragx_ultimo):
                ragx_ultimo = a.ragx_last_at
        s.reminded = lembrete is not None
        t_lembrete, t_ragx = _parse_ts(lembrete), _parse_ts(ragx_ultimo)
        s.ragx_after_reminder = t_lembrete is not None and t_ragx is not None and t_ragx >= t_lembrete
        sessoes.append(s)
    sessoes.sort(key=lambda s: s.started)
    return sessoes


# ── projetos e relatório ────────────────────────────────────────────────
def projetos_registrados(home: Path | None = None) -> list[dict[str, Any]]:
    """Projetos do hub (`~/.ragx/hub/registry.json`, o mesmo que o painel lê) com pasta local."""
    base = home or Path(os.path.expanduser("~"))
    try:
        dados = json.loads((base / ".ragx" / "hub" / "registry.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    saida: list[dict[str, Any]] = []
    for p in (dados or {}).get("projects") or []:
        if isinstance(p, dict) and isinstance(p.get("path"), str) and p["path"]:
            saida.append({"id": p.get("id"), "name": p.get("name") or Path(p["path"]).name, "path": p["path"]})
    return saida


def projeto_de(sessao: Sessao, projetos: list[dict[str, Any]]) -> dict[str, Any] | None:
    """O projeto da sessão: o de raiz mais funda que contém a pasta dela (ou a worktree dela)."""
    melhor: dict[str, Any] | None = None
    for p in projetos:
        if chave(p["path"]) in sessao.keys and (melhor is None or len(_norm(p["path"])) > len(_norm(melhor["path"]))):
            melhor = p
    return melhor


def _iso(t: datetime | None) -> str | None:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z") if t else None


def _grupo(sessoes: list[Sessao]) -> dict[str, Any]:
    valores = [s.uso.valores() for s in sessoes]
    return {
        "sessions": len(sessoes),
        "median": {
            m: (round(float(statistics.median(v[m] for v in valores)), 1) if valores else None) for m in METRICAS
        },
        "total": {m: sum(v[m] for v in valores) for m in METRICAS},
    }


def resumo(sessoes: list[Sessao]) -> dict[str, Any]:
    """Sessões, medianas com e sem RAGX, adoção e conversão do lembrete."""
    com = [s for s in sessoes if s.uso.ragx_calls > 0]
    sem = [s for s in sessoes if s.uso.ragx_calls == 0]
    perfis: dict[str, int] = {}
    for s in sessoes:
        perfis[s.profile] = perfis.get(s.profile, 0) + 1
    return {
        "sessions": len(sessoes),
        "first_at": _iso(min((s.started for s in sessoes), default=None)),
        "last_at": _iso(max((s.ended for s in sessoes), default=None)),
        "all": _grupo(sessoes),
        "with_ragx": _grupo(com),
        "without_ragx": _grupo(sem),
        "adoption": {
            "sessions": len(sessoes),
            "with_ragx": len(com),
            "hinted": sum(1 for s in sessoes if s.hinted),
            "reminded": sum(1 for s in sessoes if s.reminded),
            "ragx_after_reminder": sum(1 for s in sessoes if s.ragx_after_reminder),
        },
        "profiles": perfis,
    }


NOTA = (
    "Observação, não experimento: sessões com e sem RAGX são tarefas diferentes. "
    "Tokens lidos dos transcripts do Claude Code; tamanho de resultado em caracteres."
)


def relatorio(
    sessoes: list[Sessao],
    projetos: list[dict[str, Any]],
    days: int,
    since: datetime,
    perfis: list[tuple[str, Path]],
) -> dict[str, Any]:
    """O JSON de `ragx usage`: só contagens, datas e os projetos do registro do RAGX."""
    por_projeto: dict[int, list[Sessao]] = {}
    fora = 0
    for s in sessoes:
        p = projeto_de(s, projetos)
        if p is None:
            fora += 1
            continue
        por_projeto.setdefault(id(p), []).append(s)
    dentro = [s for lista in por_projeto.values() for s in lista]
    por_perfil: dict[str, int] = {nome: 0 for nome, _ in perfis}
    for s in sessoes:
        por_perfil[s.profile] = por_perfil.get(s.profile, 0) + 1
    lista = [
        {"id": p["id"], "name": p["name"], "path": p["path"], **resumo(por_projeto[id(p)])}
        for p in projetos
        if id(p) in por_projeto
    ]
    lista.sort(key=lambda x: (-x["sessions"], str(x["name"]).lower()))
    return {
        "source": "claude-code",
        "kind": "observation",
        "note": NOTA,
        "days": days,
        "since": _iso(since),
        "generated_at": _iso(datetime.now(UTC)),
        "chars_per_token": CHARS_POR_TOKEN,
        "profiles": [{"name": n, "sessions": c} for n, c in por_perfil.items()],
        "sessions_scanned": len(sessoes),
        "sessions_outside_projects": fora,
        "overall": resumo(dentro),
        "projects": lista,
    }
