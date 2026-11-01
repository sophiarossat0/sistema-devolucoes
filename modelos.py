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

    def cadastrarDevolucao(self, numeroPedido, dataRecebimento):
        numeroPedido = validar_texto(numeroPedido, "número do pedido")
        if not isinstance(dataRecebimento, date):
            raise ErroRegraNegocio("A data de recebimento é inválida.")
        return Devolucao(numeroPedido, dataRecebimento, responsavel=self)


class UsuarioComercial(Usuario):
    def obterPerfil(self):
        return PERFIL_COMERCIAL

    def conferirDevolucao(self, devolucao):
        verificar_aberta(devolucao)
        if devolucao.conferidaComercial:
            raise ErroRegraNegocio("Esta devolução já foi conferida pelo Comercial.")
        devolucao.conferidaComercial = True
        devolucao.registrarHistorico("Devolução conferida com os dados da plataforma de origem", self)

    def registrarEncaminhamento(self, item):
        devolucao = item.devolucao
        verificar_aberta(devolucao)
        if not devolucao.conferidaComercial:  # RN-06 / RN-07
            raise ErroRegraNegocio("A devolução precisa ser conferida pelo Comercial antes do encaminhamento.")
        if item.situacao != SEM_AVARIA:  # RN-07
            raise ErroRegraNegocio("Somente produtos Sem Avaria podem ser encaminhados ao estoque.")
        if item.foiEncaminhado():
            raise ErroRegraNegocio("Este produto já foi encaminhado ao estoque.")
        item.encaminhamento = EncaminhamentoEstoque(item.quantidade, datetime.now(), responsavel=self)
        devolucao.registrarHistorico(
            f"Encaminhamento ao estoque: {item.produto.nome} ({item.quantidade} un.)", self)
        return item.encaminhamento

    def abrirMediacao(self, devolucao, plataforma, protocolo):
        verificar_aberta(devolucao)
        if not devolucao.conferidaComercial:  # RN-06
            raise ErroRegraNegocio("A devolução precisa ser conferida pelo Comercial antes da mediação.")
        if not devolucao.possuiAvaria():  # RN-09
            raise ErroRegraNegocio("Somente devoluções com produto Com Avaria podem ter mediação.")
        if devolucao.mediacao is not None:
            raise ErroRegraNegocio("Esta devolução já possui mediação.")
        devolucao.mediacao = Mediacao(
            validar_texto(plataforma, "plataforma"), validar_texto(protocolo, "protocolo"), date.today())
        devolucao.atualizarStatus()  # RN-10
        devolucao.registrarHistorico(
            f"Mediação aberta na plataforma {devolucao.mediacao.plataforma} "
            f"(protocolo {devolucao.mediacao.protocolo})", self)
        return devolucao.mediacao

    def registrarResultadoMediacao(self, devolucao, resultado):
        verificar_aberta(devolucao)
        if devolucao.mediacao is None:
            raise ErroRegraNegocio("Esta devolução não possui mediação.")
        devolucao.mediacao.registrarResultado(resultado)
        devolucao.atualizarStatus()  # RN-11
        devolucao.registrarHistorico(f"Resultado da mediação registrado: {resultado}", self)
        if devolucao.status == STATUS_PERDAS:
            devolucao.registrarHistorico("Devolução encerrada com status Perdas", self)

    def finalizarDevolucao(self, devolucao):
        verificar_aberta(devolucao)
        pendencias = devolucao.listarPendencias()
        if pendencias:  # RN-13
            raise ErroRegraNegocio("Não é possível finalizar:\n  - " + "\n  - ".join(pendencias))
        devolucao.status = STATUS_CONCLUIDA
        devolucao.registrarHistorico("Devolução finalizada com status Concluída", self)


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


# ---------------------------------------------------------------- devolução
def verificar_aberta(devolucao):
    """RN-14: devoluções encerradas não podem ser alteradas."""
    if devolucao.estaEncerrada():
        raise ErroRegraNegocio(
            f"A devolução está com status {devolucao.status} e não pode mais ser alterada.")


class Devolucao:
    def __init__(self, numeroPedido, dataRecebimento, responsavel=None,
                 status=STATUS_EM_ABERTO, conferidaComercial=False, id=None):
        self.id = id
        self.numeroPedido = numeroPedido
        self.dataRecebimento = dataRecebimento
        self.status = status
        self.conferidaComercial = conferidaComercial
        self.responsavel = responsavel  # UsuarioProducao que cadastrou
        self.itens = []                 # composição com ItemDevolucao
        self.mediacao = None            # associação 0..1 com Mediacao
        self.historico = []             # composição com RegistroHistorico

    def adicionarItem(self, produto, quantidade):
        verificar_aberta(self)
        if produto is None or not produto.ativo:
            raise ErroRegraNegocio("Produto não encontrado ou inativo.")
        if not isinstance(quantidade, int) or quantidade <= 0:
            raise ErroRegraNegocio("A quantidade deve ser maior que zero.")
        item = ItemDevolucao(produto, quantidade, devolucao=self)
        self.itens.append(item)
        return item

    def possuiAvaria(self):
        return any(item.situacao == COM_AVARIA for item in self.itens)

    def validarCadastro(self):
        """RN-02, RN-04 e RN-05: pelo menos um produto, todos classificados e com evidências quando avariados."""
        return len(self.itens) > 0 and all(item.possuiEvidenciasObrigatorias() for item in self.itens)

    def listarPendencias(self):
        """Lista o que ainda falta para finalizar a devolução (RN-13)."""
        pendencias = []
        if not self.conferidaComercial:
            pendencias.append("A devolução ainda não foi conferida pelo Comercial.")
        for item in self.itens:
            if item.situacao == SEM_AVARIA and not item.foiEncaminhado():
                pendencias.append(f"O produto {item.produto.nome} (Sem Avaria) não foi encaminhado ao estoque.")
        if self.possuiAvaria():
            if self.mediacao is None:
                pendencias.append("A devolução possui produto Com Avaria e não tem mediação registrada.")
            elif self.mediacao.resultado != FAVORAVEL:
                pendencias.append(f"A mediação está com resultado {self.mediacao.resultado}.")
        return pendencias

    def podeSerFinalizada(self):
        return not self.estaEncerrada() and not self.listarPendencias()

    def atualizarStatus(self):
        """RN-10 e RN-11: o status acompanha a situação da mediação."""
        if self.estaEncerrada() or self.mediacao is None:
            return
        if self.mediacao.resultado == RECUSADA:
            self.status = STATUS_PERDAS
        else:
            self.status = STATUS_EM_ANDAMENTO

    def estaEncerrada(self):
        return self.status in (STATUS_CONCLUIDA, STATUS_PERDAS)

    def registrarHistorico(self, acao, usuario):
        """RF-13: guarda a ação, o usuário, a data e o horário."""
        registro = RegistroHistorico(acao, datetime.now(), usuario=usuario)
        self.historico.append(registro)
        return registro


class ItemDevolucao:
    def __init__(self, produto, quantidade, devolucao=None, situacao=None, descricaoAvaria="", id=None):
        self.id = id
        self.produto = produto
        self.quantidade = quantidade
        self.situacao = situacao
        self.descricaoAvaria = descricaoAvaria
        self.devolucao = devolucao
        self.evidencias = []        # composição com Evidencia
        self.encaminhamento = None  # associação 0..1 com EncaminhamentoEstoque

    def classificar(self, situacao, descricaoAvaria=""):
        if situacao not in (SEM_AVARIA, COM_AVARIA):
            raise ErroRegraNegocio("A situação deve ser Sem Avaria ou Com Avaria.")
        if situacao == COM_AVARIA:
            descricaoAvaria = validar_texto(descricaoAvaria, "descrição da avaria")
        else:
            descricaoAvaria = ""
            self.evidencias = []
        self.situacao = situacao
        self.descricaoAvaria = descricaoAvaria

    def adicionarEvidencia(self, tipo, caminhoArquivo):
        if self.situacao != COM_AVARIA:
            raise ErroRegraNegocio("Evidências só podem ser anexadas a produtos Com Avaria.")
        evidencia = Evidencia(tipo, caminhoArquivo, datetime.now())
        if not evidencia.validarArquivo():
            extensoes, limite = REGRAS_ARQUIVO.get(tipo, ((), 0))
            raise ErroRegraNegocio(
                f"Arquivo inválido. {tipo} deve existir, ter extensão {', '.join(extensoes)} "
                f"e no máximo {limite // (1024 * 1024)} MB.")
        self.evidencias.append(evidencia)
        return evidencia

    def possuiEvidenciasObrigatorias(self):
        """RN-05: produto Com Avaria precisa de descrição, ao menos uma foto e ao menos um vídeo."""
        if self.situacao == SEM_AVARIA:
            return True
        if self.situacao != COM_AVARIA:
            return False
        tipos = [evidencia.tipo for evidencia in self.evidencias]
        return bool(self.descricaoAvaria) and FOTO in tipos and VIDEO in tipos

    def foiEncaminhado(self):
        return self.encaminhamento is not None


class Evidencia:
    def __init__(self, tipo, caminhoArquivo, dataEnvio, id=None):
        self.id = id
        self.tipo = tipo
        self.caminhoArquivo = caminhoArquivo
        self.dataEnvio = dataEnvio

    def validarArquivo(self):
        """RNF-06: fotos JPG/PNG até 10 MB e vídeos MP4 até 100 MB."""
        if self.tipo not in REGRAS_ARQUIVO or not os.path.isfile(self.caminhoArquivo):
            return False
        extensoes, limite = REGRAS_ARQUIVO[self.tipo]
        extensao = os.path.splitext(self.caminhoArquivo)[1].lower()
        return extensao in extensoes and os.path.getsize(self.caminhoArquivo) <= limite


class RegistroHistorico:
    def __init__(self, acao, dataHora, usuario=None, id=None):
        self.id = id
        self.acao = acao
        self.dataHora = dataHora
        self.usuario = usuario  # associação com Usuario (realizado por)


# ---------------------------------------------------------------- tratamento pelo Comercial
class EncaminhamentoEstoque:
    """Registra o encaminhamento ao estoque, sem alterar o saldo de estoque da empresa (RF-09)."""

    def __init__(self, quantidade, dataHora, responsavel=None, id=None):
        self.id = id
        self.quantidade = quantidade
        self.dataHora = dataHora
        self.responsavel = responsavel  # UsuarioComercial que registrou


class Mediacao:
    def __init__(self, plataforma, protocolo, dataAbertura, resultado=PENDENTE, id=None):
        self.id = id
        self.plataforma = plataforma
        self.protocolo = protocolo
        self.dataAbertura = dataAbertura
        self.resultado = resultado

    def registrarResultado(self, resultado):
        if not self.estaPendente():
            raise ErroRegraNegocio(f"A mediação já possui resultado {self.resultado}.")
        if resultado not in (FAVORAVEL, RECUSADA):
            raise ErroRegraNegocio("O resultado deve ser Favorável ou Recusada.")
        self.resultado = resultado

    def estaPendente(self):
        return self.resultado == PENDENTE
