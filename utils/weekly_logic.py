from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass(frozen=True)
class TaskSemanal:
    """Representa uma task genérica semanal (prévia/planejamento)."""

    data: date
    horas_previstas: float
    percentual_pendencia: float
    status: str
    ajustada_feriado: bool


def resolver_data_task(sexta: date, feriados: Iterable[date]) -> date:
    """
    Retorna a sexta se não for feriado.
    Se for feriado, retorna a segunda-feira da semana seguinte.
    """
    feriados_set = set(feriados)
    if sexta not in feriados_set:
        return sexta
    return sexta + timedelta(days=3)


def _proxima_sexta_ou_mesma(data_inicio: date) -> date:
    # weekday: Monday=0 ... Friday=4
    delta = (4 - data_inicio.weekday()) % 7
    return data_inicio + timedelta(days=delta)


def proximas_datas_tasks(
    data_inicio: date,
    prazo_limite: date,
    feriados: Iterable[date],
) -> list[tuple[date, bool]]:
    """
    Retorna lista de (data_task, foi_ajustada).

    - A data base é sempre uma sexta-feira a partir de `data_inicio` (inclui a própria
      sexta se `data_inicio` cair em uma sexta).
    - Se a sexta cair em feriado, a task é movida para a segunda-feira seguinte.
    - Não gera datas após `prazo_limite` (considerando a data efetiva da task).
    """
    feriados_set = set(feriados)
    resultado: list[tuple[date, bool]] = []

    candidata = _proxima_sexta_ou_mesma(data_inicio)
    while candidata <= prazo_limite:
        ajustada = candidata in feriados_set
        data_task = resolver_data_task(candidata, feriados_set)
        if data_task <= prazo_limite:
            resultado.append((data_task, ajustada))
        candidata += timedelta(weeks=1)

    # Caso de borda: prazo muito curto (antes da próxima sexta).
    # Para não bloquear o fluxo, criamos uma única task na data do prazo.
    if not resultado and data_inicio <= prazo_limite:
        resultado.append((prazo_limite, False))

    return resultado


def _distribuir_com_ajuste_final(total: float, n: int, casas: int) -> list[float]:
    """
    Distribui `total` em `n` parcelas arredondadas, ajustando a última para fechar o total.
    """
    if n <= 0:
        return []
    base = round(total / n, casas)
    valores = [base for _ in range(n)]
    soma_parcial = round(sum(valores[:-1]), casas) if n > 1 else 0.0
    ultimo = round(total - soma_parcial, casas)
    valores[-1] = ultimo
    return valores


def dias_uteis_no_intervalo(data_inicio: date, prazo_limite: date) -> list[date]:
    """
    Retorna todas as datas de dias úteis (Seg–Sex) no intervalo [data_inicio, prazo_limite].

    Observação: feriados não são filtrados aqui (a decisão é do chamador).
    """
    if data_inicio > prazo_limite:
        return []

    out: list[date] = []
    d = data_inicio
    while d <= prazo_limite:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def distribuir_tasks_diarias_por_colaboradores(
    data_inicio: date,
    prazo_limite: date,
    colaboradores: int,
    horas_por_colaborador: float = 9.0,
) -> list[dict]:
    """
    Gera tasks genéricas por dia útil (Seg–Sex) e replica por colaborador.

    - Para cada dia útil no intervalo [data_inicio, prazo_limite], gera `colaboradores` tasks.
    - Cada task representa 1 colaborador-dia, com `horas_previstas = horas_por_colaborador`.
    - O `percentual_pendencia` é distribuído igualmente entre o total de tasks geradas.
    - Feriados não são filtrados aqui (decisão do chamador); por padrão este fluxo cria no feriado se cair em dia útil.
    """
    if colaboradores <= 0:
        return []

    dias = dias_uteis_no_intervalo(data_inicio, prazo_limite)
    if not dias:
        return []

    total_tasks = len(dias) * int(colaboradores)
    percentuais = _distribuir_com_ajuste_final(100.0, total_tasks, casas=1)

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


def distribuir_tasks_semanais(
    data_inicio: date,
    prazo_limite: date,
    horas_totais: float,
    feriados: Iterable[date],
) -> list[dict]:
    """
    Distribui horas igualmente pelas semanas entre `data_inicio` e `prazo_limite`.

    Retorna lista de dicts para o preview e para montagem do payload final.
    `ajustada_feriado` é apenas para UI e deve ser removida antes do envio ao Make.
    """
    # Compat: a assinatura mantém `feriados`, mas o modo diário não filtra feriados.
    _ = feriados

    datas = dias_uteis_no_intervalo(data_inicio, prazo_limite)
    if not datas:
        return []

    n = len(datas)
    horas_por_semana = _distribuir_com_ajuste_final(float(horas_totais), n, casas=1)
    percentuais = _distribuir_com_ajuste_final(100.0, n, casas=1)

    out: list[dict] = []
    for data_task, horas, pct in zip(datas, horas_por_semana, percentuais):
        out.append(
            {
                "data": data_task.isoformat(),
                "horas_previstas": float(horas),
                "percentual_pendencia": float(pct),
                "status": "planejada",
                "ajustada_feriado": False,
            }
        )
    return out


def formatar_nome_task_generica(os: str, subconjunto: str, percentual: float, data: date) -> str:
    """Gera o nome padrão da task genérica conforme padrão visual do Monday."""
    # Evita mostrar "0%" quando o percentual é fracionário.
    if abs(percentual - round(percentual)) < 1e-9:
        pct_str = f"{percentual:.0f}%"
    else:
        pct_str = f"{percentual:.1f}%"
    return f"{os} - {subconjunto} - {pct_str} | Dia {data.strftime('%d/%m')}"

