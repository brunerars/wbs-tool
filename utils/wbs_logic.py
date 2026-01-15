"""
Lógica de processamento WBS
Converte dias em tarefas com porcentagem progressiva
"""

from typing import List, Dict, Any


def calcular_percentuais(dias: int) -> List[int]:
    """
    Calcula a lista de percentuais baseado nos dias.
    
    Exemplo:
        dias=2 -> [50, 100]
        dias=4 -> [25, 50, 75, 100]
        dias=1 -> [100]
    
    Args:
        dias: Número de dias para a tarefa
        
    Returns:
        Lista de percentuais progressivos
    """
    if dias <= 0:
        return []
    
    if dias == 1:
        return [100]
    
    incremento = 100 / dias
    percentuais = []
    
    for i in range(1, dias + 1):
        if i == dias:
            percentuais.append(100)  # Garante que termina em 100%
        else:
            valor = round(incremento * i)
            # Garante que não ultrapassa 100
            percentuais.append(min(valor, 100))
    
    return percentuais


def gerar_tarefas_expandidas(
    nome_wbs: str,
    projeto: str,
    wbs_type: str,
    tarefas_selecionadas: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Gera a lista expandida de tarefas com percentuais.
    
    Args:
        nome_wbs: Nome/identificador do WBS (ex: "010")
        projeto: Nome do projeto vinculado
        wbs_type: Tipo do WBS (ex: "eletrico", "mecanico")
        tarefas_selecionadas: Lista de tarefas com seus dias
            [{"id": 1, "nome": "Tarefa X", "dias": 2}, ...]
    
    Returns:
        Lista de tarefas expandidas prontas para enviar ao Make
        [{"tarefa": "010 - 1. Tarefa X - 50%", "projeto": "...", "wbs_type": "..."}, ...]
    """
    tarefas_expandidas = []
    
    for tarefa in tarefas_selecionadas:
        nome_tarefa = tarefa["nome"]
        ordem = tarefa["id"]
        dias = tarefa["dias"]
        
        percentuais = calcular_percentuais(dias)
        
        for percentual in percentuais:
            tarefa_formatada = f"{nome_wbs} - {ordem}. {nome_tarefa} - {percentual}%"
            
            tarefas_expandidas.append({
                "tarefa": tarefa_formatada,
                "projeto": projeto,
                "wbs_type": wbs_type
            })
    
    return tarefas_expandidas


def validar_selecao(tarefas_selecionadas: List[Dict[str, Any]]) -> tuple[bool, str]:
    """
    Valida se a seleção de tarefas está correta.
    
    Returns:
        (is_valid, mensagem_erro)
    """
    if not tarefas_selecionadas:
        return False, "Selecione pelo menos uma tarefa."
    
    for tarefa in tarefas_selecionadas:
        if tarefa.get("dias", 0) <= 0:
            return False, f"A tarefa '{tarefa['nome']}' precisa ter pelo menos 1 dia."
    
    return True, ""


def resumo_tarefas(tarefas_expandidas: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Gera um resumo das tarefas que serão criadas.
    """
    return {
        "total_items": len(tarefas_expandidas),
        "tarefas": [t["tarefa"] for t in tarefas_expandidas]
    }


# ========================================
# Lógica Multiplicador (WBS Aquisição)
# ========================================

def gerar_tarefas_multiplicador(
    nome_wbs: str,
    projeto: str,
    wbs_type: str,
    categoria_nome: str,
    itens: List[str],
    tarefas_fixas: List[str]
) -> List[Dict[str, Any]]:
    """
    Gera tarefas no formato multiplicador (itens × tarefas fixas).
    
    Para cada item digitado, cria todas as tarefas fixas da categoria.
    
    Args:
        nome_wbs: Nome/identificador do WBS (ex: "010")
        projeto: Nome do projeto vinculado
        wbs_type: Tipo do WBS (ex: "aquisicao")
        categoria_nome: Nome da categoria (ex: "Hardware Mecânico")
        itens: Lista de itens digitados pelo usuário
        tarefas_fixas: Lista de tarefas fixas da categoria
    
    Returns:
        Lista de tarefas expandidas prontas para enviar ao Make
        
    Exemplo de output:
        "010 - <Motor spindle> - Definir lista de itens"
        "010 - <Motor spindle> - Verificar itens de estoque"
        ...
    """
    tarefas_expandidas = []
    
    for item in itens:
        item = item.strip()
        if not item:
            continue
            
        for tarefa in tarefas_fixas:
            tarefa_formatada = f"{nome_wbs} - <{item}> - {tarefa}"
            
            tarefas_expandidas.append({
                "tarefa": tarefa_formatada,
                "projeto": projeto,
                "wbs_type": wbs_type,
                "categoria": categoria_nome
            })
    
    return tarefas_expandidas


def validar_multiplicador(itens: List[str]) -> tuple[bool, str]:
    """
    Valida se a entrada de itens está correta.
    
    Returns:
        (is_valid, mensagem_erro)
    """
    # Remove itens vazios
    itens_validos = [i.strip() for i in itens if i.strip()]
    
    if not itens_validos:
        return False, "Digite pelo menos um item."
    
    return True, ""


def parse_itens(texto: str) -> List[str]:
    """
    Converte texto em lista de itens.
    Aceita separação por linha ou vírgula.
    """
    # Primeiro tenta por linha
    if "\n" in texto:
        itens = texto.split("\n")
    else:
        # Se não tem quebra de linha, tenta por vírgula
        itens = texto.split(",")
    
    # Limpa espaços e remove vazios
    return [item.strip() for item in itens if item.strip()]
