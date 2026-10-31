"""Classes do Sistema de Gestão e Controle do Processo de Devoluções.

Os nomes das classes, dos atributos e dos métodos seguem o diagrama de classes
de projeto (docs/classes.drawio).
"""
import hashlib
import os
from abc import ABC, abstractmethod
from datetime import date, datetime

# Perfis de acesso
PERFIL_ADMINISTRADOR = "Administrador"
PERFIL_PRODUCAO = "Produção"
PERFIL_COMERCIAL = "Comercial"

# Status da devolução (RF-11)
STATUS_EM_ABERTO = "Em Aberto"
STATUS_EM_ANDAMENTO = "Em Andamento"
STATUS_CONCLUIDA = "Concluída"
STATUS_PERDAS = "Perdas"

# Situação do produto (RN-04)
SEM_AVARIA = "Sem Avaria"
COM_AVARIA = "Com Avaria"

# Tipos de evidência e limites de arquivo (RNF-06)
FOTO = "Foto"
VIDEO = "Vídeo"
REGRAS_ARQUIVO = {
    FOTO: ((".jpg", ".jpeg", ".png"), 10 * 1024 * 1024),
    VIDEO: ((".mp4",), 100 * 1024 * 1024),
}

# Resultado da mediação (RF-10)
PENDENTE = "Pendente"
FAVORAVEL = "Favorável"
RECUSADA = "Recusada"


class ErroRegraNegocio(Exception):
    """Erro lançado quando uma validação ou regra de negócio não é atendida."""


def gerar_hash(senha):
    """Gera o hash SHA-256 da senha (RNF-01)."""
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()


def validar_texto(valor, campo):
    """Garante que um campo obrigatório foi preenchido (RNF-03)."""
    if valor is None or not str(valor).strip():
        raise ErroRegraNegocio(f"O campo '{campo}' é obrigatório.")
    return str(valor).strip()


# ---------------------------------------------------------------- usuários
class Usuario(ABC):
    """Classe abstrata: só existe por meio de Administrador, UsuarioProducao e UsuarioComercial."""

    def __init__(self, nome, login, senhaHash, ativo=True, id=None):
        self.id = id
        self.nome = nome
        self.login = login
        self.senhaHash = senhaHash
        self.ativo = ativo

    def autenticar(self, login, senha):
        return self.ativo and self.login == login and self.senhaHash == gerar_hash(senha)

    def alterarDados(self, nome, login):
        self.nome = validar_texto(nome, "nome")
        self.login = validar_texto(login, "login")

    def desativar(self):
        self.ativo = False

    @abstractmethod
    def obterPerfil(self):
        pass


class Administrador(Usuario):
    def obterPerfil(self):
        return PERFIL_ADMINISTRADOR

    def cadastrarUsuario(self, nome, login, senha, perfil):
        nome = validar_texto(nome, "nome")
        login = validar_texto(login, "login")
        senha = validar_texto(senha, "senha")
        return criar_usuario(perfil, nome, login, gerar_hash(senha))

    def cadastrarProduto(self, codigo, sku, nome, categoria):
        return Produto(
            validar_texto(codigo, "código"),
            validar_texto(sku, "SKU"),
            validar_texto(nome, "nome"),
            validar_texto(categoria, "categoria"),
        )


class UsuarioProducao(Usuario):
    def obterPerfil(self):
        return PERFIL_PRODUCAO


class UsuarioComercial(Usuario):
    def obterPerfil(self):
        return PERFIL_COMERCIAL


def criar_usuario(perfil, nome, login, senhaHash, ativo=True, id=None):
    """Cria o objeto da subclasse correta de acordo com o perfil."""
    classes = {
        PERFIL_ADMINISTRADOR: Administrador,
        PERFIL_PRODUCAO: UsuarioProducao,
        PERFIL_COMERCIAL: UsuarioComercial,
    }
    if perfil not in classes:
        raise ErroRegraNegocio("Perfil inválido. Use Administrador, Produção ou Comercial.")
    return classes[perfil](nome, login, senhaHash, ativo, id)


# ---------------------------------------------------------------- produto
class Produto:
    def __init__(self, codigo, sku, nome, categoria, ativo=True, id=None):
        self.id = id
        self.codigo = codigo
        self.sku = sku
        self.nome = nome
        self.categoria = categoria
        self.ativo = ativo

    def alterarDados(self, nome, categoria):
        self.nome = validar_texto(nome, "nome")
        self.categoria = validar_texto(categoria, "categoria")

    def desativar(self):
        self.ativo = False


