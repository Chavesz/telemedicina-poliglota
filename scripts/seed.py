"""Script de carga: cria coleções, índices, constraints e popula os 3 bancos.

Uso (na raiz do projeto):  python -m scripts.seed
Dados FICTÍCIOS, apenas para fins acadêmicos.
"""
from pymongo import ASCENDING, TEXT
from db import mongo, redis_client, neo4j_client

MEDICOS = [
    {"crm": "CRM-PB 1001", "nome": "Dra. Ana Lima", "especialidade": "Clínica Geral", "email": "ana@clinica.com", "senha": "123"},
    {"crm": "CRM-PB 1002", "nome": "Dr. Bruno Souza", "especialidade": "Cardiologia", "email": "bruno@clinica.com", "senha": "123"},
    {"crm": "CRM-PB 1003", "nome": "Dra. Carla Melo", "especialidade": "Endocrinologia", "email": "carla@clinica.com", "senha": "123"},
]

# Esquema FLEXÍVEL: cada prontuário tem campos diferentes.
PACIENTES = [
    {"cpf": "111.111.111-11", "nome": "José Pereira", "nascimento": "1958-03-12", "sexo": "M",
     "alergias": ["Dipirona"], "condicoes_cronicas": ["Hipertensão", "Diabetes tipo 2"],
     "uso_continuo": ["Losartana", "Metformina"],
     "prontuario": {"consultas": [{"data": "2026-08-10", "medico": {"nome": "Dr. Bruno Souza"},
                                   "queixa": "Pressão alta", "diagnosticos": ["I10"],
                                   "prescricoes": [{"medicamento": "Losartana", "posologia": "50mg 1x/dia"}]}]},
     "exames": [{"tipo": "Glicemia", "valor": 145, "unidade": "mg/dL", "data": "2026-08-10"}]},
    {"cpf": "222.222.222-22", "nome": "Maria Santos", "nascimento": "1990-07-25", "sexo": "F",
     "alergias": [], "gestante": True, "semanas_gestacao": 20,
     "uso_continuo": ["Ácido Fólico"], "prontuario": {"consultas": []}},
    {"cpf": "333.333.333-33", "nome": "Carlos Oliveira", "nascimento": "1975-11-02", "sexo": "M",
     "alergias": ["Penicilina"], "condicoes_cronicas": ["Fibrilação atrial"],
     "uso_continuo": ["Varfarina"], "prontuario": {"consultas": []},
     "exames": [{"tipo": "INR", "valor": 2.6, "data": "2026-10-01"}]},
    {"cpf": "444.444.444-44", "nome": "Fernanda Costa", "nascimento": "2001-01-15", "sexo": "F",
     "alergias": [], "uso_continuo": [], "prontuario": {"consultas": []}},
    {"cpf": "555.555.555-55", "nome": "Paulo Ramos", "nascimento": "1966-05-30", "sexo": "M",
     "alergias": ["AAS"], "condicoes_cronicas": ["Asma"], "uso_continuo": ["Salbutamol"],
     "prontuario": {"consultas": []}},
]

AGENDA = [
    {"hora": "08:00", "paciente": "José Pereira", "medico": "Dr. Bruno Souza", "tipo": "Retorno"},
    {"hora": "08:30", "paciente": "Maria Santos", "medico": "Dra. Ana Lima", "tipo": "Pré-natal"},
    {"hora": "09:00", "paciente": "Carlos Oliveira", "medico": "Dr. Bruno Souza", "tipo": "Controle INR"},
    {"hora": "10:00", "paciente": "Paulo Ramos", "medico": "Dra. Ana Lima", "tipo": "Primeira consulta"},
]

MEDICAMENTOS = ["Losartana", "Metformina", "Varfarina", "AAS", "Ibuprofeno", "Dipirona", "Penicilina",
                "Amoxicilina", "Omeprazol", "Ácido Fólico", "Salbutamol", "Propranolol", "Sinvastatina",
                "Claritromicina", "Paracetamol"]

DIAGNOSTICOS = [("I10", "Hipertensão arterial"), ("E11", "Diabetes tipo 2"), ("E78", "Dislipidemia"),
                ("I48", "Fibrilação atrial"), ("I63", "AVC isquêmico"), ("N18", "Doença renal crônica"),
                ("J45", "Asma"), ("J06", "Infecção de vias aéreas"), ("K21", "Refluxo gastroesofágico"),
                ("I25", "Doença arterial coronariana")]

# (med_a, med_b, risco, motivo) — exemplos didáticos.
CONTRAINDICACOES = [
    ("Varfarina", "AAS", "ALTO", "Risco de sangramento"),
    ("Varfarina", "Ibuprofeno", "ALTO", "Risco de sangramento"),
    ("Varfarina", "Claritromicina", "ALTO", "Potencializa anticoagulação"),
    ("Losartana", "Ibuprofeno", "MÉDIO", "Reduz efeito anti-hipertensivo / lesão renal"),
    ("Propranolol", "Salbutamol", "ALTO", "Betabloqueador antagoniza broncodilatador"),
    ("Sinvastatina", "Claritromicina", "ALTO", "Risco de rabdomiólise"),
    ("Metformina", "Ibuprofeno", "BAIXO", "Atenção à função renal"),
]

TRATA = [("Losartana", "I10"), ("Propranolol", "I10"), ("Metformina", "E11"), ("Sinvastatina", "E78"),
         ("Varfarina", "I48"), ("Salbutamol", "J45"), ("Amoxicilina", "J06"), ("Omeprazol", "K21"),
         ("AAS", "I25")]

# Cadeias clínicas: E11 -> N18, I10 -> I63, E78 -> I25 ...
CORRELACOES = [("E11", "I10"), ("E11", "N18"), ("I10", "I63"), ("I10", "N18"), ("E78", "I25"),
               ("I25", "I63"), ("I48", "I63"), ("J45", "J06")]

# Histórico no grafo: (cpf, crm, [cids], [meds em uso], [alergias])
HIST = [
    ("111.111.111-11", "CRM-PB 1002", ["I10", "E11"], ["Losartana", "Metformina"], ["Dipirona"]),
    ("222.222.222-22", "CRM-PB 1001", [], ["Ácido Fólico"], []),
    ("333.333.333-33", "CRM-PB 1002", ["I48"], ["Varfarina"], ["Penicilina"]),
    ("444.444.444-44", "CRM-PB 1001", ["J06"], [], []),
    ("555.555.555-55", "CRM-PB 1001", ["J45"], ["Salbutamol"], ["AAS"]),
]


def seed_mongo():
    for c in (mongo.profissionais, mongo.pacientes, mongo.laudos, mongo.agendamentos):
        c.drop()
    mongo.profissionais.insert_many([dict(m) for m in MEDICOS])
    mongo.pacientes.insert_many([dict(p) for p in PACIENTES])
    mongo.agendamentos.insert_many([dict(a) for a in AGENDA])
    mongo.profissionais.create_index("email", unique=True)
    mongo.profissionais.create_index("crm", unique=True)
    mongo.pacientes.create_index("cpf", unique=True)
    mongo.pacientes.create_index([("nome", TEXT)], default_language="portuguese")
    mongo.pacientes.create_index("prontuario.consultas.data")
    mongo.laudos.create_index([("cpf", ASCENDING), ("enviado_em", -1)])
    print("Mongo OK:", mongo.pacientes.count_documents({}), "pacientes")


def seed_neo4j():
    run = neo4j_client._run
    run("MATCH (n) DETACH DELETE n")
    for label, prop in [("Paciente", "cpf"), ("Medico", "crm"), ("Diagnostico", "cid"), ("Medicamento", "nome")]:
        run(f"CREATE CONSTRAINT {label.lower()}_{prop} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE")
    run("UNWIND $l AS m MERGE (:Medico {crm: m.crm, nome: m.nome, especialidade: m.especialidade})",
        l=[{k: m[k] for k in ("crm", "nome", "especialidade")} for m in MEDICOS])
    run("UNWIND $l AS n MERGE (:Medicamento {nome: n})", l=MEDICAMENTOS)
    run("UNWIND $l AS d MERGE (:Diagnostico {cid: d[0], nome: d[1]})", l=[list(d) for d in DIAGNOSTICOS])
    run("""UNWIND $l AS c MATCH (a:Medicamento {nome: c[0]}), (b:Medicamento {nome: c[1]})
           MERGE (a)-[:CONTRAINDICADO_COM {risco: c[2], motivo: c[3]}]->(b)""",
        l=[list(c) for c in CONTRAINDICACOES])
    run("""UNWIND $l AS t MATCH (m:Medicamento {nome: t[0]}), (d:Diagnostico {cid: t[1]})
           MERGE (m)-[:TRATA]->(d)""", l=[list(t) for t in TRATA])
    run("""UNWIND $l AS c MATCH (a:Diagnostico {cid: c[0]}), (b:Diagnostico {cid: c[1]})
           MERGE (a)-[:CORRELACIONADO_COM]->(b)""", l=[list(c) for c in CORRELACOES])
    nomes = {p["cpf"]: p["nome"] for p in PACIENTES}
    for cpf, crm, cids, meds, alergias in HIST:
        neo4j_client.registrar_atendimento(cpf, nomes[cpf], crm, cids, meds)
        run("""MATCH (p:Paciente {cpf: $cpf}) UNWIND $al AS a
               MATCH (m:Medicamento {nome: a}) MERGE (p)-[:ALERGICO_A]->(m)""", cpf=cpf, al=alergias)
    print("Neo4j OK")


def seed_redis():
    r = redis_client.r
    for padrao in ("fila:*", "atendimento:*", "cache:*", "contador:*"):
        for k in r.scan_iter(padrao):
            r.delete(k)
    # Alguns pacientes já aguardando na recepção virtual.
    redis_client.entrar_na_fila("444.444.444-44", "Fernanda Costa", "Normal")
    redis_client.entrar_na_fila("111.111.111-11", "José Pereira", "Urgente")
    redis_client.entrar_na_fila("333.333.333-33", "Carlos Oliveira", "Normal")
    print("Redis OK: fila com", len(redis_client.fila()), "pacientes")


if __name__ == "__main__":
    seed_mongo()
    seed_neo4j()
    seed_redis()
    print("Carga concluída. Login de teste: ana@clinica.com / 123")
