# Sistema de Gestão e Controle do Processo de Devoluções

**Integrante:** Sophia Rossato
**Disciplina:** Análise e Projeto de Sistemas

Sistema para registrar e acompanhar o processo interno de devoluções da empresa, desde o recebimento e a conferência dos produtos pelo setor de Produção até o tratamento e o encerramento pelo setor Comercial.

## Funcionalidades implementadas

- Login com senha criptografada e menu de acordo com o perfil (Administrador, Produção ou Comercial)
- Gerenciamento de usuários e produtos (Administrador)
- Cadastro de devolução com conferência dos produtos, registro de avaria e anexação de fotos e vídeos (Produção)
- Conferência da devolução, encaminhamento ao estoque, mediação e finalização (Comercial), todas na tela de detalhes da devolução
- Consulta de devoluções com filtros e consulta do histórico de ações
- Painel na tela de Início, para todos os perfis, com a quantidade de devoluções em cada status (Em Aberto, Em Andamento, Concluída e Perdas)

## Como executar

Requisitos: Python 3.10 ou superior e a biblioteca Flask.

```bash
pip install -r requirements.txt
python main.py
```

O sistema abre sozinho no navegador, no endereço http://127.0.0.1:5000. Para parar, aperte Ctrl+C no terminal.

No primeiro acesso use o usuário **admin** com a senha **admin123**. Depois cadastre os usuários da Produção e do Comercial e os produtos.

### Dados de exemplo (opcional)

Para testar sem precisar cadastrar nada, rode uma vez:

```bash
python dados_exemplo.py
```

O script cadastra os usuários abaixo, 6 produtos e 3 devoluções com status Em Aberto (uma só com produto Sem Avaria, uma com produto Com Avaria e Sem Avaria, e uma só com produto Com Avaria, com foto e vídeo de exemplo). Pode ser executado de novo sem duplicar nada.

| Perfil | Login | Senha |
| --- | --- | --- |
| Administrador | admin | admin123 |
| Produção | producao | producao123 |
| Comercial | comercial | comercial123 |

## Estrutura do projeto

| Arquivo | Conteúdo |
| --- | --- |
| `main.py` | Páginas do sistema web (rotas do Flask) e controle de acesso por perfil |
| `templates/` e `static/` | Telas em HTML e estilo visual (CSS) |
| `modelos.py` | Classes do diagrama de classes e regras de negócio |
| `banco.py` | Gravação e leitura dos dados no banco SQLite |
| `requirements.txt` | Biblioteca necessária (Flask) |
| `docs/` | Diagramas de casos de uso e de classes (Draw.io) |
| `dados_exemplo.py` e `exemplos/` | Script de dados de exemplo e a foto e o vídeo usados nas devoluções de exemplo |

O banco de dados (`devolucoes.db`) e a pasta `evidencias/` são criados automaticamente na primeira execução.
