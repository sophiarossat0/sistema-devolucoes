"""Sistema de Gestão e Controle do Processo de Devoluções - versão web.

Execute com:  python main.py
O navegador abre sozinho em http://127.0.0.1:5000
"""
import threading
import webbrowser
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

import banco
from modelos import (
    ErroRegraNegocio, PERFIL_ADMINISTRADOR, PERFIL_PRODUCAO, PERFIL_COMERCIAL,
)

app = Flask(__name__)
app.secret_key = "sistema-devolucoes-uso-local"  # assina o cookie de sessão (sistema roda só no computador local)


# ---------------------------------------------------------------- acesso e menu por perfil (RNF-02 e RN-12)
def opcoes_do_perfil(usuario):
    """Cada perfil vê somente as funcionalidades que pode usar. Devolve {nome no menu: rota}."""
    opcoes = {}
    perfil = usuario.obterPerfil()
    if perfil == PERFIL_ADMINISTRADOR:
        opcoes["Gerenciar usuários"] = "usuarios"
        opcoes["Gerenciar produtos"] = "produtos"
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
    return render_template("inicio.html")


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


def main():
    banco.inicializar()
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
