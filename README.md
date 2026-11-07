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

## Fluxo da demo (os 3 bancos juntos)
1. **Login** → valida no Mongo, cria token no Redis com TTL (aparece a contagem na barra lateral).
2. **Recepção & Fila** → check-in (`ZADD`), fila ordenada, "Chamar próximo" (`ZPOPMIN`), agenda com cache (HIT/MISS e tempo).
3. **Prontuário** → abre o documento do paciente no Mongo, anexa laudo.
4. **Prescrever** → escolher *Carlos Oliveira* + *AAS* ou *Ibuprofeno* → Neo4j mostra alerta de sangramento com Varfarina.
5. **Finalizar** → consulta gravada no Mongo, grafo ganha `DIAGNOSTICADO_COM`/`USA`, Redis tira da fila e incrementa o contador.
6. **Mapa Clínico** → desenho da teia do paciente e cadeia de diagnósticos.
7. **Mapa Clínico → Histórico epidemiológico** → diagnósticos mais comuns, comorbidades e pacientes com o mesmo CID.
8. **Painel dos Bancos** → contagens dos 3 bancos, chaves do Redis com TTL e o **log de cada comando** executado na demo.

Extras para a arguição: **✏️ Editar diagnóstico** numa consulta antiga (`$set` posicional + histórico de alterações + grafo sincronizado), **auditoria LGPD** no prontuário e o botão **⏱️ Simular expiração da sessão** na barra lateral.

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
```
