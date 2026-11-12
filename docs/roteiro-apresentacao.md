# Roteiro da defesa oral: 10 minutos, 5 integrantes

O enunciado define **até 10 minutos por grupo**, seguidos da arguição individual. A ordem segue o item 6.1 do enunciado: Introdução → Arquitetura & Modelagem → Demonstração → Arguição.
Regra de ouro: toda afirmação vem acompanhada de algo na tela (slide, app ou código).

| Tempo | Quem | Parte do enunciado | Slides / tela |
|---|---|---|---|
| 0:00–1:30 | **Integrante 1** | Introdução e problema de negócio | Capa, Problema |
| 1:30–2:30 | **Integrante 1** | Arquitetura (visão geral) | Arquitetura, Decisões |
| 2:30–3:30 | **Integrante 2** | Modelagem: MongoDB | MongoDB |
| 3:30–4:30 | **Integrante 3** | Modelagem: Redis | Redis |
| 4:30–5:30 | **Integrante 4** | Modelagem: Neo4j e Cypher | Neo4j |
| 5:30–9:30 | **Integrante 5** (no teclado) + 2, 3 e 4 narrando a sua tela | Demonstração prática no Streamlit | Slide Demo → app |
| 9:30–10:00 | **Integrante 5** | Fechamento | Obrigado |
| depois | todos | Arguição técnica (5–7 min) | slides de apêndice |

Antes de começar: bancos no ar, `python -m scripts.seed` rodado, app logado em uma aba e **Painel dos Bancos** aberto em outra.

---

## Integrante 1: abertura, problema e arquitetura (2:30)
**Domina:** `README.md`, `docker-compose.yml`, `db/config.py`

> “Boa noite. Somos o grupo Pizza de Sorvete: [nomes]. Escolhemos o Estudo de Caso 03, uma plataforma de telemedicina e gestão de prontuários.
> Numa clínica remota o paciente faz check-in, espera numa fila por prioridade, o médico abre o prontuário, prescreve e emite a receita. Nesse fluxo aparecem três tipos de dado bem diferentes: o **prontuário**, que é permanente e muda de formato de paciente para paciente; a **fila e o login**, que são temporários e mudam a cada segundo; e a **segurança da prescrição**, que é uma pergunta sobre relações entre remédios, doenças e pacientes.
> Um banco só faria tudo mal. Por isso usamos persistência poliglota: o Streamlit orquestra o MongoDB, o Redis e o Neo4j, cada um pelo seu driver. O que é permanente vai para o MongoDB, o que é temporário e rápido vai para o Redis, e o que é relação vai para o Neo4j.”

**Perguntas prováveis**
- *Por que não um banco relacional?* O prontuário tem campos variáveis (INR do cardíaco, semanas da gestante); a fila precisa de ordenação atômica em memória; e as perguntas de interação viram cadeias de JOIN.
- *Como os bancos se conectam?* O `app.py` usa `db/mongo.py`, `db/redis_client.py` e `db/neo4j_client.py`. As credenciais vêm do `.env` ou dos Secrets, nunca do código.

## Integrante 2: MongoDB (1:00 + tela de prontuário na demo)
**Domina:** `db/mongo.py`, a parte do Mongo em `scripts/seed.py`

> “No MongoDB fica o prontuário eletrônico em JSON flexível. O Carlos tem `INR` nos exames, a Maria tem `semanas_gestacao`, e nenhum dos dois exigiu mudança de esquema. Cada consulta nova entra com `$push` em `prontuario.consultas`, sem reescrever o documento. A edição flexível de diagnóstico usa `$set` posicional e guarda o histórico em `alteracoes`. Os laudos ficam na coleção `laudos`, o cadastro de médicos e especialidades em `profissionais`, e todo acesso vai para `auditoria`, pensando na LGPD. Os índices são `cpf` único, texto no nome e laudos por paciente e data.”

**Na demo, narra:** Prontuário (JSON, anexar laudo, ✏️ editar diagnóstico).

**Perguntas prováveis**
- *O array de consultas cresce sem limite?* O documento tem limite de 16 MB. Para um volume real, as consultas iriam para uma coleção própria com referência ao `cpf`.
- *Por que o prontuário não fica no Redis?* Porque é permanente e sensível. O Redis vive na memória e não é a fonte da verdade.

## Integrante 3: Redis (1:00 + tela da recepção na demo)
**Domina:** `db/redis_client.py`

> “No Redis fica o que é temporário. O login gera `sessao:{token}` com TTL de 30 minutos, renovado a cada clique. A fila é o Sorted Set `fila:espera`, com score = peso da prioridade × 10¹⁰ + hora de chegada, então uma emergência passa na frente de quem chegou antes. O médico chama com `ZPOPMIN`, que é atômico: dois médicos nunca pegam o mesmo paciente. A consulta ativa fica em `atendimento:{cpf}` com TTL de 1 hora. A agenda do dia usa cache-aside: lê do Redis; se não houver, busca no Mongo e guarda por 5 minutos. Quando a consulta é finalizada, essa chave é apagada (invalidação).”

**Na demo, narra:** Recepção (check-in Urgente passa na frente, cache MISS → HIT, chamar próximo) e o botão de simular expiração da sessão.

**Perguntas prováveis**
- *O que acontece quando o TTL expira?* A chave some sozinha e o médico volta ao login.
- *Por que a fila não fica no Mongo?* Ela muda o tempo todo e precisa de ordenação e retirada atômicas em memória.
- *E se o Redis cair?* Perde-se a fila do dia. Nenhum prontuário se perde.

## Integrante 4: Neo4j e Cypher (1:00 + tela de mapeamento na demo)
**Domina:** `db/neo4j_client.py`, a parte do grafo em `scripts/seed.py`

> “O Neo4j guarda o grafo clínico: `(:Paciente)`, `(:Medico)`, `(:Diagnostico)` e `(:Medicamento)`, ligados por `USA`, `ALERGICO_A`, `DIAGNOSTICADO_COM`, `ATENDEU`, `CONTRAINDICADO_COM` e `CORRELACIONADO_COM`. Para checar uma prescrição, o Cypher parte do paciente, segue `USA` até o remédio que ele já toma e depois `CONTRAINDICADO_COM` até o remédio novo. Ele não varre tabela nenhuma: é index-free adjacency, cada nó aponta direto para os vizinhos. Com o mesmo grafo mapeamos diagnósticos em cadeia com `*1..N` saltos e o histórico epidemiológico.”

**Na demo, narra:** alerta Carlos + AAS e a tela Mapeamento Clínico (teia, alertas do histórico, cadeia, epidemiologia).

**Perguntas prováveis**
- *Escreva a consulta de interação.* `MATCH (p:Paciente {cpf:$cpf})-[:USA]->(a:Medicamento)-[c:CONTRAINDICADO_COM]-(n:Medicamento) WHERE n.nome IN $novos RETURN n.nome, a.nome, c.risco`
- *O que é index-free adjacency?* Cada nó guarda ponteiros para os relacionamentos, então percorrer não depende de índice global nem de JOIN.

## Integrante 5: demonstração e fechamento (4:30)
**Domina:** `app.py`, `scripts/seed.py`, `docs/deploy.md`

Roteiro no teclado (o dono de cada banco narra a sua parte):
1. **0:00** Login `ana@clinica.com` / `123` → mostrar o TTL da sessão na barra lateral. *(Integrante 3)*
2. **0:20** **Painel da Recepção Virtual & Fila** → check-in de *Paulo Ramos* como **Urgente**: ele passa na frente. Recarregar: agenda MISS → HIT. *(Integrante 3)*
3. **1:00** **Chamar próximo** → abre o **Prontuário & Atendimento Médico** sozinho: JSON, anexar um laudo, ✏️ editar um diagnóstico antigo. *(Integrante 2)*
4. **1:50** Trocar para *Carlos Oliveira* → prescrever **AAS** → alerta de sangramento com a Varfarina. *(Integrante 4)*
5. **2:20** **Mapeamento Clínico & Alertas de Segurança** → teia do Carlos e cadeia de diagnósticos. *(Integrante 4)*
6. **2:50** Voltar, preencher a queixa → **Ir para a Finalização** → **Finalização da Consulta**: receita com posologia → **Emitir e finalizar** → checklist dos 3 bancos e a fila atualizada. *(Integrante 5)*
7. **3:40** Aba **Painel dos Bancos** → log com os comandos reais do Mongo, do Redis e do Neo4j. *(Integrante 5)*
8. **4:10** Fechamento: *“MongoDB guarda a verdade, Redis guarda o agora, Neo4j guarda as ligações. Obrigado.”*

**Perguntas prováveis**
- *E se o Neo4j cair na finalização?* O Mongo grava primeiro (fonte da verdade); o checklist mostra a falha e o grafo é atualizado depois (consistência eventual).
- *Como o código trata erros?* A função `erro_amigavel()` identifica qual banco caiu e o que deixa de funcionar, em vez de mostrar o traceback.

---

## Perguntas que TODOS precisam saber responder
- Por que o prontuário não fica no Redis? → é permanente; o Redis é memória.
- Por que a fila não fica no Mongo? → muda o tempo todo e precisa ordenar e ser atômica.
- O que é TTL? → tempo de vida da chave; quando expira, a chave some sozinha.
- O que é cache-aside e invalidação? → lê do cache; se não tem, busca no banco e guarda; quando o dado muda, apaga a cópia.
- O que é index-free adjacency? → cada nó aponta direto para os vizinhos.
- O que é persistência poliglota? → usar o banco certo para cada tipo de dado no mesmo sistema.

## Plano B
- Internet caiu: `docker compose up -d` + `python -m scripts.seed` + `streamlit run app.py` no notebook.
- App travou no meio: recarregar a página (a sessão dura 30 min no Redis) ou rodar o seed de novo.
- **Não usem as credenciais do AuraDB que vieram no enunciado para o seed**: ele apaga o grafo inteiro.
