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
  auditoria      quem acessou/alterou qual prontuário e quando (LGPD)
"""
import base64
from datetime import datetime, timezone
from pymongo import MongoClient
from db.config import MONGO_URI, MONGO_DB
from db.oplog import registrar

_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = _client[MONGO_DB]
profissionais = db["profissionais"]
pacientes = db["pacientes"]
laudos = db["laudos"]
agendamentos = db["agendamentos"]
auditoria = db["auditoria"]


def ping() -> bool:
    _client.admin.command("ping")
    return True


def contagens() -> dict:
    return {c.name: c.count_documents({}) for c in (profissionais, pacientes, laudos, agendamentos, auditoria)}


def autenticar(email: str, senha: str) -> dict | None:
    # Demo acadêmica: senha em texto. Em produção usar hash (bcrypt).
    registrar("MongoDB", f"db.profissionais.findOne({{email: '{email}'}})")
    return profissionais.find_one({"email": email, "senha": senha}, {"_id": 0, "senha": 0})


def listar_pacientes(texto: str = "") -> list[dict]:
    filtro = {"$text": {"$search": texto}} if texto else {}
    registrar("MongoDB", f"db.pacientes.find({filtro}, {{cpf:1, nome:1}})")
    return list(pacientes.find(filtro, {"_id": 0, "cpf": 1, "nome": 1, "nascimento": 1}).limit(50))


def obter_paciente(cpf: str) -> dict | None:
    registrar("MongoDB", f"db.pacientes.findOne({{cpf: '{cpf}'}})")
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
    registrar("MongoDB", f"db.pacientes.updateOne({{cpf: '{cpf}'}}, {{$push: {{'prontuario.consultas': "
                         f"{{queixa: '{queixa[:30]}', diagnosticos: {diagnosticos}, ...}}}}}})")


def editar_diagnosticos(cpf: str, indice: int, diagnosticos: list[str], medico: dict) -> list[str]:
    """Edita os CIDs de uma consulta já registrada, sem reescrever o documento.

    Usa o operador posicional por índice ($set em 'prontuario.consultas.N.diagnosticos')
    e guarda o histórico da alteração dentro da própria consulta ($push em 'alteracoes').
    Retorna a lista de CIDs anterior.
    """
    pac = pacientes.find_one({"cpf": cpf}, {"prontuario.consultas": 1})
    anteriores = pac["prontuario"]["consultas"][indice].get("diagnosticos", [])
    caminho = f"prontuario.consultas.{indice}"
    pacientes.update_one({"cpf": cpf}, {
        "$set": {f"{caminho}.diagnosticos": diagnosticos},
        "$push": {f"{caminho}.alteracoes": {
            "em": datetime.now(timezone.utc), "por": medico["nome"],
            "de": anteriores, "para": diagnosticos}},
    })
    registrar("MongoDB", f"db.pacientes.updateOne({{cpf: '{cpf}'}}, {{$set: {{'{caminho}.diagnosticos': "
                         f"{diagnosticos}}}, $push: {{'{caminho}.alteracoes': {{...}}}}}})")
    return anteriores


def anexar_laudo(cpf: str, nome_arquivo: str, conteudo: bytes, tipo: str) -> None:
    laudos.insert_one({
        "cpf": cpf, "arquivo": nome_arquivo, "tipo": tipo, "tamanho": len(conteudo),
        "conteudo_b64": base64.b64encode(conteudo).decode(),
        "enviado_em": datetime.now(timezone.utc),
    })
    registrar("MongoDB", f"db.laudos.insertOne({{cpf: '{cpf}', arquivo: '{nome_arquivo}', conteudo_b64: ...}})")


def laudos_do_paciente(cpf: str) -> list[dict]:
    registrar("MongoDB", f"db.laudos.find({{cpf: '{cpf}'}}, {{conteudo_b64: 0}}).sort({{enviado_em: -1}})")
    return list(laudos.find({"cpf": cpf}, {"_id": 0, "conteudo_b64": 0}).sort("enviado_em", -1))


def agenda_do_dia() -> list[dict]:
    registrar("MongoDB", "db.agendamentos.find({}).sort({hora: 1})")
    return list(agendamentos.find({}, {"_id": 0}).sort("hora", 1))


def marcar_agenda_atendida(nome_paciente: str) -> int:
    """Muda o status na agenda; quem chama deve invalidar o cache da agenda no Redis."""
    res = agendamentos.update_many({"paciente": nome_paciente, "status": {"$ne": "Atendido"}},
                                   {"$set": {"status": "Atendido"}})
    registrar("MongoDB", f"db.agendamentos.updateMany({{paciente: '{nome_paciente}'}}, "
                         "{$set: {status: 'Atendido'}})")
    return res.modified_count


def diagnosticos_mais_registrados(limite: int = 10) -> list[dict]:
    """Aggregation pipeline: CIDs mais registrados nos prontuários."""
    pipeline = [
        {"$unwind": "$prontuario.consultas"},
        {"$unwind": "$prontuario.consultas.diagnosticos"},
        {"$group": {"_id": "$prontuario.consultas.diagnosticos", "consultas": {"$sum": 1},
                    "pacientes": {"$addToSet": "$cpf"}}},
        {"$project": {"_id": 0, "cid": "$_id", "consultas": 1, "pacientes": {"$size": "$pacientes"}}},
        {"$sort": {"consultas": -1}},
        {"$limit": limite},
    ]
    registrar("MongoDB", "db.pacientes.aggregate([$unwind consultas, $unwind diagnosticos, "
                         "$group por CID, $project, $sort, $limit])")
    return list(pacientes.aggregate(pipeline))


# ---------- Auditoria (LGPD) ----------
def registrar_acesso(cpf: str, medico: dict, acao: str) -> None:
    """Todo acesso a dado de saúde fica registrado de forma permanente."""
    auditoria.insert_one({"cpf": cpf, "crm": medico["crm"], "medico": medico["nome"],
                          "acao": acao, "em": datetime.now(timezone.utc)})
    registrar("MongoDB", f"db.auditoria.insertOne({{cpf: '{cpf}', crm: '{medico['crm']}', acao: '{acao}'}})")


def acessos_do_paciente(cpf: str, limite: int = 20) -> list[dict]:
    registrar("MongoDB", f"db.auditoria.find({{cpf: '{cpf}'}}).sort({{em: -1}})")
    return list(auditoria.find({"cpf": cpf}, {"_id": 0}).sort("em", -1).limit(limite))
