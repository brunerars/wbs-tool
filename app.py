"""
WBS Hub - Gerador de Work Breakdown Structure
Substitui os forms do Monday + n8n por uma interface única e configurável

Suporta dois tipos de lógica:
- percentual: tarefas selecionadas + dias → quebra em %
- multiplicador: categoria + itens → multiplica pelas tarefas fixas
"""

import streamlit as st
import yaml
import requests
from pathlib import Path
from typing import Dict, List, Any
import time
import json

from utils import (
    gerar_tarefas_expandidas, 
    validar_selecao, 
    resumo_tarefas,
    gerar_tarefas_multiplicador,
    validar_multiplicador,
    parse_itens
)


# ========================================
# Configuração e Carregamento
# ========================================

def carregar_config() -> Dict[str, Any]:
    """Carrega configurações gerais do config.yaml"""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def carregar_templates() -> Dict[str, Dict[str, Any]]:
    """Carrega todos os templates YAML da pasta templates/"""
    templates_dir = Path(__file__).parent / "templates"
    templates = {}
    
    for template_file in templates_dir.glob("*.yaml"):
        with open(template_file, "r", encoding="utf-8") as f:
            template = yaml.safe_load(f)
            templates[template["wbs_type"]] = template
    
    return templates

def carregar_projetos(caminho: str) -> list:
    """Carrega a lista de projetos a partir de um arquivo JSON."""
    with open(caminho, 'r', encoding='utf-8') as f:
        dados = json.load(f)
    return dados["projetos"]

def enviar_para_make(
    endpoint: str, 
    tarefas: List[Dict[str, Any]], 
    timeout: int,
    delay: float = 1.0,
    progress_callback=None
) -> tuple[bool, str, List[Dict]]:
    """
    Envia tarefas para o endpoint Make.
    """
    resultados = []
    erros = []
    total = len(tarefas)
    
    for i, tarefa in enumerate(tarefas):
        try:
            response = requests.post(
                endpoint,
                json=tarefa,
                timeout=timeout
            )
            
            resultados.append({
                "tarefa": tarefa["tarefa"],
                "status": response.status_code,
                "ok": response.ok
            })
            
            if not response.ok:
                erros.append(f"{tarefa['tarefa']}: HTTP {response.status_code}")
            
            # Atualiza progresso
            if progress_callback:
                progress_callback((i + 1) / total)
            
            # Delay entre requisições (exceto na última)
            if i < total - 1:
                time.sleep(delay)
                
        except requests.RequestException as e:
            erros.append(f"{tarefa['tarefa']}: {str(e)}")
            resultados.append({
                "tarefa": tarefa["tarefa"],
                "status": "erro",
                "ok": False
            })
    
    if erros:
        return False, f"Erros em {len(erros)} tarefas:\n" + "\n".join(erros), resultados
    
    return True, f"✅ {len(tarefas)} tarefas criadas com sucesso!", resultados


# ========================================
# UI: Lógica Percentual
# ========================================

def render_ui_percentual(template: Dict, wbs_type: str) -> List[Dict[str, Any]]:
    """
    Renderiza UI para WBS com lógica percentual (tarefas + dias).
    Retorna lista de tarefas selecionadas.
    """
    st.subheader("📝 Tarefas")
    st.caption("Marque as tarefas que deseja incluir e defina os dias para cada uma.")
    
    # Botões de ação rápida
    col_sel1, col_sel2, col_sel3 = st.columns([1, 1, 4])
    tarefas = template["tarefas"]
    with col_sel1:
        if st.button("Selecionar todas"):
            for tarefa in tarefas:
                st.session_state[f"check_{wbs_type}_{tarefa['id']}"] = True
            st.rerun()
    with col_sel2:
        if st.button("Limpar seleção"):
            for tarefa in tarefas:
                st.session_state[f"check_{wbs_type}_{tarefa['id']}"] = False
            st.rerun()
    
    # Grid de tarefas em 2 colunas
    tarefas_selecionadas = []
    tarefas = template["tarefas"]
    metade = (len(tarefas) + 1) // 2
    
    col1, col2 = st.columns(2)
    
    for i, tarefa in enumerate(tarefas):
        col = col1 if i < metade else col2
        
        with col:
            c_check, c_dias = st.columns([4, 1])
            
            with c_check:
                selecionada = st.checkbox(
                    f"**{tarefa['id']}.** {tarefa['nome']}",
                    key=f"check_{wbs_type}_{tarefa['id']}"
                )
            
            with c_dias:
                if selecionada:
                    dias = st.number_input(
                        f"dias_{tarefa['id']}",
                        min_value=1,
                        max_value=30,
                        value=tarefa.get("dias_default", 1),
                        label_visibility="collapsed",
                        key=f"dias_{wbs_type}_{tarefa['id']}"
                    )
                    tarefas_selecionadas.append({
                        "id": tarefa["id"],
                        "nome": tarefa["nome"],
                        "dias": dias
                    })
                else:
                    st.caption("—")
    
    return tarefas_selecionadas


# ========================================
# UI: Lógica Multiplicador
# ========================================

def render_ui_multiplicador(template: Dict, wbs_type: str) -> tuple[Dict, List[str]]:
    """
    Renderiza UI para WBS com lógica multiplicador (categoria + itens checkbox).
    Retorna (categoria_selecionada, lista_de_itens_selecionados).
    """
    st.subheader("📦 Categoria e Itens")
    
    # Seleção de categoria
    categorias = template["categorias"]
    categoria_opcoes = {cat["nome"]: cat for cat in categorias}
    
    categoria_nome = st.selectbox(
        "Categoria",
        options=list(categoria_opcoes.keys()),
        help="Selecione a categoria de aquisição"
    )
    
    categoria = categoria_opcoes[categoria_nome]
    
    # Mostra quantas tarefas serão criadas por item
    qtd_tarefas = len(categoria["tarefas"])
    qtd_itens = len(categoria.get("itens", []))
    st.caption(f"ℹ️ {qtd_itens} itens disponíveis · Cada item selecionado gerará **{qtd_tarefas} tarefas**")
    
    st.divider()
    
    # Grid de itens (2 colunas para melhor aproveitamento)
    itens_selecionados = []
    itens_categoria = categoria.get("itens", [])

    # Botões de ação rápida
    col_sel1, col_sel2, col_sel3 = st.columns([1, 1, 4])
    with col_sel1:
        if st.button("Selecionar todos", key=f"sel_all_{categoria['id']}"):
            for i in range(len(itens_categoria)):
                st.session_state[f"item_{wbs_type}_{categoria['id']}_{i}"] = True
            st.rerun()
    with col_sel2:
        if st.button("Limpar", key=f"clear_{categoria['id']}"):
            for i in range(len(itens_categoria)):
                st.session_state[f"item_{wbs_type}_{categoria['id']}_{i}"] = False
            st.rerun()

    # Divide em 2 colunas
    col1, col2 = st.columns(2)
    metade = (len(itens_categoria) + 1) // 2

    for i, item in enumerate(itens_categoria):
        col = col1 if i < metade else col2
        with col:
            selecionado = st.checkbox(
                item,
                key=f"item_{wbs_type}_{categoria['id']}_{i}"
            )
            if selecionado:
                itens_selecionados.append(item)
    
    # Resumo
    if itens_selecionados:
        st.divider()
        total_tarefas = len(itens_selecionados) * qtd_tarefas
        st.success(f"✓ {len(itens_selecionados)} item(s) selecionado(s) → **{total_tarefas} tarefas** serão criadas")
    
    return categoria, itens_selecionados


# ========================================
# Interface Principal
# ========================================

def main():
    # Carrega configurações
    config = carregar_config()
    templates = carregar_templates()
    
    # Configuração da página
    st.set_page_config(
        page_title=config["ui"]["page_title"],
        page_icon=config["ui"]["page_icon"],
        layout=config["ui"]["layout"]
    )
    
    # Header
    st.title("📋 WBS Hub")
    st.markdown("Gerador de Work Breakdown Structure para Monday.com")
    
    # Sidebar - Configurações
    with st.sidebar:
        st.caption("TEMPLATES DISPONÍVEIS:")
        for wbs_type, template in sorted(templates.items(), key=lambda x: x[1]["nome"]):
            tipo = template.get("tipo_logica", "percentual")
            icone = "🔢" if tipo == "percentual" else "📦"
            st.caption(f"{icone} {template['nome']}")
    
    # ----------------------------------------
    # Formulário Principal
    # ----------------------------------------
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        # Seleção do template
        template_opcoes = {t["nome"]: k for k, t in templates.items()}
        opcoes_ordenadas = sorted(template_opcoes.keys())
        template_selecionado = st.selectbox(
            "Tipo de WBS",
            options=opcoes_ordenadas,
            help="Selecione o template de WBS a ser usado"
        )
        
        wbs_type = template_opcoes[template_selecionado]
        template = templates[wbs_type]
        tipo_logica = template.get("tipo_logica", "percentual")
        
        # Informações do WBS
        nome_wbs = st.text_input(
            "Nome/Código do WBS",
            placeholder="Ex: 010",
            help="Identificador único deste WBS"
        )

        # Carrega projetos do JSON e exibe em selectbox
        projetos = carregar_projetos("data/projetos.json")

        if projetos:
            projeto_opcoes = {
                f'{p.get("codigo", "?")} - {p.get("nome", "Sem nome")} ({p.get("cliente", "?")})': p
                for p in projetos
            }

            projeto_label = st.selectbox(
                "Projeto",
                options=list(projeto_opcoes.keys()),
                help="Selecione o projeto vinculado"
            )

            projeto_selecionado = projeto_opcoes[projeto_label]
            projeto = projeto_label  # Nome para exibição
            projeto_id = projeto_selecionado.get("id")  # ID para enviar ao Make
        else:
            st.warning("Nenhum projeto encontrado no arquivo data/projetos.json")
            projeto = None
            projeto_id = None
    
    with col2:
        st.markdown(f"**{template['nome']}**")
        st.caption(template.get("descricao", ""))
        
        # Badge do tipo de lógica
        if tipo_logica == "multiplicador":
            st.info("📦 Modo: Multiplicador (categoria × itens)")
        else:
            st.info("🔢 Modo: Percentual (tarefas × dias)")
    
    st.divider()
    
    # ----------------------------------------
    # Renderiza UI conforme tipo de lógica
    # ----------------------------------------
    
    tarefas_expandidas = []
    pode_enviar = False
    
    if tipo_logica == "multiplicador":
        # UI Multiplicador
        categoria, itens = render_ui_multiplicador(template, wbs_type)
        
        # Validação
        if nome_wbs and projeto and itens:
            is_valid, msg_erro = validar_multiplicador(itens)
            if is_valid:
                pode_enviar = True
                tarefas_expandidas = gerar_tarefas_multiplicador(
                    nome_wbs=nome_wbs,
                    projeto=projeto,
                    wbs_type=wbs_type,
                    categoria_nome=categoria["nome"],
                    itens=itens,
                    tarefas_fixas=categoria["tarefas"],
                    projeto_id=projeto_id
                )
            else:
                st.warning(msg_erro)
        
        # Mensagens de orientação
        if not pode_enviar:
            if not nome_wbs:
                st.info("👆 Preencha o nome/código do WBS")
            elif not projeto:
                st.info("👆 Preencha o projeto")
            elif not itens:
                st.info("👆 Digite pelo menos um item")
    
    else:
        # UI Percentual (padrão)
        tarefas_selecionadas = render_ui_percentual(template, wbs_type)
        
        # Validação
        if nome_wbs and projeto and tarefas_selecionadas:
            is_valid, msg_erro = validar_selecao(tarefas_selecionadas)
            if is_valid:
                pode_enviar = True
                tarefas_expandidas = gerar_tarefas_expandidas(
                    nome_wbs=nome_wbs,
                    projeto=projeto,
                    wbs_type=wbs_type,
                    tarefas_selecionadas=tarefas_selecionadas,
                    projeto_id=projeto_id
                )
            else:
                st.warning(msg_erro)
        
        # Mensagens de orientação
        if not pode_enviar:
            if not nome_wbs:
                st.info("👆 Preencha o nome/código do WBS")
            elif not projeto:
                st.info("👆 Preencha o projeto")
            elif not tarefas_selecionadas:
                st.info("👆 Selecione pelo menos uma tarefa")
    
    st.divider()
    
    # ----------------------------------------
    # Preview e Envio
    # ----------------------------------------
    
    if pode_enviar and tarefas_expandidas:
        resumo = resumo_tarefas(tarefas_expandidas)
        
        with st.expander(f"📋 Preview ({resumo['total_items']} itens a serem criados)", expanded=True):
            # Agrupa por item se for multiplicador
            for tarefa in resumo["tarefas"]:
                st.text(tarefa)
        
        st.divider()
        
        # Botão de envio
        col_btn, col_status = st.columns([1, 3])
        
        endpoint_configurado = config["make_endpoint"] != "https://hook.us1.make.com/SEU_ENDPOINT_AQUI"
        
        with col_btn:
            enviar = st.button(
                "🚀 Criar Tarefas",
                type="primary",
                disabled=not endpoint_configurado
            )
        
        if not endpoint_configurado:
            st.warning("⚠️ Configure o endpoint Make na sidebar antes de enviar.")
        
        # Execução do envio
        if enviar:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            status_text.text(f"Enviando {len(tarefas_expandidas)} tarefas...")
            
            sucesso, mensagem, resultados = enviar_para_make(
                endpoint=config["make_endpoint"],
                tarefas=tarefas_expandidas,
                timeout=config["request_timeout"],
                delay=config["request_delay"],
                progress_callback=lambda p: progress_bar.progress(p)
            )
            
            status_text.empty()
            
            if sucesso:
                st.success(mensagem)
                st.balloons()
            else:
                st.error(mensagem)
                
                with st.expander("Detalhes"):
                    for r in resultados:
                        status_icon = "✅" if r["ok"] else "❌"
                        st.text(f"{status_icon} {r['tarefa']} - {r['status']}")


if __name__ == "__main__":
    main()
