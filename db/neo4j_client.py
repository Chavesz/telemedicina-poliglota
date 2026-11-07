"""Neo4j — banco de GRAFOS.

Por que aqui? Recomendação é uma pergunta sobre RELACIONAMENTOS:
"quem comprou o que eu comprei, também comprou o quê?". Em SQL seriam vários
JOINs; no grafo é só seguir arestas (index-free adjacency).

Modelo:
  (:Cliente {id, nome})
  (:Produto {sku, nome})
  (:Categoria {nome})
  (:Cliente)-[:COMPROU {qtd, data}]->(:Produto)
  (:Cliente)-[:AVALIOU {nota}]->(:Produto)
  (:Produto)-[:PERTENCE_A]->(:Categoria)
"""
from neo4j import GraphDatabase
from db.config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))


def _run(query: str, **params) -> list[dict]:
    with driver.session(database=NEO4J_DATABASE) as s:
        return [rec.data() for rec in s.run(query, **params)]


def ping() -> bool:
    driver.verify_connectivity()
    return True


def quem_comprou_tambem_comprou(sku: str, limite: int = 5) -> list[dict]:
    """Filtragem colaborativa item-item."""
    return _run(
        """
        MATCH (p:Produto {sku: $sku})<-[:COMPROU]-(c:Cliente)-[:COMPROU]->(outro:Produto)
        WHERE outro <> p
        RETURN outro.sku AS sku, outro.nome AS nome, count(DISTINCT c) AS clientes
        ORDER BY clientes DESC LIMIT $limite
        """, sku=sku, limite=limite)


def recomendar_para_cliente(cid: str, limite: int = 5) -> list[dict]:
    """Clientes com perfil similar (compraram/avaliaram bem os mesmos produtos)
    também compraram... — exclui o que o cliente já tem."""
    return _run(
        """
        MATCH (eu:Cliente {id: $cid})-[:COMPROU]->(:Produto)<-[:COMPROU]-(similar:Cliente)
        WHERE similar <> eu
        MATCH (similar)-[:COMPROU]->(rec:Produto)
        WHERE NOT (eu)-[:COMPROU]->(rec)
        OPTIONAL MATCH (:Cliente)-[a:AVALIOU]->(rec)
        RETURN rec.sku AS sku, rec.nome AS nome,
               count(DISTINCT similar) AS similares,
               round(coalesce(avg(a.nota), 0), 1) AS nota_media
        ORDER BY similares DESC, nota_media DESC LIMIT $limite
        """, cid=cid, limite=limite)


def populares_da_categoria(categoria: str, limite: int = 5) -> list[dict]:
    """Fallback (cold start) para cliente sem compras."""
    return _run(
        """
        MATCH (cat:Categoria {nome: $cat})<-[:PERTENCE_A]-(p:Produto)<-[r:COMPROU]-()
        RETURN p.sku AS sku, p.nome AS nome, count(r) AS vendas
        ORDER BY vendas DESC LIMIT $limite
        """, cat=categoria, limite=limite)


def registrar_compra(cid: str, nome: str, itens: list[dict]) -> None:
    """Chamado no checkout: o grafo aprende com cada pedido."""
    _run(
        """
        MERGE (c:Cliente {id: $cid}) ON CREATE SET c.nome = $nome
        WITH c
        UNWIND $itens AS item
        MATCH (p:Produto {sku: item.sku})
        MERGE (c)-[r:COMPROU]->(p)
        ON CREATE SET r.qtd = item.qtd, r.data = datetime()
        ON MATCH  SET r.qtd = r.qtd + item.qtd, r.data = datetime()
        """, cid=cid, nome=nome, itens=[{"sku": i["sku"], "qtd": i["qtd"]} for i in itens])


def avaliar(cid: str, sku: str, nota: int) -> None:
    _run(
        """
        MATCH (c:Cliente {id: $cid}), (p:Produto {sku: $sku})
        MERGE (c)-[a:AVALIOU]->(p) SET a.nota = $nota
        """, cid=cid, sku=sku, nota=nota)


def subgrafo_cliente(cid: str) -> list[dict]:
    """Arestas para desenhar o grafo do cliente na tela."""
    return _run(
        """
        MATCH (eu:Cliente {id: $cid})-[:COMPROU]->(p:Produto)<-[:COMPROU]-(o:Cliente)
        RETURN eu.nome AS cliente, p.nome AS produto, o.nome AS outro LIMIT 40
        """, cid=cid)
