# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app locally
streamlit run app.py

# Install dependencies
pip install -r requirements.txt

# Build Docker image
docker build -t wbs-hub:latest .

# Run with Docker (development)
docker compose up

# Run in production (Docker Swarm)
IMAGE=ghcr.io/<owner>/wbs-hub:latest docker stack deploy -c docker-compose.prod.yml wbs
```

## Architecture

This is a Streamlit application (**WBS Hub**) that generates Work Breakdown Structure tasks and sends them to Monday.com via Make (formerly Integromat) webhooks. It replaces a legacy Monday forms + n8n + Make workflow.

### Multi-mode wizard (3 operation modes)

The wizard supports three selectable modes in the sidebar, with independent flows:

1. **`🔧 Setup Completo`** (`completo`): Original full flow — create pendência on Monday, then add generic tasks and WBS.
   - Steps: Step 1 (create pendência) → Step 2 (generic tasks) → Step 3 (WBS) → Step 4 (send).
   - Sends two webhooks: `webhook_pendencia` (POST) then `webhook_tasks` (POST with `pending_id`).

2. **`📅 Genéricas Avulsas`** (`genericas`): Standalone generic tasks without creating a pendência.
   - Steps: Step 1 (select project, no pendência form) → Step 2 (generic tasks) → Step 4 (send).
   - Sends one webhook: `webhook_tasks` (POST, no `pending_id`).

3. **`📋 WBS p/ Pend. Existente`** (`wbs_existente`): Add WBS to an existing Monday pendência.
   - Steps: Step 0 (fetch pendência list via GET) → Step 3 (WBS) → Step 4 (send).
   - Sends one webhook: `webhook_tasks` (POST with `pending_id` from Monday, `tasks_genericas: []`).

Mode is stored in `st.session_state.modo`; changing mode resets the wizard.

### Key files

- `app.py` — entire UI and wizard logic; new functions: `render_step0_buscar_pendencia`, `render_step1_avulsa`. Mode dispatch in `main()`.
- `config.yaml` — webhook endpoints (`webhook_get_pendencias`, `webhook_pendencia`, `webhook_tasks`), timeouts, Brazilian holidays, UI settings.
- `data/projetos.json` — project list shown in the Step 1 dropdown.
- `db/planejamentos.db` — SQLite database auto-created; stores every sent planning payload and generic tasks.

### `utils/` module

| File | Purpose |
|------|---------|
| `wbs_logic.py` | `gerar_tarefas_expandidas` (percentual logic), `gerar_tarefas_multiplicador` (item × fixed-task expansion), validators |
| `weekly_logic.py` | `distribuir_tasks_diarias_por_colaboradores` (daily tasks by business day), `formatar_nome_task_generica` (task name format) |
| `db.py` | `init_db()` / `salvar_planejamento()` — SQLite persistence via `db/planejamentos.db` |

### Template system

Templates live in `templates/*.yaml`. Two template types controlled by `tipo_logica`:

- **`percentual`** (default): each task has `dias_default`; days expand to progressive percentages (1d→100%, 2d→50%/100%, etc.). Fields: `nome`, `wbs_type`, `tarefas[{id, nome, dias_default}]`.
- **`multiplicador`**: user selects items from a category; each item × fixed task list. Used by `wbs_aquisicao.yaml`. Fields: `categorias[{id, nome, itens[], tarefas[]}]`.

A new `.yaml` file in `templates/` is auto-detected on app restart.

### Webhook payloads

**`webhook_get_pendencias`** (GET) — fetches pending items from Monday. Make returns:
```json
[
  {
    "body": [
      {
        "id": "10979972723",
        "name": "Teste Aceitação do Equipamento",
        "mappable_column_values": {
          "text_mkzd1dek": "160",
          "board_relation_mkzdy9qa": { "text": "01058 - Nome Projeto - Cliente" }
        }
      }
    ]
  }
]
```
Field mapping: `id` → pending_id · `name` → nome da pendência · `text_mkzd1dek` → subconjunto · `board_relation_mkzdy9qa.text` → projeto (OS = primeiro segmento antes de `" - "`).

**`webhook_pendencia`** (POST, modo `completo` only):
```json
{ "nome_pendencia": "...", "os": "01058", "subconjunto": "...", "prazo_limite": "2025-12-31", "projeto": "...", "projeto_id": 123 }
```
Must respond with `{ "pending_id": "<id>" }`.

**`webhook_tasks`** (POST) — payload varies by mode:

- **`completo`**: `{ "pending_id": "...", "os": "...", "subconjunto": "...", "projeto": "...", "projeto_id": ..., "tasks_genericas": [...], "wbs": [...] }`
- **`genericas`**: `{ "os": "...", "subconjunto": "...", "projeto": "...", "projeto_id": ..., "tasks_genericas": [...], "wbs": [] }`
- **`wbs_existente`**: `{ "pending_id": "...", "os": "...", "subconjunto": "...", "tasks_genericas": [], "wbs": [...] }`

### Production deployment

Deployed as a Docker Swarm service behind Traefik at `wbs.arvsystems.cloud`. The `wbs-data` volume persists `data/projetos.json`. The Docker entrypoint seeds the volume from bundled `data-template/` if empty.
