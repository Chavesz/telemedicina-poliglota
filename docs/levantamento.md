# Levantamento: o que o professor pede × o que o projeto já tem

Base: enunciado "Projeto Final – Implementação de Bancos de Dados NoSQL" (Estudo de Caso 03).
Legenda: ✅ feito · 🟡 parcial · ❌ falta

## 1. Entregáveis obrigatórios
| Pedido | Situação | Observação |
|---|---|---|
| Repositório com código Python/Streamlit organizado e comentado | ✅ | `app.py` + `db/` (um arquivo por banco) |
| `requirements.txt` ou Docker Compose | ✅ | os dois existem |
| Scripts de carga: schemas, índices e dados nos 3 bancos | ✅ | `scripts/seed.py` |
| **Projeto rodando de verdade com os 3 bancos** | ❌ | **nunca foi executado ponta a ponta**, só compilado. Prioridade nº 1 |
| Grupo no repositório | ❌ | falta adicionar os 4 colegas no GitHub |

## 2. Responsabilidade de cada banco (Caso 03)
| Pedido | Situação | Observação |
|---|---|---|
| Mongo: prontuário JSON flexível (consultas, prescrições, exames, laudos) | ✅ | |
| Mongo: cadastro de profissionais e especialidades | 🟡 | profissionais existem; não há tela de cadastro nem coleção de especialidades |
| Redis: fila de espera com Sorted Set | ✅ | `ZADD` / `ZPOPMIN` |
| Redis: tokens de sessão das consultas ativas | ✅ | `sessao:{token}` e `atendimento:{cpf}` com TTL |
| Redis: cache das agendas do dia | ✅ | `cache:agenda:hoje`, TTL 5 min |
| Neo4j: nós Paciente, Diagnostico, Medicamento, Medico | ✅ | |
| Neo4j: interações medicamentosas (contraindicação cruzada) | ✅ | 3 consultas: uso atual, mesma receita e alergia |
| Neo4j: diagnósticos correlacionados em cadeia | ✅ | caminho variável `*1..N` |
| Neo4j: "histórico epidemiológico" | ✅ | aba na tela Mapeamento Clínico & Alertas de Segurança: diagnósticos mais frequentes, comorbidades e pacientes com o mesmo CID (+ aggregation equivalente no Mongo) |

## 3. Telas mínimas no Streamlit
| Tela pedida | Situação | Observação |
|---|---|---|
| Prontuário & Atendimento (histórico, edição flexível de diagnósticos, upload de laudo) | ✅ | botão "Editar diagnóstico" em cada consulta: `$set` posicional + histórico em `alteracoes` + sincroniza o grafo |
| Recepção virtual & fila (pacientes aguardando + agenda do dia via Redis) | ✅ | |
| Mapeamento clínico & alertas (teia de diagnósticos + alertas automáticos) | ✅ | grafo em graphviz (estático) |
| Finalização (laudo/receita no Mongo + status da fila no Redis) | ✅ | está dentro da tela de Prontuário; pode virar tela própria |

## 4. Critérios de nota
| Critério (peso) | Risco | O que fazer |
|---|---|---|
| Integração arquitetural (25%) | baixo | justificativas já estão no README |
| Modelagem / Cypher (20%) | baixo | incluir diagrama do grafo e das chaves Redis nos slides |
| Streamlit + **tratamento de erros** (25%) | baixo | ✅ `erro_amigavel()` identifica qual banco caiu e explica o impacto; todas as telas passam por ele; finalização trata falha de cada banco separadamente |
| Defesa oral (30%) | **alto** | todos precisam saber explicar o código; ver seção 6 |

## 5. Melhorias que valem pontos (do protótipo `docs/prototipo.html`)
- ✅ **Painel "o que cada banco fez"** no Streamlit (tela "Painel dos Bancos" + últimos comandos na barra lateral + checklist ao finalizar). O enunciado pede para mostrar "as chamadas e atualizações acontecendo nos três bancos simultaneamente" na demo. É o item extra mais importante.
- ✅ Aba **Comparativo dos bancos** (forte/fraco/quando usar/consistência, Cypher × SQL).
- ✅ Botão **simular reinício do Redis** (fila some, prontuário fica; sessão mantida).
- ✅ Botão **simular expiração da sessão** (mostra o TTL funcionando).
- 🟡 Grafo interativo (hoje é imagem estática).

## 6. Apresentação
- 🟡 Roteiro de 10–15 min e do vídeo pronto em `docs/roteiro-apresentacao.md`; faltam os slides.
- ❌ Ensaio da demo cronometrado.
- ✅ Tempo definido: **10 a 15 minutos**.
- ❌ Cada integrante estudar o seu arquivo (`docs/divisao.md`) e as perguntas prováveis.

## 6.1 Feito no branch `telemedicina-poliglota-2.0`
- Log de comandos dos 3 bancos (`db/oplog.py`) + tela **Painel dos Bancos** (contagens, chaves Redis com TTL, log filtrável).
- **Tratamento de erros** centralizado por banco.
- **Edição de diagnóstico** de consulta já registrada (Mongo + Neo4j sincronizados).
- **Histórico epidemiológico** (Cypher) e aggregation pipeline equivalente no Mongo.
- **Auditoria LGPD** (coleção `auditoria`): abrir prontuário, editar, anexar laudo e registrar consulta.
- **Invalidação de cache**: ao finalizar, a agenda vira "Atendido" no Mongo e `cache:agenda:hoje` é apagado.
- **Seed coerente**: o prontuário no Mongo agora tem as mesmas consultas que o grafo.
- Botão **simular expiração da sessão**.

## 6.2 Feito em 11/11
- Merge do branch 2.0 testado: login, fila, prontuário, alerta, finalização nos 3 bancos e todas as telas rodam sem erro (teste automático com Mongo/Redis em memória; o Cypher ainda precisa de um Neo4j real).
- Aba Comparativo + simulação de reinício do Redis.
- Pronto para ficar online: `db/config.py` lê os Secrets do Streamlit Cloud; guia em `docs/deploy.md`.
- `requirements.txt` com versões mínimas (a fixa não instalava no Python 3.14) e parâmetro obsoleto `use_container_width` trocado.

## 6.3 Alinhamento com o enunciado final (12/11)
- Os 4 itens do menu têm exatamente os nomes das telas mínimas do Estudo de Caso 03.
- **Finalização da Consulta** virou tela própria: emite receita e/ou laudo (salvos em `documento_emitido` na consulta, no Mongo), permite baixar o documento e mostra a fila atualizada (Redis).
- **Alertas automáticos do histórico** no Mapeamento Clínico (remédios em uso que conflitam entre si ou com alergia).
- **Corpo clínico** (profissionais e especialidades do Mongo) na Recepção.
- Defesa oral: **até 10 minutos por grupo** — roteiro em `docs/roteiro-apresentacao.md`.

## 7. Observações técnicas
- O enunciado traz credenciais de um Neo4j AuraDB. Se usarem, coloquem **só no `.env`** (que não vai para o GitHub), nunca no código. Com Aura, não precisa de Docker para o Neo4j.
- Senhas estão em texto puro (aceitável para demo, mas citar na defesa que em produção seria hash/bcrypt).
- Não há testes automatizados; um teste simples do fluxo seria um diferencial.

## Ordem sugerida até 13/11
1. Rodar tudo e corrigir o que quebrar (sáb 07).
2. Tratamento de erros + edição de diagnóstico + painel "o que cada banco fez" (dom 08).
3. Aba Comparativo + simulações de queda/expiração (seg 09).
4. Slides + ensaio com o grupo (ter 10 / qua 11).
5. Ensaio final (qui 12). Apresentação sex 13/11.
