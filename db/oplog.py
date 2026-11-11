"""Registro do que cada banco fez — alimenta o "Painel dos Bancos" na demo.

O enunciado pede para mostrar "as chamadas e atualizações acontecendo nos três
bancos simultaneamente". Cada função de db/ chama registrar(banco, comando) e a
tela mostra o log em tempo real. Fora do Streamlit (ex.: seed) não faz nada.
"""
from datetime import datetime


def _streamlit_ativo() -> bool:
    try:
        from streamlit.runtime import exists
        return exists()
    except Exception:  # noqa: BLE001
        return False


def registrar(banco: str, comando: str) -> None:
    if not _streamlit_ativo():
        return
    import streamlit as st
    log = st.session_state.setdefault("oplog", [])
    log.insert(0, {"hora": datetime.now().strftime("%H:%M:%S"), "banco": banco,
                   "comando": " ".join(comando.split())[:250]})
    del log[100:]


def ultimas(n: int = 100) -> list[dict]:
    if not _streamlit_ativo():
        return []
    import streamlit as st
    return st.session_state.get("oplog", [])[:n]
