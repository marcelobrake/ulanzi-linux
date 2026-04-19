# AGENTS.md

Guia operacional para qualquer agente de IA, copiloto ou ferramenta de desenvolvimento assistido que trabalhe neste repositório. Este arquivo é a fonte de verdade para automação orientada por IA.

## Objetivo do projeto

Este repositório implementa um cliente Linux não oficial para o Ulanzi Stream Controller D200. O projeto fala com o hardware via USB HID, mantém um daemon para processar eventos e ações, oferece CLI para operação manual e expõe um editor web local para editar o `deck.yaml` sem depender do software proprietário.

## Mapa rápido do código

- `src/ulanzi_linux/domain/`
  - Regras puras de negócio e contratos.
  - Contém `DeckDevice`, `DeckSpec`, eventos, enums de protocolo e modelos de configuração.
  - Não deve depender de infraestrutura.
- `src/ulanzi_linux/application/`
  - Casos de uso e orquestração.
  - Pontos principais: `deck_service.py`, `daemon.py`, `config_loader.py`, `config_watcher.py`, `action_runner.py`.
- `src/ulanzi_linux/infrastructure/`
  - Implementações concretas do hardware e empacotamento do protocolo.
  - Pontos principais: `hid_transport.py`, `ulanzi_d200.py`, `packet.py`, `zip_builder.py`, `system_metrics.py`.
- `src/ulanzi_linux/interface/`
  - Superfícies de entrada do usuário.
  - CLI em `cli.py`.
  - Editor web FastAPI em `web/app.py` e assets estáticos em `web/static/`.
- `src/ulanzi_linux/observability/`
  - Logging estruturado e hooks de telemetria.
- `tests/`
  - Cobertura por comportamento: protocolo, daemon, hot reload, paginação, web app, reconexão, small window.
- `docs/`
  - Documentação humana complementar. Consulte antes de alterar comportamento público.

## Fluxo de execução em produção

1. O usuário mantém a configuração em `~/.config/ulanzi/deck.yaml`.
2. O daemon (`ulanzi-linux daemon`) lê o YAML, sincroniza o layout no dispositivo e processa eventos de botão.
3. O `ConfigWatcher` recarrega alterações do arquivo sem reinício quando o watch está ativo.
4. O editor web (`ulanzi-linux gui`) apenas lê, valida e grava o YAML. Ele não fala com o hardware.
5. O dispositivo D200 é controlado por `UlanziD200Device`, que serializa payloads HID, restaura estado após reconexão e mantém a small window atualizada.

## Fontes de verdade por assunto

- Configuração YAML: `src/ulanzi_linux/application/config_loader.py`
- Modelo de domínio da configuração: `src/ulanzi_linux/domain/button_config.py`
- CLI pública: `src/ulanzi_linux/interface/cli.py`
- API web: `src/ulanzi_linux/interface/web/app.py`
- Protocolo HID do D200: `src/ulanzi_linux/infrastructure/ulanzi_d200.py` e `src/ulanzi_linux/infrastructure/packet.py`
- Empacotamento visual dos botões: `src/ulanzi_linux/infrastructure/zip_builder.py`
- Versão publicada do pacote: `pyproject.toml` e `src/ulanzi_linux/__init__.py`
- Histórico de releases: `CHANGELOG.md`

## Regras para agentes de IA

1. Faça mudanças pequenas e coerentes com a arquitetura existente.
2. Não pule a validação do `config_loader` ao alterar schema YAML.
3. Não acople a camada `interface` diretamente na `infrastructure` se já existir abstração na `application` ou `domain`.
4. Ao alterar a GUI web, trate backend e frontend como parte do mesmo contrato.
5. Não edite manualmente arquivos gerados em `src/ulanzi_linux.egg-info/`; eles são regenerados na instalação.
6. Preserve compatibilidade com Linux e Python 3.11+.

## Fluxos comuns de mudança

### Mudanças em YAML/configuração

- Atualize o parser em `config_loader.py`.
- Ajuste o modelo em `domain/button_config.py` se o schema mudar.
- Atualize a documentação em `docs/configuration.md`.
- Adicione ou ajuste testes em `tests/test_web_app.py`, `tests/test_hot_reload.py` e testes específicos da feature.

### Mudanças no daemon ou na small window

- Priorize `src/ulanzi_linux/application/daemon.py` para a regra de alto nível.
- Atualize `src/ulanzi_linux/infrastructure/ulanzi_d200.py` apenas para detalhes de transporte, payload ou recuperação de estado.
- Cubra o comportamento em `tests/test_small_window.py`, `tests/test_reconnect.py` e, se aplicável, `tests/test_deck_service.py`.

### Mudanças na interface web

- Backend: `src/ulanzi_linux/interface/web/app.py` e `models.py`.
- Frontend: `src/ulanzi_linux/interface/web/static/index.html`, `app.js`, `app.css`.
- Valide o contrato HTTP em `tests/test_web_app.py`.
- Importante: a GUI servida ao usuário vem do pacote instalado. Depois de mudar `src/ulanzi_linux/interface/web/*`, reinstale com `python3 -m pip install --user '.[web]'` e reinicie `ulanzi-linux gui` para refletir `/api/editor` e assets estáticos atualizados.

## Comandos úteis para desenvolvimento

Ambiente local completo:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"
```

Testes:

```bash
PYTHONPATH=src pytest -q
PYTHONPATH=src pytest tests/test_web_app.py -q
PYTHONPATH=src pytest tests/test_small_window.py tests/test_reconnect.py -q
```

Lint e tipos:

```bash
ruff check .
mypy src
```

Execução local:

```bash
ulanzi-linux devices
ulanzi-linux push-config ~/.config/ulanzi/deck.yaml
ulanzi-linux daemon ~/.config/ulanzi/deck.yaml
ulanzi-linux gui ~/.config/ulanzi/deck.yaml
```

## Política obrigatória de versionamento e changelog

Toda mudança aceita no repositório deve incrementar a versão atual e registrar a alteração em `CHANGELOG.md`. Não reutilize a mesma versão para múltiplos conjuntos de mudanças.

### Como escolher o incremento

Use Semantic Versioning com esta leitura operacional:

- `major` = primeiro dígito.
  - Use quando houver quebra de compatibilidade, remoção de comportamento público, mudança de schema incompatível, mudança de API/CLI/HTTP que exija adaptação do usuário ou refatoração com breaking change.
- `mid` = dígito do meio, equivalente ao `minor` do SemVer.
  - Use para nova feature compatível, novo endpoint, novo campo opcional, nova ação, novo comando, melhoria funcional visível ao usuário sem quebra.
- `minor` = último dígito, equivalente a `patch` no SemVer.
  - Use para correção de bug, ajuste de documentação, correção de UX, melhoria interna compatível, teste adicional ou refino operacional sem quebra.

### Regra de decisão para agentes

O agente de IA deve classificar a mudança antes de finalizar o trabalho:

- Nova feature compatível: incremente o dígito do meio.
- Correção compatível: incremente o último dígito.
- Refatoração com quebra, breaking change ou mudança incompatível: incremente o primeiro dígito.

Se houver dúvida entre dois níveis, use o mais alto.

### Arquivos que devem ser atualizados em todo bump de versão

1. `pyproject.toml`
2. `src/ulanzi_linux/__init__.py`
3. `CHANGELOG.md`

Não edite `src/ulanzi_linux.egg-info/*` manualmente. Esse conteúdo será regenerado pela instalação.

### Estrutura esperada no changelog

- Adicione uma nova seção no topo com a nova versão e a data no formato `YYYY-MM-DD`.
- Use categorias compatíveis com Keep a Changelog, conforme fizer sentido: `Added`, `Changed`, `Fixed`, `Removed`.
- Descreva comportamento visível, impacto operacional e eventuais migrações.
- Se houver breaking change, deixe isso explícito na nova entrada.

Exemplo:

```md
## [0.2.0] — 2026-04-18

### Added

- Novo editor visual com reset do deck.

### Fixed

- Reconexão automática após reinício do dispositivo.
```

## Checklist mínimo antes de encerrar uma tarefa

1. Confirmar quais arquivos são fonte de verdade para a mudança.
2. Atualizar testes ou documentação afetada.
3. Escolher e aplicar o bump de versão.
4. Registrar a release no `CHANGELOG.md`.
5. Rodar validação proporcional ao escopo.
6. Se a GUI web mudou, reinstalar o pacote e reiniciar a GUI antes de validar manualmente.

## Documentação complementar

- `README.md` — visão geral do projeto.
- `docs/architecture.md` — dependências entre camadas.
- `docs/operations.md` — instalação, operação e troubleshooting.
- `docs/configuration.md` — schema do `deck.yaml`.
- `docs/web-ui.md` — editor web e API HTTP.
- `docs/protocol.md` — notas do protocolo HID.

Se uma ferramenta suportar `CLAUDE.md`, `AGENTS.md`, `COPILOT.md` ou arquivo equivalente, este conteúdo deve ser tratado como a instrução principal do repositório.
