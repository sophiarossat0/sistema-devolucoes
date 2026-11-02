"""Acesso ao banco de dados SQLite (RNF-04).

Este módulo salva e carrega os objetos de modelos.py.
"""
import os
import sqlite3
from contextlib import contextmanager

from modelos import (
    PERFIL_ADMINISTRADOR, ErroRegraNegocio, criar_usuario, gerar_hash,
    Produto,
)

PASTA_PROJETO = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_BANCO = os.path.join(PASTA_PROJETO, "devolucoes.db")

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


