"""Configuração das conexões.

Ordem de leitura: variáveis de ambiente / arquivo .env (rodando local) e,
se não existir, os "Secrets" do Streamlit Community Cloud (projeto online).
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _cfg(nome: str, padrao: str) -> str:
    valor = os.getenv(nome)
    if valor:
        return valor
    try:  # Streamlit Cloud: Settings -> Secrets
        import streamlit as st
        if nome in st.secrets:
            return str(st.secrets[nome])
    except Exception:  # noqa: BLE001 — sem secrets.toml, segue o padrão local
        pass
    return padrao


MONGO_URI = _cfg("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = _cfg("MONGO_DB", "telemedicina")
REDIS_URL = _cfg("REDIS_URL", "redis://localhost:6379/0")
NEO4J_URI = _cfg("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = _cfg("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = _cfg("NEO4J_PASSWORD", "senha12345")
NEO4J_DATABASE = _cfg("NEO4J_DATABASE", "neo4j")
