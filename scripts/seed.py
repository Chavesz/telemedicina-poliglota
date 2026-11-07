"""Script de carga: cria coleções, índices, constraints e popula os 3 bancos.

Uso (na raiz do projeto):  python -m scripts.seed
"""
import random
from pymongo import ASCENDING, TEXT
from db import mongo, redis_client, neo4j_client

random.seed(42)

PRODUTOS = [
    # Esquema FLEXÍVEL: cada categoria tem "specs" diferentes.
    {"sku": "NB-001", "nome": "Notebook Lenovo IdeaPad 5", "categoria": "Informática", "marca": "Lenovo",
     "preco": 3899.90, "estoque": 12, "specs": {"ram": "16GB", "ssd": "512GB", "cpu": "Ryzen 5"}},
    {"sku": "NB-002", "nome": "Notebook Dell Inspiron 15", "categoria": "Informática", "marca": "Dell",
     "preco": 4299.00, "estoque": 8, "specs": {"ram": "16GB", "ssd": "1TB", "cpu": "Core i7"}},
    {"sku": "MS-001", "nome": "Mouse sem fio Logitech M280", "categoria": "Informática", "marca": "Logitech",
     "preco": 89.90, "estoque": 100, "specs": {"dpi": 1000, "conexao": "USB 2.4GHz"}},
    {"sku": "TC-001", "nome": "Teclado Mecânico Redragon Kumara", "categoria": "Informática", "marca": "Redragon",
     "preco": 229.90, "estoque": 40, "specs": {"switch": "Outemu Blue", "layout": "ABNT2"}},
    {"sku": "MN-001", "nome": "Monitor LG 24\" IPS", "categoria": "Informática", "marca": "LG",
     "preco": 799.00, "estoque": 20, "specs": {"polegadas": 24, "resolucao": "1920x1080", "hz": 75}},
    {"sku": "FN-001", "nome": "Fone JBL Tune 510BT", "categoria": "Áudio", "marca": "JBL",
     "preco": 249.90, "estoque": 35, "specs": {"bluetooth": "5.0", "bateria_h": 40}},
    {"sku": "CX-001", "nome": "Caixa de Som JBL Go 3", "categoria": "Áudio", "marca": "JBL",
     "preco": 279.00, "estoque": 25, "specs": {"potencia_w": 4.2, "resistente_agua": "IP67"}},
    {"sku": "CM-001", "nome": "Camiseta Dry Fit Masculina", "categoria": "Moda", "marca": "Nike",
     "preco": 119.90, "estoque": 60, "specs": {"tamanhos": ["P", "M", "G", "GG"], "material": "Poliéster"}},
    {"sku": "TN-001", "nome": "Tênis de Corrida Revolution 7", "categoria": "Moda", "marca": "Nike",
     "preco": 399.90, "estoque": 30, "specs": {"numeracao": [38, 39, 40, 41, 42], "cor": "Preto"}},
    {"sku": "MC-001", "nome": "Mochila para Notebook 15.6\"", "categoria": "Acessórios", "marca": "Samsonite",
     "preco": 349.00, "estoque": 18, "specs": {"litros": 22, "compartimento_notebook": True}},
    {"sku": "LV-001", "nome": "Livro: Bancos de Dados NoSQL", "categoria": "Livros", "marca": "Novatec",
     "preco": 89.00, "estoque": 50, "specs": {"autor": "Pramod Sadalage", "paginas": 220, "isbn": "9788575223383"}},
    {"sku": "LV-002", "nome": "Livro: Python Fluente", "categoria": "Livros", "marca": "Novatec",
     "preco": 159.00, "estoque": 22, "specs": {"autor": "Luciano Ramalho", "paginas": 800}},
]

CLIENTES = [
    {"cliente_id": f"C{i:02d}", "nome": n, "email": f"{n.lower()}@demo.com", "senha": "123",
     "endereco": {"cidade": "Campina Grande", "uf": "PB"}}
    for i, n in enumerate(["Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe", "Gabi", "Heitor"], 1)
]

# Perfis de compra que geram padrões claros no grafo.
PERFIS = {
    "gamer":   ["NB-002", "MS-001", "TC-001", "MN-001", "FN-001"],
    "estudo":  ["NB-001", "MS-001", "MC-001", "LV-001", "LV-002"],
    "esporte": ["CM-001", "TN-001", "FN-001", "CX-001"],
}


def seed_mongo():
    mongo.produtos.drop(); mongo.clientes.drop(); mongo.pedidos.drop()
    mongo.produtos.insert_many([dict(p) for p in PRODUTOS])
    mongo.clientes.insert_many([dict(c) for c in CLIENTES])
    mongo.produtos.create_index([("sku", ASCENDING)], unique=True)
    mongo.produtos.create_index([("categoria", ASCENDING), ("preco", ASCENDING)])
    mongo.produtos.create_index([("nome", TEXT), ("marca", TEXT)], default_language="portuguese")
    mongo.clientes.create_index("email", unique=True)
    mongo.pedidos.create_index([("cliente.id", ASCENDING), ("criado_em", -1)])
    print("Mongo OK:", mongo.produtos.count_documents({}), "produtos")


def seed_neo4j():
    run = neo4j_client._run
    run("MATCH (n) DETACH DELETE n")
    run("CREATE CONSTRAINT produto_sku IF NOT EXISTS FOR (p:Produto) REQUIRE p.sku IS UNIQUE")
    run("CREATE CONSTRAINT cliente_id IF NOT EXISTS FOR (c:Cliente) REQUIRE c.id IS UNIQUE")
    run("CREATE CONSTRAINT categoria_nome IF NOT EXISTS FOR (c:Categoria) REQUIRE c.nome IS UNIQUE")
    run("""
        UNWIND $prods AS p
        MERGE (prod:Produto {sku: p.sku}) SET prod.nome = p.nome
        MERGE (cat:Categoria {nome: p.categoria})
        MERGE (prod)-[:PERTENCE_A]->(cat)
    """, prods=[{"sku": p["sku"], "nome": p["nome"], "categoria": p["categoria"]} for p in PRODUTOS])

    perfis = list(PERFIS.values())
    for i, c in enumerate(CLIENTES):
        base = perfis[i % len(perfis)]
        compras = random.sample(base, k=random.randint(2, len(base) - 1))
        itens = [{"sku": s, "qtd": 1} for s in compras]
        neo4j_client.registrar_compra(c["cliente_id"], c["nome"], itens)
        for s in compras:
            neo4j_client.avaliar(c["cliente_id"], s, random.randint(3, 5))
    print("Neo4j OK")


def seed_redis():
    for k in redis_client.r.scan_iter("cache:*"):
        redis_client.r.delete(k)
    redis_client.r.delete("ranking:mais_vistos")
    print("Redis OK (caches limpos)")


if __name__ == "__main__":
    seed_mongo()
    seed_neo4j()
    seed_redis()
    print("Carga concluída. Login de teste: ana@demo.com / 123")
