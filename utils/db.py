from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "planejamentos.db"


def init_db() -> None:
    """Cria tabelas se não existirem. Chamar no início do `app.py`."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS planejamentos (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                pending_id   TEXT,
                os           TEXT,
                subconjunto  TEXT,
                payload_json TEXT,
                status       TEXT DEFAULT 'ok',
                erro_msg     TEXT,
                criado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks_genericas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                planejamento_id INTEGER,
                pending_id      TEXT,
                nome            TEXT,
                data            DATE,
                horas_previstas REAL,
                percentual      REAL,
                status          TEXT DEFAULT 'planejada',
                FOREIGN KEY (planejamento_id) REFERENCES planejamentos(id)
            );
            """
        )


def salvar_planejamento(
    pending_id: str,
    payload: dict[str, Any],
    status: str = "ok",
    erro_msg: str | None = None,
) -> int:
    """
    Salva o planejamento (payload completo) e as tasks genéricas.

    Retorna o `id` do planejamento no SQLite.
    """
    init_db()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload_json = json.dumps(payload, ensure_ascii=False)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """
            INSERT INTO planejamentos
            (pending_id, os, subconjunto, payload_json, status, erro_msg)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                pending_id,
                payload.get("os"),
                payload.get("subconjunto"),
                payload_json,
                status,
                erro_msg,
            ),
        )
        plan_id = int(cursor.lastrowid)

        tasks = payload.get("tasks_genericas", []) or []
        if tasks and pending_id:
            conn.executemany(
                """
                INSERT INTO tasks_genericas
                (planejamento_id, pending_id, nome, data, horas_previstas, percentual, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        plan_id,
                        pending_id,
                        t["nome"],
                        t["data"],
                        float(t["horas_previstas"]),
                        float(t["percentual_pendencia"]),
                        t.get("status", "planejada"),
                    )
                    for t in tasks
                ],
            )

        return plan_id

