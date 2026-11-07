# 🛒 Loja Poliglota — E-commerce com Recomendação (Polyglot Persistence)

Projeto Final — Implementação de Bancos de Dados NoSQL (Prof. Ricardo Roberto de Lima)
**Estudo de Caso 01: E-Commerce Inteligente & Motor de Recomendação**

Aplicação Python + Streamlit que usa **3 bancos NoSQL ao mesmo tempo**, cada um no que faz de melhor.

## Por que cada dado está em cada banco

| Banco | Modelo | O que guarda | Por quê |
|---|---|---|---|
| **MongoDB** | Documento (JSON) | Catálogo de produtos, clientes, pedidos | Produtos têm `specs` diferentes por categoria (esquema flexível). Pedido é um documento com snapshot dos itens/preços — histórico permanente. Índices de texto para busca. |
| **Redis** | Chave-valor em memória | Sessão/token de login, carrinho, cache, ranking | Dados temporários e que precisam ser rápidos. **TTL** faz expirar sozinho: sessão (30 min), carrinho (24 h), cache (60 s). |
| **Neo4j** | Grafo | `(:Cliente)-[:COMPROU]->(:Produto)-[:PERTENCE_A]->(:Categoria)`, `[:AVALIOU]` | Recomendação é pergunta sobre relacionamentos: navegar arestas (index-free adjacency) em vez de vários JOINs. |

### Chaves do Redis
| Chave | Tipo | TTL |
|---|---|---|
| `sessao:{token}` | STRING (JSON do cliente) | 30 min (renovado a cada acesso) |
| `carrinho:{cliente_id}` | HASH `sku -> qtd` | 24 h |
| `cache:produto:{sku}` / `cache:busca:{termo}:{cat}` | STRING (JSON) | 60 s |
| `ranking:mais_vistos` | SORTED SET | — |

### Exemplo de documento (MongoDB `produtos`)
```json
{ "sku": "NB-001", "nome": "Notebook Lenovo IdeaPad 5", "categoria": "Informática",
  "marca": "Lenovo", "preco": 3899.90, "estoque": 12,
  "specs": { "ram": "16GB", "ssd": "512GB", "cpu": "Ryzen 5" } }
```

### Cypher de recomendação
```cypher
MATCH (eu:Cliente {id:$cid})-[:COMPROU]->(:Produto)<-[:COMPROU]-(similar:Cliente)
MATCH (similar)-[:COMPROU]->(rec:Produto)
WHERE NOT (eu)-[:COMPROU]->(rec)
RETURN rec.nome, count(DISTINCT similar) AS similares
ORDER BY similares DESC LIMIT 5
```

## Fluxo da demo (os 3 bancos juntos)
1. **Login** → valida no Mongo, cria token no Redis com TTL.
2. **Catálogo** → busca no Mongo; 2ª busca igual vem do Redis (cache HIT, mostra o tempo).
3. **Carrinho** → `HINCRBY`/`HSET`/`HDEL` no Redis em tempo real.
4. **Recomendações** → Cypher no Neo4j + desenho do grafo.
5. **Checkout** → salva pedido no Mongo, cria `[:COMPROU]` no Neo4j, apaga o carrinho no Redis.

## Como rodar
```bash
docker compose up -d                 # sobe Mongo, Redis e Neo4j
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env               # (Linux/Mac: cp)
python -m scripts.seed               # cria índices/constraints e popula os 3 bancos
streamlit run app.py
```
Login de teste: `ana@demo.com` / `123` (também bruno@, carla@, diego@ ... `@demo.com`).
Neo4j Browser para ver o grafo: http://localhost:7474 (neo4j / senha12345) → `MATCH (n) RETURN n`.

## Estrutura
```
app.py               # Streamlit: telas e orquestração
db/mongo.py          # MongoDB: catálogo, clientes, pedidos
db/redis_client.py   # Redis: sessão, carrinho, cache, ranking
db/neo4j_client.py   # Neo4j: grafo e consultas Cypher
scripts/seed.py      # carga inicial + índices nos 3 bancos
docs/divisao.md      # divisão da apresentação entre o grupo
```
