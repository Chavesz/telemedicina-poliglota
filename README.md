# 🩺 Telemedicina Poliglota — Gestão de Prontuários (Polyglot Persistence)

Projeto Final — Implementação de Bancos de Dados NoSQL (Prof. Ricardo Roberto de Lima)
**Estudo de Caso 03: Plataforma de Telemedicina & Gestão de Prontuários Médicos**

Aplicação Python + Streamlit que usa **3 bancos NoSQL ao mesmo tempo**, cada um no que faz de melhor.
Dados 100% fictícios.

## Modelo de negócio
Uma clínica com atendimento remoto: o paciente faz check-in na recepção virtual, entra numa fila
por prioridade, o médico chama, consulta o prontuário, prescreve, e o sistema **alerta** se o remédio
conflita com o que o paciente já usa ou com alergias. Ao final, emite a receita e atualiza a fila.

## Por que cada dado está em cada banco

| Banco | Modelo | O que guarda | Por quê |
|---|---|---|---|
| **MongoDB** | Documento (JSON) | Prontuários, profissionais, laudos anexados, agenda | Cada paciente tem um histórico diferente (gestante tem `semanas_gestacao`, cardíaco tem `INR`...). Esquema flexível, consultas embutidas no documento (`$push`), registro **permanente**. |
| **Redis** | Chave-valor em memória | Token de login, fila de espera, quem está em atendimento, cache da agenda, contador | Estado temporário e em tempo real. **Sorted Set** ordena a fila por prioridade; **ZPOPMIN** é atômico; **TTL** expira sessão e cache sozinhos. |
| **Neo4j** | Grafo | Pacientes, médicos, diagnósticos, medicamentos e suas relações | Interação medicamentosa e diagnósticos em cadeia são perguntas sobre **relacionamentos**: segue arestas em vez de auto-JOINs. |

### Chaves do Redis
| Chave | Tipo | TTL |
|---|---|---|
| `sessao:{token}` | STRING (JSON do médico) | 30 min (renova a cada acesso) |
| `fila:espera` | SORTED SET `cpf -> score` | — |
| `fila:info:{cpf}` | HASH `nome, prioridade, chegada` | — |
| `atendimento:{cpf}` | STRING (CRM do médico) | 1 h |
| `cache:agenda:hoje` | STRING (JSON) | 5 min (apagado ao finalizar uma consulta — invalidação) |
| `contador:atendidos_hoje` | STRING (INCR) | — |

Score da fila = `peso_prioridade × 10¹⁰ + timestamp_chegada` → Emergência (0) passa na frente de Urgente (1) e Normal (2); empate decide quem chegou antes.

### Exemplo de documento (MongoDB `pacientes`)
```json
{ "cpf": "333.333.333-33", "nome": "Carlos Oliveira", "nascimento": "1975-11-02",
  "alergias": ["Penicilina"], "condicoes_cronicas": ["Fibrilação atrial"],
  "uso_continuo": ["Varfarina"],
  "exames": [{ "tipo": "INR", "valor": 2.6, "data": "2026-10-01" }],
  "prontuario": { "consultas": [
    { "data": "...", "medico": {"crm": "CRM-PB 1002", "nome": "Dr. Bruno Souza"},
      "queixa": "...", "diagnosticos": ["I48"],
      "prescricoes": [{"medicamento": "Varfarina", "posologia": "5mg 1x/dia"}] } ] } }
```

### Grafo (Neo4j)
```
(:Medico)-[:ATENDEU]->(:Paciente)-[:DIAGNOSTICADO_COM]->(:Diagnostico)-[:CORRELACIONADO_COM]->(:Diagnostico)
(:Paciente)-[:USA]->(:Medicamento)-[:CONTRAINDICADO_COM {risco, motivo}]-(:Medicamento)
(:Paciente)-[:ALERGICO_A]->(:Medicamento)-[:TRATA]->(:Diagnostico)
```

Alerta de interação com o que o paciente já usa:
```cypher
MATCH (p:Paciente {cpf:$cpf})-[:USA]->(atual:Medicamento)-[c:CONTRAINDICADO_COM]-(novo:Medicamento)
WHERE novo.nome IN $novos
RETURN novo.nome, atual.nome, c.risco, c.motivo
```
Diagnósticos correlacionados em cadeia (até N saltos):
```cypher
MATCH caminho = (d:Diagnostico {cid:$cid})-[:CORRELACIONADO_COM*1..2]->(o:Diagnostico)
RETURN o.nome, length(caminho) AS saltos
```

## Telas mínimas do enunciado (Estudo de Caso 03) → onde estão no app
| Tela exigida | Menu do app | Bancos |
|---|---|---|
| 1. Prontuário & Atendimento Médico (histórico, edição flexível de diagnósticos, upload de laudos) | **Prontuário & Atendimento Médico** | MongoDB (+ Neo4j sincroniza a edição) |
| 2. Painel da Recepção Virtual & Fila (pacientes aguardando e agenda do dia) | **Painel da Recepção Virtual & Fila** | Redis (Sorted Set + cache da agenda) |
| 3. Mapeamento Clínico & Alertas de Segurança (teia de diagnósticos, alertas de prescrição e do histórico) | **Mapeamento Clínico & Alertas de Segurança** | Neo4j |
| 4. Finalização da Consulta (receita/laudo no MongoDB e status da fila no Redis) | **Finalização da Consulta** | MongoDB + Neo4j + Redis |

Extras: **Painel dos Bancos** (log de cada comando nos 3 bancos) e **Comparativo dos bancos** (forte/fraco, Cypher × SQL, simular reinício do Redis).

## Fluxo da demo (os 3 bancos juntos)
1. **Login** → valida no Mongo, cria token no Redis com TTL (contagem na barra lateral).
2. **Painel da Recepção Virtual & Fila** → check-in (`ZADD`), fila por prioridade, agenda com cache (MISS/HIT), "Chamar próximo" (`ZPOPMIN`) já abre o prontuário.
3. **Prontuário & Atendimento Médico** → documento do paciente no Mongo, anexa laudo, ✏️ edita um diagnóstico antigo.
4. **Prescrever** *Carlos Oliveira* + *AAS* → o Neo4j alerta sangramento com a Varfarina.
5. **Mapeamento Clínico & Alertas de Segurança** → teia do paciente, alertas do histórico, cadeia de diagnósticos e histórico epidemiológico.
6. **Finalização da Consulta** → emite receita/laudo (Mongo), grafo aprende `USA`/`DIAGNOSTICADO_COM` (Neo4j), paciente sai da fila e o contador sobe (Redis); a fila atualizada aparece na hora.
7. **Painel dos Bancos** → log com os comandos reais dos três bancos.

Extras para a arguição: **auditoria LGPD** no prontuário, **⏱️ Simular expiração da sessão** (barra lateral) e **💥 Simular reinício do Redis** (Comparativo).

## Como rodar
```bash
docker compose up -d                 # sobe Mongo, Redis e Neo4j
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env               # (Linux/Mac: cp)
python -m scripts.seed               # cria índices/constraints e popula os 3 bancos
streamlit run app.py
```
Login de teste: `ana@clinica.com` / `123` (também `bruno@clinica.com`, `carla@clinica.com`).
Neo4j Browser: http://localhost:7474 (neo4j / senha12345) → `MATCH (n) RETURN n`.

## Estrutura
```
app.py               # Streamlit: telas e orquestração dos 3 bancos
db/mongo.py          # MongoDB: prontuários, profissionais, laudos, agenda
db/redis_client.py   # Redis: sessão, fila (Sorted Set), atendimento, cache
db/neo4j_client.py   # Neo4j: grafo clínico, alertas e epidemiologia (Cypher)
db/oplog.py          # log dos comandos de cada banco (Painel dos Bancos)
scripts/seed.py      # carga inicial + índices/constraints nos 3 bancos
docs/divisao.md      # divisão da apresentação entre o grupo
docs/roteiro-apresentacao.md  # roteiro de 10–15 min, demo e vídeo
docs/deploy.md       # como colocar online (Streamlit Cloud + Atlas + Redis Cloud + AuraDB)
```
