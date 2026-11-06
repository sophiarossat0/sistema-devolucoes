"""Sistema de Gestão e Controle do Processo de Devoluções - versão web.

Execute com:  python main.py
O navegador abre sozinho em http://127.0.0.1:5000
"""
import os
import tempfile
import threading
import webbrowser
from datetime import datetime
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from flask import send_from_directory
from werkzeug.utils import secure_filename

import banco
from modelos import (
    ErroRegraNegocio, PERFIL_ADMINISTRADOR, PERFIL_PRODUCAO, PERFIL_COMERCIAL,
    SEM_AVARIA, COM_AVARIA, FOTO, VIDEO,
    STATUS_EM_ABERTO, STATUS_EM_ANDAMENTO, STATUS_CONCLUIDA, STATUS_PERDAS,
    FAVORAVEL, RECUSADA, PLATAFORMAS,
)

app = Flask(__name__)
app.secret_key = "sistema-devolucoes-uso-local"  # assina o cookie de sessão (sistema roda só no computador local)
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024  # permite enviar vídeos de até 100 MB (RNF-06)
PASTA_TEMPORARIA = os.path.join(tempfile.gettempdir(), "sistema-devolucoes")


# ---------------------------------------------------------------- acesso e menu por perfil (RNF-02 e RN-12)
def opcoes_do_perfil(usuario):
    """Cada perfil vê somente as funcionalidades que pode usar. Devolve {nome no menu: rota}."""
    opcoes = {}
    perfil = usuario.obterPerfil()
    if perfil == PERFIL_ADMINISTRADOR:
        opcoes["Gerenciar usuários"] = "usuarios"
        opcoes["Gerenciar produtos"] = "produtos"
    if perfil == PERFIL_PRODUCAO:
        opcoes["Cadastrar devolução"] = "cadastrar_devolucao"
    opcoes["Consultar devoluções"] = "consultar_devolucoes"
    return opcoes


def acesso(*perfis):
    """Exige login (RNF-01) e, se informado, um dos perfis permitidos (RNF-02)."""
    def decorador(funcao):
        @wraps(funcao)
        def verificar(*args, **kwargs):
            usuario = banco.buscar_usuario_por_id(session.get("usuario_id"))
            if usuario is None or not usuario.ativo:
                session.clear()
                return redirect(url_for("login"))
            if perfis and usuario.obterPerfil() not in perfis:
                flash("Seu perfil não tem acesso a essa funcionalidade.", "erro")
                return redirect(url_for("inicio"))
            g.usuario = usuario
            return funcao(*args, **kwargs)
        return verificar
    return decorador


@app.context_processor
def dados_do_menu():
    usuario = g.get("usuario")
    return {"usuario": usuario, "menu": opcoes_do_perfil(usuario) if usuario else {}}


# ---------------------------------------------------------------- leitura dos campos (RNF-03)
def ler_data(valor, obrigatorio=True):
    """Converte uma data no formato DD/MM/AAAA."""
    valor = (valor or "").strip()
    if not valor:
        if obrigatorio:
            raise ErroRegraNegocio("Informe a data no formato DD/MM/AAAA.")
        return None
    try:
        return datetime.strptime(valor, "%d/%m/%Y").date()
    except ValueError:
        raise ErroRegraNegocio(f"Data inválida: {valor}. Use o formato DD/MM/AAAA.")


def ler_quantidade(valor):
    valor = (valor or "").strip()
    if not valor.isdigit() or int(valor) <= 0:
        raise ErroRegraNegocio("A quantidade deve ser um número inteiro maior que zero.")
    return int(valor)


@app.template_filter("nome_arquivo")
def nome_arquivo(caminho):
    return os.path.basename(caminho)


@app.template_filter("codigo")
def codigo_devolucao(id):
    """Mostra o identificador único da devolução (RN-01) no formato DEV-0001."""
    return f"DEV-{id:04d}"


# ---------------------------------------------------------------- autenticação (RF-01)
@app.route("/")
def raiz():
    return redirect(url_for("inicio"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_informado = request.form.get("login", "").strip()
        usuario = banco.buscar_usuario_por_login(login_informado)
        if usuario is not None and usuario.autenticar(login_informado, request.form.get("senha", "")):
            session.clear()
            session["usuario_id"] = usuario.id
            return redirect(url_for("inicio"))
        flash("Login ou senha inválidos, ou usuário desativado.", "erro")
    return render_template("login.html")


@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("login"))


@app.route("/inicio")
@acesso()
def inicio():
    """Painel com a quantidade de devoluções em cada status (RF-11), visto por todos os perfis."""
    totais = banco.contar_devolucoes_por_status()
    painel = {status: totais.get(status, 0)
              for status in (STATUS_EM_ABERTO, STATUS_EM_ANDAMENTO, STATUS_CONCLUIDA, STATUS_PERDAS)}
    return render_template("inicio.html", painel=painel)


# ---------------------------------------------------------------- Administrador (RF-02 e RF-03)
@app.route("/usuarios", methods=["GET", "POST"])
@acesso(PERFIL_ADMINISTRADOR)
def usuarios():
    if request.method == "POST":
        acao = request.form.get("acao")
        try:
            if acao == "cadastrar":
                novo = g.usuario.cadastrarUsuario(request.form.get("nome"), request.form.get("login"),
                                                  request.form.get("senha"), request.form.get("perfil"))
                banco.salvar_usuario(novo)
                flash(f"Usuário {novo.login} cadastrado com sucesso.", "sucesso")
            else:
                usuario = banco.buscar_usuario_por_id(int(request.form.get("id", 0)))
                if usuario is None:
                    raise ErroRegraNegocio("Usuário não encontrado.")
                if acao == "alterar":
                    usuario.alterarDados(request.form.get("nome", "").strip() or usuario.nome,
                                         request.form.get("login", "").strip() or usuario.login)
                    banco.salvar_usuario(usuario)
                    flash("Usuário alterado com sucesso.", "sucesso")
                elif acao == "desativar":
                    if usuario.id == g.usuario.id:
                        raise ErroRegraNegocio("Você não pode desativar o próprio usuário.")
                    usuario.desativar()
                    banco.salvar_usuario(usuario)
                    flash(f"Usuário {usuario.login} desativado.", "sucesso")
            return redirect(url_for("usuarios"))
        except ErroRegraNegocio as erro:
            flash(str(erro), "erro")
    editando = request.args.get("editar", type=int)
    return render_template("usuarios.html", usuarios=banco.listar_usuarios(),
                           editando=banco.buscar_usuario_por_id(editando) if editando else None,
                           perfis=[PERFIL_ADMINISTRADOR, PERFIL_PRODUCAO, PERFIL_COMERCIAL])


@app.route("/produtos", methods=["GET", "POST"])
@acesso(PERFIL_ADMINISTRADOR)
def produtos():
    if request.method == "POST":
        acao = request.form.get("acao")
        try:
            if acao == "cadastrar":
                produto = g.usuario.cadastrarProduto(request.form.get("codigo"), request.form.get("sku"),
                                                     request.form.get("nome"), request.form.get("categoria"))
                banco.salvar_produto(produto)
                flash(f"Produto {produto.nome} cadastrado com sucesso.", "sucesso")
            else:
                produto = banco.buscar_produto_por_codigo(request.form.get("codigo", ""))
                if produto is None:
                    raise ErroRegraNegocio("Produto não encontrado.")
                if acao == "alterar":
                    produto.alterarDados(request.form.get("nome", "").strip() or produto.nome,
                                         request.form.get("categoria", "").strip() or produto.categoria)
                    banco.salvar_produto(produto)
                    flash("Produto alterado com sucesso.", "sucesso")
                elif acao == "desativar":
                    produto.desativar()
                    banco.salvar_produto(produto)
                    flash(f"Produto {produto.nome} desativado.", "sucesso")
            return redirect(url_for("produtos"))
        except ErroRegraNegocio as erro:
            flash(str(erro), "erro")
    editando = request.args.get("editar")
    return render_template("produtos.html", produtos=banco.listar_produtos(),
                           editando=banco.buscar_produto_por_codigo(editando) if editando else None)


# ---------------------------------------------------------------- Produção (RF-04, RF-05 e RF-06)
def montar_devolucao(usuario, dados):
    """Monta a devolução com os produtos já conferidos, aplicando as regras RN-02, RN-04 e RN-05."""
    devolucao = usuario.cadastrarDevolucao(dados["pedido"], dados.get("plataforma", ""), ler_data(dados["data"]))
    for item_dados in dados["itens"]:
        produto = banco.buscar_produto_por_codigo(item_dados["codigo"])
        item = devolucao.adicionarItem(produto, ler_quantidade(item_dados["quantidade"]))
        registrar_conferencia(item, item_dados)
    return devolucao


def registrar_conferencia(item, item_dados):
    """Registrar Conferência dos Produtos («include» de Cadastrar Devolução)."""
    if item_dados["situacao"] == COM_AVARIA:
        registrar_avaria(item, item_dados)
    else:
        item.classificar(item_dados["situacao"])


def registrar_avaria(item, item_dados):
    """Registrar Avaria e Evidências («extend»): só ocorre para produto Com Avaria (RN-05)."""
    item.classificar(COM_AVARIA, item_dados["descricao"])
    for tipo, caminho in item_dados["evidencias"]:
        item.adicionarEvidencia(tipo, caminho)
    if not item.possuiEvidenciasObrigatorias():
        raise ErroRegraNegocio("Produto Com Avaria precisa de descrição, pelo menos uma foto (JPG/PNG até 10 MB) "
                               "e pelo menos um vídeo (MP4 até 100 MB).")


def guardar_arquivos_enviados(campo, tipo):
    """Guarda numa pasta temporária os arquivos enviados pelo navegador até a confirmação do cadastro."""
    os.makedirs(PASTA_TEMPORARIA, exist_ok=True)
    evidencias = []
    for arquivo in request.files.getlist(campo):
        if arquivo and arquivo.filename:
            nome = datetime.now().strftime("%Y%m%d_%H%M%S_%f_") + secure_filename(arquivo.filename)
            caminho = os.path.join(PASTA_TEMPORARIA, nome)
            arquivo.save(caminho)
            evidencias.append([tipo, caminho])
    return evidencias


@app.route("/devolucoes/nova", methods=["GET", "POST"])
@acesso(PERFIL_PRODUCAO)
def cadastrar_devolucao():
    dados = session.get("nova_devolucao") or {"pedido": "", "plataforma": "", "data": "", "itens": []}
    if request.method == "POST":
        acao = request.form.get("acao")
        try:
            if acao == "cancelar":
                session.pop("nova_devolucao", None)
                flash("Cadastro cancelado.", "sucesso")
                return redirect(url_for("cadastrar_devolucao"))
            if acao == "adicionar":
                if not dados["itens"]:
                    dados["pedido"] = request.form.get("pedido", "")
                    dados["plataforma"] = request.form.get("plataforma", "")
                    dados["data"] = request.form.get("data", "")
                novo = {"codigo": request.form.get("produto", ""), "quantidade": request.form.get("quantidade", ""),
                        "situacao": request.form.get("situacao", ""), "descricao": request.form.get("descricao", ""),
                        "evidencias": guardar_arquivos_enviados("fotos", FOTO) + guardar_arquivos_enviados("videos", VIDEO)}
                if not novo["codigo"]:
                    raise ErroRegraNegocio("Selecione o produto.")
                montar_devolucao(g.usuario, {**dados, "itens": dados["itens"] + [novo]})  # valida antes de guardar
                dados["itens"].append(novo)
                session["nova_devolucao"] = dados
                flash("Produto adicionado à devolução.", "sucesso")
                return redirect(url_for("cadastrar_devolucao"))
            if acao == "confirmar":
                if not dados["itens"]:
                    raise ErroRegraNegocio("Adicione pelo menos um produto conferido à devolução.")
                devolucao = montar_devolucao(g.usuario, dados)
                if not devolucao.validarCadastro():
                    raise ErroRegraNegocio("Existem produtos sem classificação ou sem evidências.")
                for item in devolucao.itens:
                    for evidencia in item.evidencias:
                        evidencia.caminhoArquivo = banco.copiar_evidencia(evidencia.caminhoArquivo)
                devolucao.registrarHistorico(f"Devolução cadastrada com {len(devolucao.itens)} produto(s), "
                                     f"plataforma {devolucao.plataforma}", g.usuario)
                for item in devolucao.itens:
                    texto = f"Produto {item.produto.nome} classificado como {item.situacao}"
                    if item.situacao == COM_AVARIA:
                        texto += f" ({len(item.evidencias)} evidência(s) anexada(s))"
                    devolucao.registrarHistorico(texto, g.usuario)
                banco.salvar_devolucao(devolucao)
                session.pop("nova_devolucao", None)
                flash(f"Devolução nº {devolucao.id} cadastrada com status {devolucao.status}.", "sucesso")
                return redirect(url_for("cadastrar_devolucao"))
        except ErroRegraNegocio as erro:
            flash(str(erro), "erro")
    produtos_ativos = [p for p in banco.listar_produtos() if p.ativo]
    nomes = {p.codigo: p.nome for p in banco.listar_produtos()}
    return render_template("cadastrar_devolucao.html", dados=dados, produtos=produtos_ativos, nomes=nomes,
                           situacoes=[SEM_AVARIA, COM_AVARIA], com_avaria=COM_AVARIA,
                           plataformas=PLATAFORMAS)


# ---------------------------------------------------------------- consultas (RF-07 e RF-14)
@app.route("/devolucoes")
@acesso()
def consultar_devolucoes():
    filtros = {campo: request.args.get(campo, "").strip() for campo in ("pedido", "status", "produto", "inicio", "fim")}
    devolucoes = []
    try:
        devolucoes = banco.pesquisar_devolucoes(filtros["pedido"], filtros["status"], filtros["produto"],
                                                ler_data(filtros["inicio"], False), ler_data(filtros["fim"], False))
    except ErroRegraNegocio as erro:
        flash(str(erro), "erro")
    status = [STATUS_EM_ABERTO, STATUS_EM_ANDAMENTO, STATUS_CONCLUIDA, STATUS_PERDAS]
    totais = banco.contar_devolucoes_por_status()
    contagem = {s: totais.get(s, 0) for s in status}
    contagem[""] = sum(contagem.values())  # aba "Todas"
    return render_template("consultar_devolucoes.html", filtros=filtros, devolucoes=devolucoes, status=status,
                           contagem=contagem, com_avaria=COM_AVARIA,
                           pode_cadastrar=g.usuario.obterPerfil() == PERFIL_PRODUCAO)


@app.route("/devolucoes/<int:id>")
@acesso()
def detalhar_devolucao(id):
    """Tela de detalhes da devolução, aberta em uma nova aba a partir da consulta."""
    devolucao = banco.carregar_devolucao(id)
    if devolucao is None:
        flash("Devolução não encontrada.", "erro")
        return redirect(url_for("consultar_devolucoes"))
    return render_template("detalhes_devolucao.html", devolucao=devolucao,
                           ver_historico=request.args.get("historico") == "1",  # «extend» Consultar Histórico
                           com_avaria=COM_AVARIA, foto=FOTO, plataformas=PLATAFORMAS,
                           pode_tratar=g.usuario.obterPerfil() == PERFIL_COMERCIAL)


@app.route("/evidencias/<path:nome>")
@acesso()
def ver_evidencia(nome):
    """Permite consultar as fotos e os vídeos das devoluções (RNF-06)."""
    return send_from_directory(banco.PASTA_EVIDENCIAS, nome)


# ---------------------------------------------------------------- Comercial (RF-08 e RF-09)
def acao_do_comercial(id, acao):
    """Executa uma ação do Comercial sobre a devolução e volta para a tela de detalhes dela."""
    devolucao = banco.carregar_devolucao(id)
    if devolucao is None:
        flash("Devolução não encontrada.", "erro")
        return redirect(url_for("consultar_devolucoes"))
    try:
        mensagem = acao(devolucao)
        banco.salvar_devolucao(devolucao)
        flash(mensagem, "sucesso")
    except ErroRegraNegocio as erro:
        flash(str(erro), "erro")
    return redirect(url_for("detalhar_devolucao", id=id, _anchor="tratamento"))


@app.route("/devolucoes/<int:id>/conferir", methods=["POST"])
@acesso(PERFIL_COMERCIAL)
def conferir_devolucao(id):
    def conferir(devolucao):
        g.usuario.conferirDevolucao(devolucao)
        return "Conferência registrada."
    return acao_do_comercial(id, conferir)


@app.route("/devolucoes/<int:id>/encaminhamento", methods=["POST"])
@acesso(PERFIL_COMERCIAL)
def registrar_encaminhamento(id):
    def encaminhar(devolucao):
        posicao = request.form.get("item", "")
        if not posicao.isdigit() or not 1 <= int(posicao) <= len(devolucao.itens):
            raise ErroRegraNegocio("Produto inválido.")
        g.usuario.registrarEncaminhamento(devolucao.itens[int(posicao) - 1])
        return "Encaminhamento ao estoque registrado (o saldo de estoque não é alterado)."
    return acao_do_comercial(id, encaminhar)


# ---------------------------------------------------------------- Comercial (RF-10 e RF-12)
@app.route("/devolucoes/<int:id>/mediacao", methods=["POST"])
@acesso(PERFIL_COMERCIAL)
def gerenciar_mediacao(id):
    def registrar(devolucao):
        if devolucao.mediacao is None:
            g.usuario.abrirMediacao(devolucao, request.form.get("plataforma"), request.form.get("protocolo"))
            return f"Mediação registrada. Status da devolução: {devolucao.status}."
        resultado = request.form.get("resultado", "")
        if not resultado:
            raise ErroRegraNegocio("Selecione o resultado da mediação.")
        g.usuario.registrarResultadoMediacao(devolucao, resultado)
        return f"Resultado registrado. Status da devolução: {devolucao.status}."
    return acao_do_comercial(id, registrar)


@app.context_processor
def resultados_da_mediacao():
    return {"resultados": [FAVORAVEL, RECUSADA]}


@app.route("/devolucoes/<int:id>/finalizar", methods=["POST"])
@acesso(PERFIL_COMERCIAL)
def finalizar_devolucao(id):
    def finalizar(devolucao):
        g.usuario.finalizarDevolucao(devolucao)
        return "Devolução finalizada com status Concluída."
    return acao_do_comercial(id, finalizar)


def main():
    banco.inicializar()
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
