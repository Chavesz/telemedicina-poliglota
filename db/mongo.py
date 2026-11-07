"""MongoDB — banco orientado a DOCUMENTOS.

Por que aqui? Prontuário é naturalmente um documento: cada paciente tem um
histórico diferente (consultas, prescrições, exames, laudos, alergias). Um
JSON flexível guarda tudo junto, sem dezenas de tabelas e JOINs, e aceita
campos novos (ex.: um exame novo) sem alterar esquema. É o registro PERMANENTE.

Coleções:
  profissionais  {crm, nome, especialidade, email, senha}
  pacientes      {cpf, nome, nascimento, alergias[], prontuario: {consultas[]}}
  laudos         arquivos anexados (base64) ligados ao paciente
  agendamentos   agenda do dia
"""
import base64
from datetime import datetime, timezone
from pymongo import MongoClient
from db.config import MONGO_URI, MONGO_DB

_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = _client[MONGO_DB]
profissionais = db["profissionais"]
pacientes = db["pacientes"]
laudos = db["laudos"]
agendamentos = db["agendamentos"]


def ping() -> bool:
    _client.admin.command("ping")
    return True


def autenticar(email: str, senha: str) -> dict | None:
    # Demo acadêmica: senha em texto. Em produção usar hash (bcrypt).
    return profissionais.find_one({"email": email, "senha": senha}, {"_id": 0, "senha": 0})


def listar_pacientes(texto: str = "") -> list[dict]:
    filtro = {"$text": {"$search": texto}} if texto else {}
    return list(pacientes.find(filtro, {"_id": 0, "cpf": 1, "nome": 1, "nascimento": 1}).limit(50))


def obter_paciente(cpf: str) -> dict | None:
    return pacientes.find_one({"cpf": cpf}, {"_id": 0})


def registrar_consulta(cpf: str, medico: dict, queixa: str, diagnosticos: list[str],
                       prescricoes: list[dict], observacoes: str) -> None:
    """Adiciona uma consulta ao array do prontuário ($push) — sem mexer no resto do documento."""
    consulta = {
        "data": datetime.now(timezone.utc),
        "medico": {"crm": medico["crm"], "nome": medico["nome"], "especialidade": medico["especialidade"]},
        "queixa": queixa,
        "diagnosticos": diagnosticos,
        "prescricoes": prescricoes,          # [{medicamento, posologia}]
        "observacoes": observacoes,
    }
    pacientes.update_one({"cpf": cpf}, {"$push": {"prontuario.consultas": consulta}})


def anexar_laudo(cpf: str, nome_arquivo: str, conteudo: bytes, tipo: str) -> None:
    laudos.insert_one({
        "cpf": cpf, "arquivo": nome_arquivo, "tipo": tipo, "tamanho": len(conteudo),
        "conteudo_b64": base64.b64encode(conteudo).decode(),
        "enviado_em": datetime.now(timezone.utc),
    })


def laudos_do_paciente(cpf: str) -> list[dict]:
    return list(laudos.find({"cpf": cpf}, {"_id": 0, "conteudo_b64": 0}).sort("enviado_em", -1))


def agenda_do_dia() -> list[dict]:
    return list(agendamentos.find({}, {"_id": 0}).sort("hora", 1))
