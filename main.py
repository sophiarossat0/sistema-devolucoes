"""Sistema de Gestão e Controle do Processo de Devoluções - versão web.

Execute com:  python main.py
O navegador abre sozinho em http://127.0.0.1:5000
"""
import threading
import webbrowser
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

import banco

app = Flask(__name__)
app.secret_key = "sistema-devolucoes-uso-local"  # assina o cookie de sessão (sistema roda só no computador local)


# ---------------------------------------------------------------- acesso e menu por perfil (RNF-02 e RN-12)
def opcoes_do_perfil(usuario):
    """Cada perfil vê somente as funcionalidades que pode usar. Devolve {nome no menu: rota}."""
    opcoes = {}
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


def main():
    banco.inicializar()
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
