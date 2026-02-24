from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests
import streamlit as st
import yaml

from utils import (
    gerar_tarefas_expandidas,
    gerar_tarefas_multiplicador,
    validar_multiplicador,
    validar_selecao,
)
from utils.db import init_db, salvar_planejamento
try:
    from utils.weekly_logic import distribuir_tasks_diarias_por_colaboradores, formatar_nome_task_generica
except ImportError:
    # Fallback para quando o Streamlit está com reload/caches inconsistentes.
    from utils.weekly_logic import dias_uteis_no_intervalo, formatar_nome_task_generica

    def distribuir_tasks_diarias_por_colaboradores(
        data_inicio: date,
        prazo_limite: date,
        colaboradores: int,
        horas_por_colaborador: float = 9.0,
    ) -> list[dict]:
        if colaboradores <= 0:
            return []

        dias = dias_uteis_no_intervalo(data_inicio, prazo_limite)
        if not dias:
            return []

        total_tasks = len(dias) * int(colaboradores)
        pct_base = round(100.0 / total_tasks, 1)
        percentuais = [pct_base for _ in range(total_tasks)]
        if percentuais:
            percentuais[-1] = round(100.0 - round(sum(percentuais[:-1]), 1), 1)

        out: list[dict] = []
        idx = 0
        for d in dias:
            for dono_idx in range(1, int(colaboradores) + 1):
                out.append(
                    {
                        "data": d.isoformat(),
                        "horas_previstas": float(horas_por_colaborador),
                        "percentual_pendencia": float(percentuais[idx]),
                        "status": "planejada",
                        "ajustada_feriado": False,
                        "dono_idx": int(dono_idx),
                        "dono_total": int(colaboradores),
                    }
                )
                idx += 1
        return out


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
TEMPLATES_DIR = BASE_DIR / "templates"
PROJETOS_PATH = BASE_DIR / "data" / "projetos.json"


def carregar_config() -> dict[str, Any]:
    """Carrega configurações gerais do `config.yaml`."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def carregar_templates() -> dict[str, dict[str, Any]]:
    """Carrega todos os templates YAML da pasta `templates/`."""
    templates: dict[str, dict[str, Any]] = {}
    for template_file in TEMPLATES_DIR.glob("*.yaml"):
        with open(template_file, "r", encoding="utf-8") as f:
            template = yaml.safe_load(f) or {}
        wbs_type = template.get("wbs_type")
        if wbs_type:
            templates[str(wbs_type)] = template
    return templates


def carregar_projetos() -> list[dict[str, Any]]:
    """Carrega projetos a partir de `data/projetos.json`."""
    if not PROJETOS_PATH.exists():
        return []
    with open(PROJETOS_PATH, "r", encoding="utf-8") as f:
        dados = json.load(f) or {}
    projetos = dados.get("projetos", [])
    return list(projetos) if isinstance(projetos, list) else []


def _parse_feriados(config: dict[str, Any]) -> list[date]:
    feriados_raw = config.get("feriados_br", []) or []
    feriados: list[date] = []
    for d in feriados_raw:
        try:
            feriados.append(datetime.strptime(str(d), "%Y-%m-%d").date())
        except ValueError:
            continue
    return feriados


def _init_state() -> None:
    if "step" not in st.session_state:
        st.session_state.step = 1
    if "pendencia" not in st.session_state:
        st.session_state.pendencia = {}
    if "tasks_genericas_preview" not in st.session_state:
        st.session_state.tasks_genericas_preview = []
    if "tasks_genericas" not in st.session_state:
        st.session_state.tasks_genericas = []
    if "wbs" not in st.session_state:
        st.session_state.wbs = []
    if "pending_id" not in st.session_state:
        st.session_state.pending_id = None
    if "codigo_wbs" not in st.session_state:
        st.session_state.codigo_wbs = ""


def _go_to(step: int) -> None:
    st.session_state.step = step
    st.rerun()


def _sidebar_progresso() -> None:
    steps = ["1. Pendência", "2. Carga Semanal", "3. WBS", "4. Confirmar"]
    step = int(st.session_state.step)
    st.sidebar.progress((step - 1) / (len(steps) - 1))
    for i, label in enumerate(steps, 1):
        icon = "✅" if i < step else ("▶️" if i == step else "⬜")
        st.sidebar.write(f"{icon} {label}")


def render_step1(projetos: list[dict[str, Any]]) -> None:
    st.subheader("1) Registrar Pendência")

    hoje = date.today()
    pendencia_atual: dict[str, Any] = dict(st.session_state.pendencia or {})

    projeto_opcoes: dict[str, dict[str, Any]] = {}
    for p in projetos:
        label = f"{p.get('codigo', '?')} - {p.get('nome', 'Sem nome')} ({p.get('cliente', '?')})"
        projeto_opcoes[label] = p

    with st.form("form_step1", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            if projeto_opcoes:
                labels = list(projeto_opcoes.keys())
                label_default = pendencia_atual.get("projeto") if pendencia_atual.get("projeto") in labels else labels[0]
                projeto_label = st.selectbox("Projeto", options=labels, index=labels.index(label_default))
                projeto_sel = projeto_opcoes[projeto_label]

                os_val = str(projeto_sel.get("codigo", "") or "").strip()
                projeto_id = projeto_sel.get("id")
                projeto_nome = str(projeto_sel.get("nome", "") or "")
                projeto_cliente = str(projeto_sel.get("cliente", "") or "")

                # Mantém o valor exibido sempre sincronizado com o projeto selecionado.
                st.session_state["os_projeto_display"] = os_val
                st.text_input("OS (do projeto)", key="os_projeto_display", disabled=True)
            else:
                st.warning("Nenhum projeto encontrado em `data/projetos.json`.")
                projeto_label = None
                projeto_id = None
                projeto_nome = None
                projeto_cliente = None
                os_val = st.text_input("OS", value=str(pendencia_atual.get("os", "")), placeholder="Ex: 01058")

            subconjunto_val = st.text_input(
                "Subconjunto", value=str(pendencia_atual.get("subconjunto", "")), placeholder="Ex: Estação 100"
            )
            nome_pendencia_val = st.text_input(
                "Nome da pendência",
                value=str(pendencia_atual.get("nome_pendencia", "")),
                placeholder="Ex: Montagem geral da estação 100",
                help="Nome/título do item de pendência que será criado no Monday.",
            )
            prazo_val = st.date_input(
                "Prazo limite",
                value=datetime.strptime(pendencia_atual["prazo_limite"], "%Y-%m-%d").date()
                if pendencia_atual.get("prazo_limite")
                else hoje,
                min_value=hoje,
            )

        with col2:
            descricao_val = st.text_area("Descrição (opcional)", value=str(pendencia_atual.get("descricao", "")), height=120)

        confirmar = st.form_submit_button("Confirmar e avançar", type="primary")

    if confirmar:
        os_val = (os_val or "").strip()
        subconjunto_val = (subconjunto_val or "").strip()
        nome_pendencia_val = (nome_pendencia_val or "").strip()

        erros: list[str] = []
        if not os_val:
            erros.append("OS é obrigatório.")
        if not subconjunto_val:
            erros.append("Subconjunto é obrigatório.")
        if not nome_pendencia_val:
            erros.append("Nome da pendência é obrigatório.")
        if prazo_val < hoje:
            erros.append("Prazo limite deve ser maior ou igual a hoje.")

        if erros:
            for e in erros:
                st.error(e)
            return

        st.session_state.pendencia = {
            "os": os_val,
            "subconjunto": subconjunto_val,
            "nome_pendencia": nome_pendencia_val,
            "descricao": (descricao_val or "").strip(),
            "prazo_limite": prazo_val.isoformat(),
            "projeto": projeto_label,
            "projeto_id": projeto_id,
            "projeto_nome": projeto_nome,
            "projeto_cliente": projeto_cliente,
        }
        _go_to(2)


def render_step2(feriados: list[date]) -> None:
    st.subheader("2) Tasks Genéricas (dias úteis)")

    pendencia = st.session_state.pendencia or {}
    if not pendencia.get("prazo_limite"):
        st.error("Pendência não preenchida. Volte ao Step 1.")
        if st.button("← Voltar para Step 1"):
            _go_to(1)
        return

    prazo_limite = datetime.strptime(pendencia["prazo_limite"], "%Y-%m-%d").date()
    hoje = date.today()

    criar_genericas = st.checkbox(
        "Criar tasks genéricas",
        value=bool(st.session_state.get("criar_genericas", True)),
        help="Alguns times não usam tasks genéricas. Desmarque para pular esta etapa.",
    )
    st.session_state["criar_genericas"] = bool(criar_genericas)

    if not criar_genericas:
        st.session_state.tasks_genericas_preview = []
        st.session_state.tasks_genericas = []
        st.info("Tasks genéricas desativadas. Você pode avançar para seleção de WBS.")

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        data_inicio = st.date_input("Data de início", value=hoje)
    with col2:
        if criar_genericas:
            colaboradores = st.number_input("Colaboradores", min_value=1, step=1, value=1)
            st.caption("Padrão: 9h/dia por colaborador (replica as tasks por colaborador).")
        else:
            colaboradores = 1

    if criar_genericas and st.button("Distribuir dias úteis", type="primary"):
        if data_inicio > prazo_limite:
            st.session_state.tasks_genericas_preview = []
            st.session_state.tasks_genericas = []
            st.error("Data de início não pode ser maior que o prazo limite.")
            return

        # Feriados não filtram as tasks (se cair em dia útil, cria normalmente).
        _ = feriados
        preview = distribuir_tasks_diarias_por_colaboradores(
            data_inicio=data_inicio, prazo_limite=prazo_limite, colaboradores=int(colaboradores), horas_por_colaborador=9.0
        )
        if not preview:
            st.session_state.tasks_genericas_preview = []
            st.session_state.tasks_genericas = []
            st.warning("Não há dias úteis no intervalo para gerar tasks.")
        else:
            os_val = pendencia.get("os", "")
            subconjunto_val = pendencia.get("subconjunto", "")

            rows_preview: list[dict[str, Any]] = []
            rows_payload: list[dict[str, Any]] = []
            for item in preview:
                data_task = datetime.strptime(item["data"], "%Y-%m-%d").date()
                nome = formatar_nome_task_generica(
                    os=os_val, subconjunto=subconjunto_val, percentual=float(item["percentual_pendencia"]), data=data_task
                )
                dono_idx = int(item.get("dono_idx", 1))
                nome = f"{nome} | dono {dono_idx}"
                rows_preview.append({**item, "nome": nome})
                rows_payload.append(
                    {
                        "nome": nome,
                        "data": item["data"],
                        "horas_previstas": item["horas_previstas"],
                        "percentual_pendencia": item["percentual_pendencia"],
                        "status": item["status"],
                    }
                )

            st.session_state.tasks_genericas_preview = rows_preview
            st.session_state.tasks_genericas = rows_payload

    preview = st.session_state.tasks_genericas_preview or []
    if criar_genericas and preview:
        st.caption("Preview")
        tabela = []
        for t in preview:
            d = datetime.strptime(t["data"], "%Y-%m-%d").date()
            obs = ""
            tabela.append(
                {
                    "Nome da Task": t["nome"],
                    "Data": d.strftime("%a %d/%m/%Y"),
                    "Horas": t["horas_previstas"],
                    "% Pendência": t["percentual_pendencia"],
                    "Obs": obs,
                }
            )
        st.dataframe(tabela, use_container_width=True, hide_index=True)

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("← Voltar"):
            _go_to(1)
    with col_btn2:
        pode_avancar = (not criar_genericas) or bool(st.session_state.tasks_genericas)
        if st.button("Confirmar e avançar", type="primary", disabled=not pode_avancar):
            _go_to(3)
        if not pode_avancar:
            st.info("Gere ao menos 1 dia útil para avançar.")


def render_step3(templates: dict[str, dict[str, Any]]) -> None:
    st.subheader("3) Selecionar WBS e Tasks")

    pendencia = st.session_state.pendencia or {}
    if not pendencia.get("os") or not pendencia.get("subconjunto"):
        st.error("Pendência não preenchida. Volte ao Step 1.")
        if st.button("← Voltar para Step 1"):
            _go_to(1)
        return

    codigo_wbs = st.text_input(
        "Código do WBS (opcional)",
        value=str(st.session_state.codigo_wbs or ""),
        help="Mantém o padrão atual do WBS Hub (prefixo no nome das tasks WBS).",
    )
    st.session_state.codigo_wbs = codigo_wbs

    st.caption("Marque os templates que deseja incluir e refine a seleção dentro de cada um.")

    for wbs_type, template in sorted(templates.items(), key=lambda x: str(x[1].get("nome", x[0]))):
        nome_template = str(template.get("nome", wbs_type))
        tipo_logica = str(template.get("tipo_logica", "percentual"))

        inclui_key = f"inclui_{wbs_type}"
        if inclui_key not in st.session_state:
            st.session_state[inclui_key] = False

        with st.expander(f"{nome_template}  ·  tipo: {tipo_logica}", expanded=bool(st.session_state[inclui_key])):
            inclui = st.checkbox("Incluir este WBS", key=inclui_key)
            if not inclui:
                continue

            if tipo_logica == "multiplicador":
                categorias = template.get("categorias", []) or []
                if not categorias:
                    st.warning("Template sem categorias.")
                    continue

                cat_map = {str(c.get("nome", c.get("id", ""))): c for c in categorias}
                cat_labels = list(cat_map.keys())
                cat_key = f"cat_{wbs_type}"
                if cat_key not in st.session_state:
                    st.session_state[cat_key] = cat_labels[0]

                cat_nome = st.selectbox("Categoria", options=cat_labels, key=cat_key)
                categoria = cat_map[cat_nome]

                itens_categoria = list(categoria.get("itens", []) or [])
                tarefas_fixas = list(categoria.get("tarefas", []) or [])

                st.caption(
                    f"ℹ️ {len(itens_categoria)} itens · cada item selecionado gerará {len(tarefas_fixas)} tarefas"
                )

                col_sel1, col_sel2, _ = st.columns([1, 1, 4])
                with col_sel1:
                    if st.button("Selecionar todos", key=f"sel_all_{wbs_type}_{categoria.get('id','cat')}"):
                        for i in range(len(itens_categoria)):
                            st.session_state[f"item_{wbs_type}_{categoria.get('id','cat')}_{i}"] = True
                        st.rerun()
                with col_sel2:
                    if st.button("Limpar", key=f"clear_{wbs_type}_{categoria.get('id','cat')}"):
                        for i in range(len(itens_categoria)):
                            st.session_state[f"item_{wbs_type}_{categoria.get('id','cat')}_{i}"] = False
                        st.rerun()

                col1, col2 = st.columns(2)
                metade = (len(itens_categoria) + 1) // 2
                for i, item in enumerate(itens_categoria):
                    col = col1 if i < metade else col2
                    with col:
                        st.checkbox(item, key=f"item_{wbs_type}_{categoria.get('id','cat')}_{i}")

            else:
                tarefas = template.get("tarefas", []) or []
                if not tarefas:
                    st.warning("Template sem tarefas.")
                    continue

                col_sel1, col_sel2, _ = st.columns([1, 1, 4])
                with col_sel1:
                    if st.button("Selecionar todas", key=f"sel_all_{wbs_type}"):
                        for tarefa in tarefas:
                            st.session_state[f"check_{wbs_type}_{tarefa['id']}"] = True
                        st.rerun()
                with col_sel2:
                    if st.button("Limpar seleção", key=f"clear_{wbs_type}"):
                        for tarefa in tarefas:
                            st.session_state[f"check_{wbs_type}_{tarefa['id']}"] = False
                        st.rerun()

                metade = (len(tarefas) + 1) // 2
                c1, c2 = st.columns(2)
                for idx, tarefa in enumerate(tarefas):
                    tid = tarefa.get("id")
                    if tid is None:
                        continue

                    check_key = f"check_{wbs_type}_{tid}"
                    dias_key = f"dias_{wbs_type}_{tid}"
                    if check_key not in st.session_state:
                        st.session_state[check_key] = True
                    if dias_key not in st.session_state:
                        st.session_state[dias_key] = int(tarefa.get("dias_default", 1))

                    col = c1 if idx < metade else c2
                    with col:
                        cc1, cc2 = st.columns([4, 1])
                        with cc1:
                            selecionada = st.checkbox(f"**{tid}.** {tarefa.get('nome','')}", key=check_key)
                        with cc2:
                            if selecionada:
                                st.number_input(
                                    f"dias_{tid}",
                                    min_value=1,
                                    max_value=30,
                                    label_visibility="collapsed",
                                    key=dias_key,
                                )
                            else:
                                st.caption("—")

    col_btn1, col_btn2 = st.columns([1, 3])
    with col_btn1:
        if st.button("← Voltar"):
            _go_to(2)
    with col_btn2:
        if st.button("Confirmar WBS e avançar", type="primary"):
            os_val = str(pendencia.get("os", ""))
            subconjunto_val = str(pendencia.get("subconjunto", ""))
            projeto_label = pendencia.get("projeto_nome")
            projeto_id = pendencia.get("projeto_id")

            wbs_out: list[dict[str, Any]] = []
            erros: list[str] = []
            total_tasks = 0

            for wbs_type, template in templates.items():
                if not st.session_state.get(f"inclui_{wbs_type}", False):
                    continue

                nome_template = str(template.get("nome", wbs_type))
                tipo_logica = str(template.get("tipo_logica", "percentual"))

                if tipo_logica == "multiplicador":
                    categorias = template.get("categorias", []) or []
                    cat_map = {str(c.get("nome", c.get("id", ""))): c for c in categorias}
                    cat_labels = list(cat_map.keys())
                    cat_nome = st.session_state.get(f"cat_{wbs_type}", cat_labels[0] if cat_labels else None)
                    if not cat_nome or cat_nome not in cat_map:
                        erros.append(f"{nome_template}: categoria inválida.")
                        continue

                    categoria = cat_map[cat_nome]
                    itens_categoria = list(categoria.get("itens", []) or [])
                    cat_id = categoria.get("id", "cat")
                    itens_sel = [
                        item
                        for i, item in enumerate(itens_categoria)
                        if st.session_state.get(f"item_{wbs_type}_{cat_id}_{i}", False)
                    ]

                    ok, msg = validar_multiplicador(itens_sel)
                    if not ok:
                        erros.append(f"{nome_template}: {msg}")
                        continue

                    tarefas_exp = gerar_tarefas_multiplicador(
                        nome_wbs=str(codigo_wbs or ""),
                        projeto=str(projeto_label or ""),
                        wbs_type=wbs_type,
                        categoria_nome=str(categoria.get("nome", "")),
                        itens=itens_sel,
                        tarefas_fixas=list(categoria.get("tarefas", []) or []),
                        projeto_id=projeto_id,
                    )
                else:
                    tarefas = template.get("tarefas", []) or []
                    tarefas_sel = []
                    for tarefa in tarefas:
                        tid = tarefa.get("id")
                        if tid is None:
                            continue
                        if st.session_state.get(f"check_{wbs_type}_{tid}", False):
                            dias = int(st.session_state.get(f"dias_{wbs_type}_{tid}", tarefa.get("dias_default", 1)))
                            tarefas_sel.append({"id": tid, "nome": tarefa.get("nome", ""), "dias": dias})

                    ok, msg = validar_selecao(tarefas_sel)
                    if not ok:
                        erros.append(f"{nome_template}: {msg}")
                        continue

                    tarefas_exp = gerar_tarefas_expandidas(
                        nome_wbs=str(codigo_wbs or ""),
                        projeto=str(projeto_label or ""),
                        wbs_type=wbs_type,
                        tarefas_selecionadas=tarefas_sel,
                        projeto_id=projeto_id,
                    )

                tasks_payload: list[dict[str, Any]] = []
                for t in tarefas_exp:
                    nome_task = t.get("tarefa")
                    if not nome_task:
                        continue
                    payload = {"nome": nome_task, "os": os_val, "subconjunto": subconjunto_val, "wbs_type": wbs_type}
                    if projeto_label:
                        payload["projeto"] = projeto_label
                    if projeto_id is not None:
                        payload["projeto_id"] = projeto_id
                    if "categoria" in t and t["categoria"]:
                        payload["categoria"] = t["categoria"]
                    tasks_payload.append(payload)

                if not tasks_payload:
                    erros.append(f"{nome_template}: nenhuma task gerada.")
                    continue

                total_tasks += len(tasks_payload)
                wbs_out.append({"template": wbs_type, "nome": nome_template, "tasks": tasks_payload})

            if erros:
                for e in erros:
                    st.error(e)
                return

            if total_tasks <= 0:
                st.error("Selecione ao menos 1 task em ao menos 1 WBS para avançar.")
                return

            st.session_state.wbs = wbs_out
            _go_to(4)


def render_step4(config: dict[str, Any]) -> None:
    st.subheader("4) Review Final e Envio")

    pendencia: dict[str, Any] = st.session_state.pendencia or {}
    tasks_genericas: list[dict[str, Any]] = st.session_state.tasks_genericas or []
    wbs: list[dict[str, Any]] = st.session_state.wbs or []

    if not pendencia:
        st.error("Pendência não preenchida.")
        if st.button("← Voltar para Step 1"):
            _go_to(1)
        return

    st.markdown("**Pendência**")
    st.write(
        {
            "nome_pendencia": pendencia.get("nome_pendencia"),
            "os": pendencia.get("os"),
            "subconjunto": pendencia.get("subconjunto"),
            "prazo_limite": pendencia.get("prazo_limite"),
            "projeto": pendencia.get("projeto_nome"),
            "projeto_id": pendencia.get("projeto_id"),
            "descricao": pendencia.get("descricao"),
        }
    )

    st.divider()

    st.markdown("**Tasks genéricas**")
    if not tasks_genericas:
        st.warning("Nenhuma task genérica gerada.")
    else:
        st.dataframe(tasks_genericas, use_container_width=True, hide_index=True)

    st.divider()

    st.markdown("**WBS**")
    if not wbs:
        st.warning("Nenhum WBS selecionado.")
    else:
        for entry in wbs:
            with st.expander(f"{entry.get('nome')} ({len(entry.get('tasks', []))} tasks)", expanded=False):
                st.dataframe(entry.get("tasks", []), use_container_width=True, hide_index=True)

    st.divider()

    col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 3])
    with col_btn1:
        if st.button("← Voltar"):
            _go_to(3)
    with col_btn2:
        if st.button("Voltar ao início (editar)"):
            _go_to(1)

    webhook_pendencia = str(config.get("webhook_pendencia", "") or "")
    webhook_tasks = str(config.get("webhook_tasks", "") or "")
    timeout_pendencia = int(config.get("timeout_pendencia", 30) or 30)
    timeout_tasks = int(config.get("timeout_tasks", 60) or 60)

    endpoints_ok = bool(webhook_pendencia and webhook_tasks) and "ENDPOINT_" not in (webhook_pendencia + webhook_tasks)
    with col_btn3:
        criar = st.button("Criar tudo no Monday", type="primary", disabled=not endpoints_ok)
        if not endpoints_ok:
            st.warning("Configure `webhook_pendencia` e `webhook_tasks` em `config.yaml` para habilitar o envio.")

    if not criar:
        return

    payload_pendencia: dict[str, Any] = {
        "nome": pendencia.get("nome_pendencia"),
        "nome_pendencia": pendencia.get("nome_pendencia"),
        "os": pendencia.get("os"),
        "subconjunto": pendencia.get("subconjunto"),
        "descricao": pendencia.get("descricao"),
        "prazo_limite": pendencia.get("prazo_limite"),
        "projeto": pendencia.get("projeto_nome"),
        "projeto_id": pendencia.get("projeto_id"),
    }

    try:
        with st.spinner("Criando pendência no Monday..."):
            r1 = requests.post(webhook_pendencia, json=payload_pendencia, timeout=timeout_pendencia)
            r1.raise_for_status()
            data1 = r1.json() if r1.content else None
            pending_id: str | None
            if isinstance(data1, dict):
                pending_id = data1.get("pending_id") or data1.get("id")  # compat
            elif isinstance(data1, (int, str)):
                pending_id = str(data1)
            else:
                pending_id = None
            if not pending_id:
                raise ValueError("Resposta do webhook_pendencia não contém `pending_id`.")
            st.session_state.pending_id = pending_id

        payload_tasks: dict[str, Any] = {
            "pending_id": pending_id,
            "nome_pendencia": pendencia.get("nome_pendencia"),
            "os": pendencia.get("os"),
            "subconjunto": pendencia.get("subconjunto"),
            "projeto": pendencia.get("projeto_nome"),
            "projeto_id": pendencia.get("projeto_id"),
            "tasks_genericas": tasks_genericas,
            "wbs": wbs,
        }

        with st.spinner("Criando tasks e vinculando à pendência..."):
            r2 = requests.post(webhook_tasks, json=payload_tasks, timeout=timeout_tasks)
            r2.raise_for_status()

        salvar_planejamento(pending_id=str(pending_id), payload=payload_tasks, status="ok", erro_msg=None)
        st.success("Planejamento criado com sucesso!")
        st.info(f"ID da Pendência no Monday: `{pending_id}`")

    except Exception as e:
        pending_id = st.session_state.get("pending_id")
        if pending_id:
            st.error("Falha ao criar tasks. A pendência já foi criada.")
            st.info(f"ID da Pendência no Monday: `{pending_id}`")
            payload_tasks = {
                "pending_id": pending_id,
                "os": pendencia.get("os"),
                "subconjunto": pendencia.get("subconjunto"),
                "projeto": pendencia.get("projeto"),
                "projeto_id": pendencia.get("projeto_id"),
                "tasks_genericas": tasks_genericas,
                "wbs": wbs,
            }
            salvar_planejamento(
                pending_id=str(pending_id),
                payload=payload_tasks,
                status="erro_tasks",
                erro_msg=str(e),
            )
        else:
            st.error(f"Falha ao criar pendência: {e}")


def main() -> None:
    config = carregar_config()

    st.set_page_config(
        page_title=str(config.get("ui", {}).get("page_title", "WBS Hub — Planejamento")),
        page_icon=str(config.get("ui", {}).get("page_icon", "📋")),
        layout=str(config.get("ui", {}).get("layout", "wide")),
    )

    init_db()
    templates = carregar_templates()
    projetos = carregar_projetos()
    feriados = _parse_feriados(config)

    _init_state()
    _sidebar_progresso()

    st.title("WBS Hub — Planejamento")
    st.caption("Wizard de planejamento: pendência → semanas → WBS → envio")

    step = int(st.session_state.step)
    if step == 1:
        render_step1(projetos)
    elif step == 2:
        render_step2(feriados)
    elif step == 3:
        render_step3(templates)
    elif step == 4:
        render_step4(config)
    else:
        st.session_state.step = 1
        st.rerun()


if __name__ == "__main__":
    main()
