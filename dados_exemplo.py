"""Cadastra dados de exemplo para testar o sistema: usuários, produtos e devoluções Em Aberto.

Execute uma vez:  python dados_exemplo.py
Pode ser executado de novo: o que já existe não é cadastrado outra vez.
"""
import os
from datetime import date

import banco
from modelos import PERFIL_PRODUCAO, PERFIL_COMERCIAL, SEM_AVARIA, COM_AVARIA, FOTO, VIDEO, ErroRegraNegocio

PASTA_EXEMPLOS = os.path.join(banco.PASTA_PROJETO, "exemplos")
FOTO_EXEMPLO = os.path.join(PASTA_EXEMPLOS, "foto-avaria.jpg")
VIDEO_EXEMPLO = os.path.join(PASTA_EXEMPLOS, "video-avaria.mp4")

USUARIOS = [
    # nome, login, senha, perfil
    ("Usuário Produção", "producao", "producao123", PERFIL_PRODUCAO),
    ("Usuário Comercial", "comercial", "comercial123", PERFIL_COMERCIAL),
]

PRODUTOS = [
    # código, SKU, nome, categoria
    ("P001", "FON-001", "Fone Bluetooth", "Áudio"),
    ("P002", "CX-002", "Caixa de Som", "Áudio"),
    ("P003", "CAR-003", "Carregador USB-C", "Acessórios"),
    ("P004", "SMW-004", "Smartwatch", "Acessórios"),
    ("P005", "MOU-005", "Mouse sem fio", "Informática"),
    ("P006", "TEC-006", "Teclado mecânico", "Informática"),
]

DEVOLUCOES = [
    # número do pedido, plataforma, data de recebimento, [(código do produto, quantidade, situação, descrição da avaria)]
    ("48338436243", "Mercado Livre", date(2026, 11, 3), [
        ("P001", 2, SEM_AVARIA, ""),
    ]),
    ("2345678901", "Shopee", date(2026, 11, 4), [
        ("P002", 1, COM_AVARIA, "Caixa amassada na lateral e alto-falante sem som"),
        ("P003", 1, SEM_AVARIA, ""),
    ]),
    ("7712093344", "Amazon", date(2026, 11, 5), [
        ("P004", 1, COM_AVARIA, "Tela trincada no canto superior"),
    ]),
]


def cadastrar_usuarios(admin):
    for nome, login, senha, perfil in USUARIOS:
        if banco.buscar_usuario_por_login(login) is None:
            banco.salvar_usuario(admin.cadastrarUsuario(nome, login, senha, perfil))
            print(f"  Usuário {login} ({perfil}) cadastrado.")


def cadastrar_produtos(admin):
    for codigo, sku, nome, categoria in PRODUTOS:
        if banco.buscar_produto_por_codigo(codigo) is None:
            banco.salvar_produto(admin.cadastrarProduto(codigo, sku, nome, categoria))
            print(f"  Produto {codigo} - {nome} cadastrado.")


def cadastrar_devolucoes(producao):
    """Usa as mesmas classes e regras do cadastro feito pela tela (RN-02, RN-04 e RN-05)."""
    pedidos_existentes = {devolucao.numeroPedido for devolucao in banco.pesquisar_devolucoes()}
    for numero_pedido, plataforma, data_recebimento, itens in DEVOLUCOES:
        if numero_pedido in pedidos_existentes:
            continue
        devolucao = producao.cadastrarDevolucao(numero_pedido, plataforma, data_recebimento)
        for codigo, quantidade, situacao, descricao in itens:
            item = devolucao.adicionarItem(banco.buscar_produto_por_codigo(codigo), quantidade)
            item.classificar(situacao, descricao)
            if situacao == COM_AVARIA:
                for tipo, caminho in ((FOTO, FOTO_EXEMPLO), (VIDEO, VIDEO_EXEMPLO)):
                    evidencia = item.adicionarEvidencia(tipo, caminho)
                    evidencia.caminhoArquivo = banco.copiar_evidencia(caminho)
        if not devolucao.validarCadastro():
            raise ErroRegraNegocio(f"Devolução do pedido {numero_pedido} sem classificação ou sem evidências.")
        devolucao.registrarHistorico(f"Devolução cadastrada com {len(devolucao.itens)} produto(s), "
                                     f"plataforma {devolucao.plataforma}", producao)
        for item in devolucao.itens:
            texto = f"Produto {item.produto.nome} classificado como {item.situacao}"
            if item.situacao == COM_AVARIA:
                texto += f" ({len(item.evidencias)} evidência(s) anexada(s))"
            devolucao.registrarHistorico(texto, producao)
        banco.salvar_devolucao(devolucao)
        print(f"  Devolução nº {devolucao.id} (pedido {numero_pedido}, {plataforma}) cadastrada com status "
              f"{devolucao.status}.")


def main():
    banco.inicializar()
    admin = banco.buscar_usuario_por_login("admin")
    if admin is None or not admin.ativo:
        print("O usuário admin não está disponível. Nada foi cadastrado.")
        return
    print("Cadastrando dados de exemplo...")
    cadastrar_usuarios(admin)
    cadastrar_produtos(admin)
    producao = banco.buscar_usuario_por_login("producao")
    if producao is None or not producao.ativo or producao.obterPerfil() != PERFIL_PRODUCAO:
        print("O usuário producao não é um usuário ativo da Produção. As devoluções de exemplo não foram cadastradas.")
        return
    cadastrar_devolucoes(producao)
    print("Pronto. Logins: admin/admin123 (Administrador), producao/producao123 (Produção), comercial/comercial123 (Comercial).")


if __name__ == "__main__":
    main()
