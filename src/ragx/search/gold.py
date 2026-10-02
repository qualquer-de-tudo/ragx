"""Conjunto-ouro derivado do git (RAGX-0167).

O próprio git traz um gabarito grátis, que cresce sozinho: a MENSAGEM do commit é a consulta e os ARQUIVOS alterados são os
documentos relevantes. Vazamento é inevitável e aceito: o índice está no HEAD, que já contém a mudança do commit; o conjunto
mede "dada a intenção, ache o lugar", não previsão. Por isso `commit` e `kind` ficam em cada caso, para permitir recortes.

Só hash curto, assunto e caminhos saem do git: autor, e-mail e corpo do commit NUNCA são lidos. Um assunto que dispare o
`SecurityScanner` é descartado (e contado), sem ser escrito. A saída é determinística: ordem por data do commit e hash, e o
único dado de procedência é o hash do HEAD de origem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ragx.gitinfo import Commit
from ragx.security.entropy import looks_random
from ragx.security.scanner import SecurityScanner, load_ruleset

#: arquivos que quase todo commit toca e que não dizem nada sobre a consulta
_RUIDO = ("CHANGELOG.md", "uv.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock")
_RUIDO_PASTAS = ("knowledge/", "release/", "dist/", "node_modules/", ".ragx/")
_PREFIXO = re.compile(r"^\w+(\([^)]*\))?!?:\s*")
_SUFIXO = re.compile(r"\s*\((?:RAGX-\d+(?:\s*[,/e]\s*(?:RAGX-)?\d+)*)\)\s*$")
_MIN_PALAVRAS = 3


@dataclass
class Funil:
    """Quantos commits sobram depois de cada filtro (o primeiro entregável da RAGX-0167)."""

    total: int = 0
    release: int = 0  # `chore(release)` e afins
    segredo: int = 0  # assunto que dispara o scanner
    consulta_curta: int = 0
    sem_arquivo_indexado: int = 0
    grande_demais: int = 0
    aceitos: int = 0
    arquivos_ruido: int = 0  # arquivos descartados do gabarito (changelog, knowledge, lockfile)

    def linhas(self) -> list[str]:
        return [
            f"commits sem merge                    {self.total}",
            f"  - de release                       {self.release}",
            f"  - assunto com segredo              {self.segredo}",
            f"  - consulta com menos de {_MIN_PALAVRAS} palavras   {self.consulta_curta}",
            f"  - sem arquivo indexado hoje        {self.sem_arquivo_indexado}",
            f"  - com arquivos demais              {self.grande_demais}",
            f"casos gerados                        {self.aceitos}",
        ]


@dataclass(frozen=True)
class GoldCase:
    query: str
    relevant_paths: tuple[str, ...]
    commit: str
    kind: str  # code | doc | mixed
    date: int = 0


@dataclass
class GoldResult:
    cases: list[GoldCase] = field(default_factory=list)
    funnel: Funil = field(default_factory=Funil)


def clean_subject(subject: str) -> str:
    """Assunto sem o prefixo `tipo(escopo):` e sem o sufixo `(RAGX-0xxx)`."""
    texto = _PREFIXO.sub("", subject.strip())
    return _SUFIXO.sub("", texto).strip()


def _tem_segredo(scanner: SecurityScanner, assunto: str) -> bool:
    """O assunto traz um segredo? As regras do scanner pegam o que tem contexto (`chave = valor`, formatos conhecidos); um
    segredo SOLTO na frase só se reconhece pela cara: palavra comprida, com letra e dígito e entropia alta. É conservador de
    propósito (um hash de commit no assunto também cai fora): descartar uma consulta custa pouco, vazar um segredo não."""
    if scanner.scan_content("commit-subject", assunto):
        return True
    for palavra in assunto.split():
        token = palavra.strip(".,;:()[]{}'\"`")
        mistura = any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token)
        if len(token) >= 16 and mistura and looks_random(token, min_entropy=3.0, min_length=16):
            return True
    return False


def _e_ruido(path: str) -> bool:
    nome = PurePosixPath(path).name
    return nome in _RUIDO or path.startswith(_RUIDO_PASTAS) or ".generated." in nome


def derive_cases(
    commits: list[Commit], indexed: dict[str, str], max_files: int = 8, scanner: SecurityScanner | None = None
) -> GoldResult:
    """Casos a partir dos commits. `indexed` mapeia `rel_path -> doc_kind` do que existe hoje em `documents`.

    Arquivo apagado ou renomeado depois some do gabarito (não está em `indexed`); renomeações seguem pelo caminho NOVO.
    """
    scanner = scanner or SecurityScanner(load_ruleset(), min_entropy=3.0)
    out = GoldResult()
    f = out.funnel
    for c in commits:
        f.total += 1
        if c.subject.startswith(("chore(release)", "release:")):
            f.release += 1
            continue
        if _tem_segredo(scanner, c.subject):
            f.segredo += 1
            continue
        consulta = clean_subject(c.subject)
        if len(consulta.split()) < _MIN_PALAVRAS:
            f.consulta_curta += 1
            continue
        relevantes: list[str] = []
        for p in c.files:
            if _e_ruido(p):
                f.arquivos_ruido += 1
            elif p in indexed and p not in relevantes:
                relevantes.append(p)
        if not relevantes:
            f.sem_arquivo_indexado += 1
            continue
        if len(relevantes) > max_files:
            f.grande_demais += 1
            continue
        tipos = {indexed[p] for p in relevantes}
        kind = "code" if tipos == {"code"} else "doc" if tipos <= {"doc", "config"} and "code" not in tipos else "mixed"
        out.cases.append(GoldCase(consulta, tuple(sorted(relevantes)), c.short, kind, c.date))
        f.aceitos += 1
    out.cases.sort(key=lambda g: (g.date, g.commit))
    return out


def render_yaml(result: GoldResult, head: str) -> str:
    """O YAML determinístico: cabeçalho com o hash do HEAD de origem (sem data) e os casos em ordem estável."""
    import json

    linhas = [
        "# Conjunto-ouro derivado do git (RAGX-0167): a mensagem do commit é a consulta e os arquivos alterados,",
        "# os documentos relevantes. Gerado por `ragx gold build`; não edite à mão.",
        f"# HEAD de origem: {head}",
        "",
    ]
    for g in result.cases:
        linhas.append(f"- query: {json.dumps(g.query, ensure_ascii=False)}")
        linhas.append("  class: git")
        linhas.append("  difficulty: hard")
        linhas.append(f"  commit: {g.commit}")
        linhas.append(f"  kind: {g.kind}")
        linhas.append(f"  note: \"derivado de {g.commit}\"")
        linhas.append("  relevant_paths:")
        linhas.extend(f"    - {json.dumps(p, ensure_ascii=False)}" for p in g.relevant_paths)
        linhas.append("")
    return "\n".join(linhas)
