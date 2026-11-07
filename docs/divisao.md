# Divisão sugerida (grupo de 5) — defesa de até 30 min

| Pessoa | Parte | Tempo | Arquivo que precisa dominar |
|---|---|---|---|
| 1 | Problema, escopo e modelo de negócio da clínica | 3–5 min | README.md |
| 2 | MongoDB: prontuário como documento JSON flexível, `$push`, índices, laudos | ~3 min | db/mongo.py |
| 3 | Redis: token com TTL, fila com Sorted Set, ZPOPMIN atômico, cache da agenda | ~3 min | db/redis_client.py |
| 4 | Neo4j: modelo do grafo, Cypher de interação medicamentosa e cadeia de diagnósticos | ~3 min | db/neo4j_client.py |
| 5 | Demo ao vivo: check-in → chamar → prontuário → alerta → finalizar | 10 min | app.py, scripts/seed.py |

Perguntas que todos devem saber responder:
- Por que o prontuário NÃO fica no Redis? (é permanente; Redis é volátil/memória)
- Por que a fila NÃO fica no Mongo? (muda a cada segundo, precisa ordenar e ser atômica)
- O que acontece quando o TTL da sessão expira? (chave some, médico volta ao login)
- Como o Neo4j descobre a interação? (segue USA → CONTRAINDICADO_COM a partir do paciente)
- O que é index-free adjacency? (cada nó aponta direto para seus vizinhos, sem busca em índice)
