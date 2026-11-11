# Roteiro — apresentação de 10 a 15 minutos (e vídeo)

Objetivo que o professor cobra: **as diferenças dos 3 bancos, o que cada um faz, como foi implementado aqui e quando usar cada um.**
Regra de ouro: toda afirmação vem acompanhada de algo na tela (o app ou o código).

## Bloco 1 — Problema (1–2 min) · Pessoa 1
- Clínica de telemedicina: recepção virtual, fila por prioridade, prontuário, receita com checagem de segurança.
- Três tipos de dado com necessidades diferentes: **permanente e variável** (prontuário), **temporário e rápido** (fila, login), **cheio de ligações** (remédios × doenças × pacientes).
- Frase-chave: *"um banco só faria tudo mal; usamos persistência poliglota."*

## Bloco 2 — Os 3 bancos (4–5 min) · Pessoas 2, 3 e 4 — tela **Comparativo dos bancos**
Cada um fala ~1:30 mostrando a tabela + o arquivo do código:
- **MongoDB (documento)** — `db/mongo.py`. Mostrar o JSON do Carlos (tem `INR`) e da Maria (tem `semanas_gestacao`): esquema flexível. Consulta nova entra com `$push`; edição de diagnóstico com `$set` posicional. *Quando usar:* dado principal, permanente, formato variável. *Fraco em:* relacionar muitos documentos.
- **Redis (chave-valor em memória)** — `db/redis_client.py`. `sessao:{token}` com TTL 30 min, fila em **Sorted Set** (`ZADD`/`ZPOPMIN` atômico), cache da agenda com TTL 5 min e invalidação. *Quando usar:* temporário, muito acessado, que expira. *Fraco em:* RAM limitada, pode perder dados.
- **Neo4j (grafo)** — `db/neo4j_client.py`. Modelo `(:Paciente)-[:USA]->(:Medicamento)-[:CONTRAINDICADO_COM]-(:Medicamento)`. Mostrar o Cypher × SQL lado a lado. *Quando usar:* a pergunta é sobre conexões. *Fraco em:* guardar documentos e relatórios de tudo.

## Bloco 3 — Demo ao vivo (5–6 min) · Pessoa 5 — deixar o **Painel dos Bancos** aberto numa segunda aba
1. Login → sidebar mostra o TTL da sessão (**Redis**).
2. Recepção → check-in de *Paulo Ramos* como **Urgente**: ele passa na frente (**Redis Sorted Set**). Recarregar a agenda: **MISS** (Mongo) e depois **HIT** (Redis).
3. Chamar próximo → abre o Prontuário (**MongoDB**).
4. Paciente *Carlos Oliveira* → receitar **AAS** → alerta de sangramento com Varfarina (**Neo4j**).
5. Finalizar → aparece o checklist "o que cada banco fez" (Mongo grava, Neo4j aprende, Redis tira da fila).
6. Painel dos Bancos → mostrar o log com os comandos reais dos três.
7. Fecho de impacto: Comparativo → **Simular reinício do Redis** → a fila some, os prontuários continuam.

## Bloco 4 — Fechamento (30 s)
"MongoDB guarda a verdade, Redis guarda o agora, Neo4j guarda as ligações."

## Perguntas prováveis (todos precisam saber)
- Por que o prontuário não fica no Redis? → é permanente; Redis é memória.
- Por que a fila não fica no Mongo? → muda o tempo todo, precisa ordenar e ser atômica.
- O que é TTL e o que acontece quando expira? → tempo de vida; a chave some e o médico volta ao login.
- O que é cache-aside e invalidação? → lê do Redis; se não tem, busca no Mongo e guarda; ao mudar o dado, apaga a cópia.
- O que é index-free adjacency? → cada nó aponta direto para os vizinhos, sem procurar em índice.
- E se o Neo4j cair na finalização? → a consulta já está salva no Mongo (fonte da verdade); o grafo fica para depois (consistência eventual).

## Vídeo (mesmo roteiro, gravado)
- Gravar a tela com **OBS Studio** (grátis) ou a Barra de Jogo do Windows (`Win + Alt + R`), 1080p.
- Um bloco por pessoa, cada um grava a sua parte com o próprio microfone; junta tudo num editor (CapCut ou Clipchamp).
- Antes de gravar: `python -m scripts.seed` para os dados ficarem iguais ao roteiro.
- Alvo: 10–12 min. Legenda simples com o nome de quem fala e do banco em destaque.
