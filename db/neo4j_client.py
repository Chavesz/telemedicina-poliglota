"""Neo4j — banco de GRAFOS.

Por que aqui? Segurança clínica é uma pergunta sobre RELACIONAMENTOS:
"algum remédio novo conflita com o que o paciente já toma?",
"que diagnósticos costumam vir em cadeia com este?". No grafo é só seguir
arestas (index-free adjacency); em SQL seriam auto-JOINs encadeados.

Modelo:
  (:Paciente {cpf, nome}) (:Medico {crm, nome}) (:Diagnostico {cid, nome}) (:Medicamento {nome})
  (:Medico)-[:ATENDEU {data}]->(:Paciente)
  (:Paciente)-[:DIAGNOSTICADO_COM]->(:Diagnostico)
  (:Paciente)-[:USA]->(:Medicamento)
  (:Paciente)-[:ALERGICO_A]->(:Medicamento)
  (:Medicamento)-[:CONTRAINDICADO_COM {risco, motivo}]->(:Medicamento)
  (:Medicamento)-[:TRATA]->(:Diagnostico)
  (:Diagnostico)-[:CORRELACIONADO_COM]->(:Diagnostico)
"""
from neo4j import GraphDatabase
from db.config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE
from db.oplog import registrar

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD), connection_timeout=5)


def _run(query: str, log: bool = True, **params) -> list[dict]:
    if log:
        linhas = [l for l in query.strip().splitlines() if l.strip() and not l.strip().startswith("//")]
        registrar("Neo4j", " ".join(linhas))
    with driver.session(database=NEO4J_DATABASE) as s:
        return [rec.data() for rec in s.run(query, **params)]


def ping() -> bool:
    driver.verify_connectivity()
    return True


def medicamentos() -> list[str]:
    return [r["nome"] for r in _run("MATCH (m:Medicamento) RETURN m.nome AS nome ORDER BY nome", log=False)]


def diagnosticos() -> list[dict]:
    return _run("MATCH (d:Diagnostico) RETURN d.cid AS cid, d.nome AS nome ORDER BY nome", log=False)


# Consultas de alerta (cada uma é explicável sozinha na defesa).
CYPHER_INTERACAO_USO_ATUAL = """
MATCH (p:Paciente {cpf: $cpf})-[:USA]->(atual:Medicamento)-[c:CONTRAINDICADO_COM]-(novo:Medicamento)
WHERE novo.nome IN $novos
RETURN novo.nome AS medicamento, atual.nome AS conflita_com, c.risco AS risco, c.motivo AS motivo
"""
CYPHER_INTERACAO_MESMA_RECEITA = """
MATCH (a:Medicamento)-[c:CONTRAINDICADO_COM]-(b:Medicamento)
WHERE a.nome IN $novos AND b.nome IN $novos AND a.nome < b.nome
RETURN a.nome AS medicamento, b.nome AS conflita_com, c.risco AS risco, c.motivo AS motivo
"""
CYPHER_ALERGIA = """
MATCH (p:Paciente {cpf: $cpf})-[:ALERGICO_A]->(m:Medicamento)
WHERE m.nome IN $novos
RETURN m.nome AS medicamento, 'alergia do paciente' AS conflita_com, 'ALTO' AS risco,
       'Alergia registrada' AS motivo
"""


def alertas_prescricao(cpf: str, novos: list[str]) -> list[dict]:
    alertas = []
    for tipo, q in [("Interação com uso atual", CYPHER_INTERACAO_USO_ATUAL),
                    ("Interação na mesma receita", CYPHER_INTERACAO_MESMA_RECEITA),
                    ("Alergia", CYPHER_ALERGIA)]:
        alertas += [{"tipo": tipo, **r} for r in _run(q, cpf=cpf, novos=novos)]
    return alertas


CYPHER_ALERTA_HISTORICO = """
// Alertas automáticos do HISTÓRICO: remédios que o paciente já usa e que conflitam entre si
MATCH (p:Paciente {cpf: $cpf})-[:USA]->(a:Medicamento)-[c:CONTRAINDICADO_COM]-(b:Medicamento)<-[:USA]-(p)
WHERE a.nome < b.nome
RETURN 'Conflito entre remédios em uso' AS tipo, a.nome AS medicamento, b.nome AS conflita_com,
       c.risco AS risco, c.motivo AS motivo
UNION
// ...ou um remédio em uso ao qual o paciente é alérgico
MATCH (p:Paciente {cpf: $cpf})-[:USA]->(m:Medicamento)<-[:ALERGICO_A]-(p)
RETURN 'Usa remédio ao qual é alérgico' AS tipo, m.nome AS medicamento, 'alergia do paciente' AS conflita_com,
       'ALTO' AS risco, 'Alergia registrada' AS motivo
"""


def alertas_historico(cpf: str) -> list[dict]:
    return _run(CYPHER_ALERTA_HISTORICO, cpf=cpf)


def diagnosticos_correlacionados(cid: str, profundidade: int = 2) -> list[dict]:
    """Cadeia de diagnósticos correlacionados até N saltos (path variável)."""
    return _run(
        f"""
        MATCH caminho = (d:Diagnostico {{cid: $cid}})-[:CORRELACIONADO_COM*1..{int(profundidade)}]->(o:Diagnostico)
        WHERE o <> d
        RETURN o.cid AS cid, o.nome AS nome, min(length(caminho)) AS saltos
        ORDER BY saltos
        """, cid=cid)


def teia_paciente(cpf: str) -> list[dict]:
    """Arestas do paciente para desenhar o grafo."""
    return _run(
        """
        MATCH (p:Paciente {cpf: $cpf})-[r]-(x)
        RETURN p.nome AS origem, type(r) AS rel, coalesce(x.nome, x.cid) AS destino
        """, cpf=cpf)


def registrar_atendimento(cpf: str, nome: str, crm: str, cids: list[str], meds: list[str]) -> None:
    """Ao finalizar a consulta, o grafo ganha o novo histórico do paciente."""
    _run(
        """
        MERGE (p:Paciente {cpf: $cpf}) ON CREATE SET p.nome = $nome
        WITH p
        OPTIONAL MATCH (m:Medico {crm: $crm})
        FOREACH (_ IN CASE WHEN m IS NULL THEN [] ELSE [1] END |
                 CREATE (m)-[:ATENDEU {data: datetime()}]->(p))
        WITH p
        UNWIND $cids AS cid
        MATCH (d:Diagnostico {cid: cid})
        MERGE (p)-[:DIAGNOSTICADO_COM]->(d)
        """, cpf=cpf, nome=nome, crm=crm, cids=cids or [""])
    _run(
        """
        MATCH (p:Paciente {cpf: $cpf})
        UNWIND $meds AS med
        MATCH (m:Medicamento {nome: med})
        MERGE (p)-[:USA]->(m)
        """, cpf=cpf, meds=meds)


def atualizar_diagnosticos(cpf: str, removidos: list[str], adicionados: list[str]) -> None:
    """Sincroniza o grafo quando um diagnóstico de consulta antiga é editado no Mongo."""
    if removidos:
        _run("""
            MATCH (p:Paciente {cpf: $cpf})-[r:DIAGNOSTICADO_COM]->(d:Diagnostico)
            WHERE d.cid IN $removidos
            DELETE r
            """, cpf=cpf, removidos=removidos)
    if adicionados:
        _run("""
            MATCH (p:Paciente {cpf: $cpf})
            UNWIND $adicionados AS cid
            MATCH (d:Diagnostico {cid: cid})
            MERGE (p)-[:DIAGNOSTICADO_COM]->(d)
            """, cpf=cpf, adicionados=adicionados)


# ---------- Histórico epidemiológico ----------
CYPHER_EPIDEMIOLOGIA = """
// Diagnósticos mais frequentes na clínica e quantos pacientes têm cada um
MATCH (p:Paciente)-[:DIAGNOSTICADO_COM]->(d:Diagnostico)
RETURN d.cid AS cid, d.nome AS diagnostico, count(DISTINCT p) AS pacientes
ORDER BY pacientes DESC, cid
"""
CYPHER_MESMO_CID = """
// Pacientes que compartilham o mesmo diagnóstico e os remédios que eles usam
MATCH (d:Diagnostico {cid: $cid})<-[:DIAGNOSTICADO_COM]-(p:Paciente)
OPTIONAL MATCH (p)-[:USA]->(m:Medicamento)
RETURN p.nome AS paciente, collect(DISTINCT m.nome) AS usa
ORDER BY paciente
"""
CYPHER_COMORBIDADES = """
// Comorbidades: diagnósticos que aparecem JUNTOS no mesmo paciente
MATCH (d1:Diagnostico)<-[:DIAGNOSTICADO_COM]-(p:Paciente)-[:DIAGNOSTICADO_COM]->(d2:Diagnostico)
WHERE d1.cid < d2.cid
RETURN d1.nome + ' + ' + d2.nome AS combinacao, count(DISTINCT p) AS pacientes
ORDER BY pacientes DESC
LIMIT 10
"""


def epidemiologia() -> list[dict]:
    return _run(CYPHER_EPIDEMIOLOGIA)


def pacientes_com_cid(cid: str) -> list[dict]:
    return _run(CYPHER_MESMO_CID, cid=cid)


def comorbidades() -> list[dict]:
    return _run(CYPHER_COMORBIDADES)


def estatisticas() -> dict:
    return {
        "nos": _run("MATCH (n) RETURN labels(n)[0] AS tipo, count(*) AS total ORDER BY total DESC", log=False),
        "relacionamentos": _run("MATCH ()-[r]->() RETURN type(r) AS tipo, count(*) AS total "
                                "ORDER BY total DESC", log=False),
    }
