"""Acesso ao banco de dados SQLite (RNF-04).

Este módulo salva e carrega os objetos de modelos.py.
"""
import os
import sqlite3
from contextlib import contextmanager
import shutil
from datetime import date, datetime

from modelos import (
    PERFIL_ADMINISTRADOR, ErroRegraNegocio, criar_usuario, gerar_hash,
    Produto,
    Devolucao, ItemDevolucao, Evidencia, RegistroHistorico,
    EncaminhamentoEstoque,
    Mediacao,
)

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_BANCO = os.path.join(PASTA_PROJETO, "devolucoes.db")
PASTA_EVIDENCIAS = os.path.join(PASTA_PROJETO, "evidencias")

SQL_TABELAS = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    login TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS produtos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    sku TEXT NOT NULL,
    nome TEXT NOT NULL,
    categoria TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS devolucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_pedido TEXT NOT NULL,
    plataforma TEXT NOT NULL DEFAULT '',
    data_recebimento TEXT NOT NULL,
    status TEXT NOT NULL,
    conferida_comercial INTEGER NOT NULL DEFAULT 0,
    responsavel_id INTEGER NOT NULL REFERENCES usuarios(id)
);
CREATE TABLE IF NOT EXISTS itens_devolucao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devolucao_id INTEGER NOT NULL REFERENCES devolucoes(id),
    produto_id INTEGER NOT NULL REFERENCES produtos(id),
    quantidade INTEGER NOT NULL,
    situacao TEXT NOT NULL,
    descricao_avaria TEXT
);
CREATE TABLE IF NOT EXISTS evidencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES itens_devolucao(id),
    tipo TEXT NOT NULL,
    caminho_arquivo TEXT NOT NULL,
    data_envio TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS encaminhamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL UNIQUE REFERENCES itens_devolucao(id),
    responsavel_id INTEGER NOT NULL REFERENCES usuarios(id),
    quantidade INTEGER NOT NULL,
    data_hora TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mediacoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devolucao_id INTEGER NOT NULL UNIQUE REFERENCES devolucoes(id),
    plataforma TEXT NOT NULL,
    protocolo TEXT NOT NULL,
    data_abertura TEXT NOT NULL,
    resultado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devolucao_id INTEGER NOT NULL REFERENCES devolucoes(id),
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    acao TEXT NOT NULL,
    data_hora TEXT NOT NULL
);
"""


@contextmanager
def conectar():
    """Abre a conexão, confirma as alterações (commit) no final e sempre fecha o banco."""
    conexao = sqlite3.connect(ARQUIVO_BANCO)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    try:
        yield conexao
        conexao.commit()
    except Exception:
        conexao.rollback()
        raise
    finally:
        conexao.close()


def criar_tabelas():
    with conectar() as conexao:
        conexao.executescript(SQL_TABELAS)
        # Bancos criados antes da plataforma existir ganham a coluna nova
        colunas = [linha["name"] for linha in conexao.execute("PRAGMA table_info(devolucoes)")]
        if "plataforma" not in colunas:
            conexao.execute("ALTER TABLE devolucoes ADD COLUMN plataforma TEXT NOT NULL DEFAULT ''")


def criar_admin_padrao():
    """Na primeira execução, cria o usuário admin (senha admin123) para o primeiro acesso."""
    with conectar() as conexao:
        total = conexao.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if total == 0:
            conexao.execute(
                "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, 1)",
                ("Administrador", "admin", gerar_hash("admin123"), PERFIL_ADMINISTRADOR))


def inicializar():
    criar_tabelas()
    criar_admin_padrao()


# ---------------------------------------------------------------- usuários
def _para_usuario(linha):
    if linha is None:
        return None
    return criar_usuario(linha["perfil"], linha["nome"], linha["login"], linha["senha_hash"],
                         bool(linha["ativo"]), linha["id"])


def buscar_usuario_por_login(login):
    with conectar() as conexao:
        return _para_usuario(conexao.execute("SELECT * FROM usuarios WHERE login = ?", (login,)).fetchone())


def buscar_usuario_por_id(id):
    with conectar() as conexao:
        return _para_usuario(conexao.execute("SELECT * FROM usuarios WHERE id = ?", (id,)).fetchone())


def listar_usuarios():
    with conectar() as conexao:
        return [_para_usuario(l) for l in conexao.execute("SELECT * FROM usuarios ORDER BY nome")]


def salvar_usuario(usuario):
    try:
        with conectar() as conexao:
            if usuario.id is None:
                cursor = conexao.execute(
                    "INSERT INTO usuarios (nome, login, senha_hash, perfil, ativo) VALUES (?, ?, ?, ?, ?)",
                    (usuario.nome, usuario.login, usuario.senhaHash, usuario.obterPerfil(), int(usuario.ativo)))
                usuario.id = cursor.lastrowid
            else:
                conexao.execute(
                    "UPDATE usuarios SET nome = ?, login = ?, senha_hash = ?, ativo = ? WHERE id = ?",
                    (usuario.nome, usuario.login, usuario.senhaHash, int(usuario.ativo), usuario.id))
    except sqlite3.IntegrityError:
        raise ErroRegraNegocio("Já existe um usuário com este login.")


# ---------------------------------------------------------------- produtos
def _para_produto(linha):
    if linha is None:
        return None
    return Produto(linha["codigo"], linha["sku"], linha["nome"], linha["categoria"],
                   bool(linha["ativo"]), linha["id"])


def salvar_produto(produto):
    try:
        with conectar() as conexao:
            if produto.id is None:
                cursor = conexao.execute(
                    "INSERT INTO produtos (codigo, sku, nome, categoria, ativo) VALUES (?, ?, ?, ?, ?)",
                    (produto.codigo, produto.sku, produto.nome, produto.categoria, int(produto.ativo)))
                produto.id = cursor.lastrowid
            else:
                conexao.execute(
                    "UPDATE produtos SET sku = ?, nome = ?, categoria = ?, ativo = ? WHERE id = ?",
                    (produto.sku, produto.nome, produto.categoria, int(produto.ativo), produto.id))
    except sqlite3.IntegrityError:
        raise ErroRegraNegocio("Já existe um produto com este código.")


def buscar_produto_por_codigo(codigo):
    with conectar() as conexao:
        return _para_produto(conexao.execute("SELECT * FROM produtos WHERE codigo = ?", (codigo,)).fetchone())


def buscar_produto_por_id(id):
    with conectar() as conexao:
        return _para_produto(conexao.execute("SELECT * FROM produtos WHERE id = ?", (id,)).fetchone())


def listar_produtos():
    with conectar() as conexao:
        return [_para_produto(l) for l in conexao.execute("SELECT * FROM produtos ORDER BY nome")]


# ---------------------------------------------------------------- devoluções
def copiar_evidencia(caminho_origem):
    """Copia o arquivo de evidência para a pasta evidencias/ do sistema e devolve o novo caminho (RNF-06)."""
    os.makedirs(PASTA_EVIDENCIAS, exist_ok=True)
    nome = datetime.now().strftime("%Y%m%d_%H%M%S_%f_") + os.path.basename(caminho_origem)
    destino = os.path.join(PASTA_EVIDENCIAS, nome)
    shutil.copy2(caminho_origem, destino)
    return destino


def salvar_devolucao(devolucao):
    """Salva a devolução e tudo o que pertence a ela em uma única transação."""
    with conectar() as conexao:
        if devolucao.id is None:
            cursor = conexao.execute(
                "INSERT INTO devolucoes (numero_pedido, plataforma, data_recebimento, status, conferida_comercial, "
                "responsavel_id) VALUES (?, ?, ?, ?, ?, ?)",
                (devolucao.numeroPedido, devolucao.plataforma, devolucao.dataRecebimento.isoformat(), devolucao.status,
                 int(devolucao.conferidaComercial), devolucao.responsavel.id))
            devolucao.id = cursor.lastrowid
        else:
            conexao.execute(
                "UPDATE devolucoes SET status = ?, conferida_comercial = ? WHERE id = ?",
                (devolucao.status, int(devolucao.conferidaComercial), devolucao.id))

        for item in devolucao.itens:
            if item.id is None:
                cursor = conexao.execute(
                    "INSERT INTO itens_devolucao (devolucao_id, produto_id, quantidade, situacao, descricao_avaria) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (devolucao.id, item.produto.id, item.quantidade, item.situacao, item.descricaoAvaria))
                item.id = cursor.lastrowid
            for evidencia in item.evidencias:
                if evidencia.id is None:
                    cursor = conexao.execute(
                        "INSERT INTO evidencias (item_id, tipo, caminho_arquivo, data_envio) VALUES (?, ?, ?, ?)",
                        (item.id, evidencia.tipo, evidencia.caminhoArquivo, evidencia.dataEnvio.isoformat()))
                    evidencia.id = cursor.lastrowid
            encaminhamento = item.encaminhamento
            if encaminhamento is not None and encaminhamento.id is None:
                cursor = conexao.execute(
                    "INSERT INTO encaminhamentos (item_id, responsavel_id, quantidade, data_hora) VALUES (?, ?, ?, ?)",
                    (item.id, encaminhamento.responsavel.id, encaminhamento.quantidade,
                     encaminhamento.dataHora.isoformat()))
                encaminhamento.id = cursor.lastrowid

        mediacao = devolucao.mediacao
        if mediacao is not None:
            if mediacao.id is None:
                cursor = conexao.execute(
                    "INSERT INTO mediacoes (devolucao_id, plataforma, protocolo, data_abertura, resultado) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (devolucao.id, mediacao.plataforma, mediacao.protocolo,
                     mediacao.dataAbertura.isoformat(), mediacao.resultado))
                mediacao.id = cursor.lastrowid
            else:
                conexao.execute("UPDATE mediacoes SET resultado = ? WHERE id = ?", (mediacao.resultado, mediacao.id))

        for registro in devolucao.historico:
            if registro.id is None:
                cursor = conexao.execute(
                    "INSERT INTO historico (devolucao_id, usuario_id, acao, data_hora) VALUES (?, ?, ?, ?)",
                    (devolucao.id, registro.usuario.id, registro.acao, registro.dataHora.isoformat()))
                registro.id = cursor.lastrowid


def carregar_devolucao(id):
    """Monta o objeto Devolucao completo (itens, evidências, mediação e histórico)."""
    with conectar() as conexao:
        linha = conexao.execute("SELECT * FROM devolucoes WHERE id = ?", (id,)).fetchone()
        if linha is None:
            return None
        devolucao = Devolucao(linha["numero_pedido"], linha["plataforma"], date.fromisoformat(linha["data_recebimento"]),
                              buscar_usuario_por_id(linha["responsavel_id"]), linha["status"],
                              bool(linha["conferida_comercial"]), linha["id"])

        for l in conexao.execute("SELECT * FROM itens_devolucao WHERE devolucao_id = ? ORDER BY id", (id,)):
            item = ItemDevolucao(buscar_produto_por_id(l["produto_id"]), l["quantidade"], devolucao,
                                 l["situacao"], l["descricao_avaria"] or "", l["id"])
            for e in conexao.execute("SELECT * FROM evidencias WHERE item_id = ? ORDER BY id", (item.id,)):
                item.evidencias.append(Evidencia(e["tipo"], e["caminho_arquivo"],
                                                 datetime.fromisoformat(e["data_envio"]), e["id"]))
            e = conexao.execute("SELECT * FROM encaminhamentos WHERE item_id = ?", (item.id,)).fetchone()
            if e is not None:
                item.encaminhamento = EncaminhamentoEstoque(e["quantidade"], datetime.fromisoformat(e["data_hora"]),
                                                            buscar_usuario_por_id(e["responsavel_id"]), e["id"])
            devolucao.itens.append(item)

        m = conexao.execute("SELECT * FROM mediacoes WHERE devolucao_id = ?", (id,)).fetchone()
        if m is not None:
            devolucao.mediacao = Mediacao(m["plataforma"], m["protocolo"], date.fromisoformat(m["data_abertura"]),
                                          m["resultado"], m["id"])

        for h in conexao.execute("SELECT * FROM historico WHERE devolucao_id = ? ORDER BY id", (id,)):
            devolucao.historico.append(RegistroHistorico(h["acao"], datetime.fromisoformat(h["data_hora"]),
                                                         buscar_usuario_por_id(h["usuario_id"]), h["id"]))
        return devolucao


def pesquisar_devolucoes(numero_pedido="", status="", codigo_produto="", data_inicio=None, data_fim=None):
    """RF-07: pesquisa devoluções por pedido, status, produto e período de recebimento."""
    sql = "SELECT DISTINCT d.id FROM devolucoes d " \
          "LEFT JOIN itens_devolucao i ON i.devolucao_id = d.id " \
          "LEFT JOIN produtos p ON p.id = i.produto_id WHERE 1 = 1"
    parametros = []
    if numero_pedido:
        sql += " AND d.numero_pedido LIKE ?"
        parametros.append(f"%{numero_pedido}%")
    if status:
        sql += " AND d.status = ?"
        parametros.append(status)
    if codigo_produto:
        sql += " AND p.codigo = ?"
        parametros.append(codigo_produto)
    if data_inicio:
        sql += " AND d.data_recebimento >= ?"
        parametros.append(data_inicio.isoformat())
    if data_fim:
        sql += " AND d.data_recebimento <= ?"
        parametros.append(data_fim.isoformat())
    sql += " ORDER BY d.id"
    with conectar() as conexao:
        ids = [linha["id"] for linha in conexao.execute(sql, parametros)]
    return [carregar_devolucao(id) for id in ids]


def contar_devolucoes_por_status():
    """Conta quantas devoluções existem em cada status, para o painel da tela de Início."""
    with conectar() as conexao:
        return {linha["status"]: linha["total"] for linha in
                conexao.execute("SELECT status, COUNT(*) AS total FROM devolucoes GROUP BY status")}
