# Divisão sugerida (grupo de 5) — defesa de até 30 min

| Pessoa | Parte | Tempo | Arquivo que precisa dominar |
|---|---|---|---|
| 1 | Problema, escopo e modelo de negócio | 3–5 min | README.md |
| 2 | MongoDB: JSON flexível, índices, pedido como documento | ~3 min | db/mongo.py |
| 3 | Redis: token de login com TTL, carrinho HASH, cache-aside | ~3 min | db/redis_client.py |
| 4 | Neo4j: modelo do grafo e Cypher de recomendação | ~3 min | db/neo4j_client.py |
| 5 | Demo ao vivo do fluxo completo + checkout nos 3 bancos | 10 min | app.py, scripts/seed.py |

Todos devem saber responder: por que o carrinho NÃO fica no Mongo? Por que o pedido NÃO fica no Redis?
O que acontece quando o TTL expira? Como a recomendação é calculada?
