"""Memória de longo prazo: notas em Markdown, busca por índice FTS5.

A pasta de notas é a **fonte da verdade**: arquivos `.md` comuns, que você
edita à mão ou no Obsidian. O índice SQLite ao lado é derivado e descartável
-- se corromper, apaga e reconstrói (5.000 notas em 0,06s medidos).

Por que FTS5 e não busca por substring: além de ser ~240x mais rápida no
mesmo volume, ela ordena por RELEVÂNCIA (BM25) e devolve um **trecho**, não a
nota inteira. Esse trecho é o que importa aqui -- tudo que entra no prompt é
pago a cada turno, e foi essa disciplina que derrubou o ciclo de 3,7s para
2,1s hoje. Trazer 2.000 caracteres de nota quando 200 respondem seria desfazer
esse trabalho.
"""

import os
import re
import sqlite3
import time
import unicodedata
from pathlib import Path

BASE = Path(__file__).parent
BANCO = BASE / ".memoria.db"          # derivado; fica FORA do vault
NOTA_SEMPRE = "_sempre.md"            # sempre no prompt
PASTA_DO_JARVIS = "jarvis"            # a única onde ele escreve
TETO_SEMPRE = 3000                    # caracteres; acima disso ele avisa

# Palavras que não ajudam a discriminar nada em português.
_VAZIAS = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "em",
    "no", "na", "nos", "nas", "por", "para", "pra", "pro", "com", "sem", "que",
    "e", "ou", "se", "ao", "aos", "the", "eu", "voce", "meu", "minha", "seu",
    "sua", "isso", "isto", "aquilo", "ele", "ela", "mais", "menos", "muito",
    "como", "quando", "onde", "qual", "quais", "quem", "sobre", "esta", "estou",
    "foi", "ser", "ter", "tem", "era", "ja", "nao", "sim", "aqui", "ali",
}


def _sem_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                   if not unicodedata.combining(c))


def caminho_vault():
    """Pasta das notas, vinda do .env. Cria a estrutura se ainda não existir."""
    bruto = (os.getenv("VAULT") or "").strip()
    vault = Path(bruto) if bruto else Path.home() / "Jarvis" / "vault"
    try:
        (vault / PASTA_DO_JARVIS).mkdir(parents=True, exist_ok=True)
        sempre = vault / NOTA_SEMPRE
        if not sempre.exists():
            sempre.write_text(
                "# Sempre\n\n"
                "<!-- Isto vai no prompt do Jarvis em TODA conversa. Mantenha\n"
                "     curto: fatos que valem sempre, nao detalhes de um assunto\n"
                "     so. Comentarios como este NAO sao enviados ao modelo. -->\n\n",
                encoding="utf-8")
    except Exception as e:
        print("  [Memoria] nao consegui preparar %s: %s" % (vault, e))
    return vault


# ------------------------------------------------------------------- indice

def _conectar():
    con = sqlite3.connect(BANCO)
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notas "
                "USING fts5(caminho UNINDEXED, titulo, corpo)")
    con.execute("CREATE TABLE IF NOT EXISTS arquivos "
                "(caminho TEXT PRIMARY KEY, mtime REAL)")
    return con


def indexar(vault=None):
    """Sincroniza o índice com a pasta. Devolve (novas, atualizadas, removidas).

    Incremental por mtime: reler tudo a cada busca funcionaria (0,06s para
    5.000 notas), mas relê o disco à toa. O que o mtime não pega -- edição que
    preserva o timestamp -- se resolve apagando o .memoria.db.
    """
    vault = Path(vault or caminho_vault())
    novas = atualizadas = removidas = 0
    con = _conectar()
    try:
        conhecidos = dict(con.execute("SELECT caminho, mtime FROM arquivos"))
        no_disco = set()

        for arq in vault.rglob("*.md"):
            rel = str(arq.relative_to(vault))
            no_disco.add(rel)
            try:
                mtime = arq.stat().st_mtime
            except OSError:
                continue
            if conhecidos.get(rel) == mtime:
                continue
            try:
                corpo = arq.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            titulo = arq.stem.replace("_", " ")
            con.execute("DELETE FROM notas WHERE caminho = ?", (rel,))
            con.execute("INSERT INTO notas (caminho, titulo, corpo) VALUES (?,?,?)",
                        (rel, titulo, _sem_acentos(corpo)))
            con.execute("INSERT OR REPLACE INTO arquivos VALUES (?,?)", (rel, mtime))
            if rel in conhecidos:
                atualizadas += 1
            else:
                novas += 1

        for rel in set(conhecidos) - no_disco:
            con.execute("DELETE FROM notas WHERE caminho = ?", (rel,))
            con.execute("DELETE FROM arquivos WHERE caminho = ?", (rel,))
            removidas += 1

        con.commit()
    finally:
        con.close()
    return novas, atualizadas, removidas


def _consulta_segura(texto):
    """Transforma uma pergunta em linguagem natural numa consulta FTS5.

    Não dá para jogar a frase crua no MATCH: aspas, hifens e parenteses são
    sintaxe para o FTS5 e derrubam a consulta com erro. Ficam as palavras com
    3 letras ou mais que não sejam vazias, unidas por OR -- quem separa o joio
    depois é o BM25, ordenando por relevância.
    """
    palavras = re.findall(r"[a-z0-9]+", _sem_acentos(texto or "").lower())
    uteis = [p for p in palavras if len(p) >= 3 and p not in _VAZIAS]
    return " OR ".join(dict.fromkeys(uteis))          # sem repetir, na ordem


def buscar(consulta, limite=3, largura=18):
    """Notas mais relevantes, já recortadas no trecho que casou.

    Devolve [(titulo, caminho, trecho, score)], da mais relevante para a menos.
    """
    termos = _consulta_segura(consulta)
    if not termos:
        return []
    con = _conectar()
    try:
        linhas = con.execute(
            "SELECT titulo, caminho, snippet(notas, 2, '', '', '...', ?), bm25(notas) "
            "FROM notas WHERE notas MATCH ? ORDER BY bm25(notas) LIMIT ?",
            (largura, termos, limite)).fetchall()
    except sqlite3.OperationalError as e:
        print("  [Memoria] consulta invalida (%s): %r" % (e, termos))
        return []
    finally:
        con.close()
    return linhas


def sempre():
    """Conteúdo do `_sempre.md`, que vai no prompt de sistema todo turno.

    Cortado no teto de propósito: medido hoje, conteúdo ESTÁVEL no prompt custa
    +0,04s a 2.000 caracteres e +0,32s a 20.000. Cabe muita coisa antes de
    doer, mas não é infinito -- e o aviso existe para você perceber antes de
    sentir.
    """
    arq = caminho_vault() / NOTA_SEMPRE
    try:
        texto = arq.read_text(encoding="utf-8").strip()
    except Exception:
        return ""
    # Comentarios HTML sao instrucao para o HUMANO, nao memoria: o Obsidian os
    # esconde na leitura e aqui eles nao chegam ao modelo. Sem isso, o texto de
    # ajuda do arquivo em branco entrava no prompt de TODA conversa -- 117
    # caracteres de instrucao inutil por turno, medidos no primeiro teste.
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.DOTALL)
    linhas = [l for l in texto.splitlines()
              if l.strip() and not l.startswith("#") and l.strip() != "-"]
    texto = "\n".join(linhas).strip()
    if len(texto) > TETO_SEMPRE:
        print("  [Memoria] %s tem %d caracteres (teto %d); cortando. "
              "Mova o excesso para uma nota propria."
              % (NOTA_SEMPRE, len(texto), TETO_SEMPRE))
        texto = texto[:TETO_SEMPRE]
    return texto


def anotar(assunto, texto, origem=""):
    """Grava ou ATUALIZA uma nota em vault/jarvis/. Devolve o caminho.

    Atualiza em vez de acumular: sem isso, um assunto recorrente viraria dez
    notas quase iguais e a busca traria a versao errada. O carimbo de data e
    de origem existe para voce poder auditar de onde saiu cada coisa.
    """
    vault = caminho_vault()
    nome = re.sub(r"[^a-z0-9]+", "-", _sem_acentos(assunto).lower()).strip("-")
    if not nome:
        nome = "nota"
    arq = vault / PASTA_DO_JARVIS / (nome + ".md")

    carimbo = time.strftime("%d/%m/%Y %H:%M")
    bloco = "\n- %s — %s" % (carimbo, texto.strip())
    if origem:
        bloco += "\n  <!-- origem: %s -->" % origem.strip().replace("--", "-")

    try:
        if arq.exists():
            arq.write_text(arq.read_text(encoding="utf-8").rstrip() + bloco + "\n",
                           encoding="utf-8")
        else:
            arq.write_text("# %s\n%s\n" % (assunto.strip(), bloco), encoding="utf-8")
        indexar(vault)
    except Exception as e:
        print("  [Memoria] falhei ao anotar %s: %s" % (arq, e))
        return None
    return arq


def estatisticas():
    """Números para o --doutor."""
    vault = caminho_vault()
    con = _conectar()
    try:
        n = con.execute("SELECT count(*) FROM arquivos").fetchone()[0]
    except Exception:
        n = 0
    finally:
        con.close()
    return {
        "vault": str(vault),
        "existe": vault.is_dir(),
        "notas": n,
        "sempre_chars": len(sempre()),
    }
