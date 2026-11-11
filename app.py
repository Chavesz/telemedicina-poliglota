"""Telemedicina Poliglota — Streamlit orquestrando MongoDB + Redis + Neo4j.

Rodar:  streamlit run app.py
Fluxo da demo:
  Login (token no Redis c/ TTL) -> Recepção: fila de espera (Redis Sorted Set)
  -> Chamar paciente -> Prontuário (Mongo) -> Prescrever: alertas (Neo4j)
  -> Finalizar: grava consulta (Mongo) + atualiza grafo (Neo4j) + tira da fila (Redis)
  -> Painel dos Bancos: log de cada comando executado nos 3 bancos
"""
import time
import streamlit as st
from neo4j.exceptions import Neo4jError, ServiceUnavailable
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from db import mongo, oplog, redis_client as rc, neo4j_client as gc

st.set_page_config(page_title="Telemedicina Poliglota", page_icon="🩺", layout="wide")


def status_bancos() -> dict[str, str | None]:
    """Testa cada banco; None = ok, senão a mensagem de erro."""
    res = {}
    for nome, fn in [("MongoDB", mongo.ping), ("Redis", rc.ping), ("Neo4j", gc.ping)]:
        try:
            fn(); res[nome] = None
        except Exception as e:  # noqa: BLE001 — mostrar qualquer falha na tela
            res[nome] = str(e).splitlines()[0][:120]
    return res


def erro_amigavel(e: Exception) -> None:
    """Traduz a exceção de cada driver numa mensagem que o usuário entende."""
    if isinstance(e, PyMongoError):
        banco, efeito = "MongoDB", "prontuários, agenda e laudos ficam indisponíveis"
    elif isinstance(e, RedisError):
        banco, efeito = "Redis", "fila, sessão e cache ficam indisponíveis (o prontuário continua salvo no Mongo)"
    elif isinstance(e, (Neo4jError, ServiceUnavailable)):
        banco, efeito = "Neo4j", "alertas de interação e o mapa clínico ficam indisponíveis"
    else:
        st.error(f"Erro inesperado: {e}")
        return
    st.error(f"**{banco} não respondeu** — {efeito}. Verifique se o container está rodando "
             f"(`docker compose ps`).\n\nDetalhe técnico: `{str(e).splitlines()[0][:150]}`")


# ------------------------------------------------------------------ login
def tela_login():
    st.title("🩺 Telemedicina Poliglota")
    st.caption("O login gera um token guardado no **Redis** com TTL de 30 min.")
    if st.session_state.pop("sessao_expirou", False):
        st.warning("⏱️ Sua sessão expirou: a chave `sessao:{token}` sumiu do Redis pelo TTL. Entre de novo.")
    with st.form("login"):
        email = st.text_input("E-mail", "ana@clinica.com")
        senha = st.text_input("Senha", "123", type="password")
        if st.form_submit_button("Entrar"):
            try:
                med = mongo.autenticar(email, senha)
                if not med:
                    st.error("Credenciais inválidas."); return
                st.session_state.token = rc.criar_sessao(med)
            except Exception as e:  # noqa: BLE001
                erro_amigavel(e); return
            st.rerun()


def medico_logado() -> dict | None:
    token = st.session_state.get("token")
    if not token:
        return None
    try:
        med = rc.obter_sessao(token)
    except Exception as e:  # noqa: BLE001
        erro_amigavel(e)
        return None
    if med is None:                       # o token existia mas o TTL apagou a chave
        st.session_state.pop("token", None)
        st.session_state.sessao_expirou = True
    return med


# ------------------------------------------------------------------ recepção
def agenda_com_cache() -> tuple[list[dict], str, float]:
    """Cache-aside: tenta o Redis; se não tiver (MISS), busca no Mongo e guarda com TTL."""
    t0 = time.perf_counter()
    agenda = rc.cache_get(rc.CHAVE_AGENDA)
    origem = "Redis (cache HIT)"
    if agenda is None:
        agenda = mongo.agenda_do_dia()
        rc.cache_set(rc.CHAVE_AGENDA, agenda, rc.TTL_AGENDA)
        origem = "MongoDB (cache MISS)"
    return agenda, origem, (time.perf_counter() - t0) * 1000


def tela_recepcao(med):
    st.header("🏥 Recepção Virtual & Fila (Redis)")
    m1, m2, m3 = st.columns(3)
    fila = rc.fila()
    m1.metric("Aguardando", len(fila))
    m2.metric("Em atendimento", len(rc.em_atendimento()))
    m3.metric("Atendidos hoje", rc.atendidos_hoje())

    st.subheader("Fila de espera — Sorted Set `fila:espera`")
    st.caption("Ordenada por prioridade (Emergência > Urgente > Normal) e depois hora de chegada.")
    st.dataframe(fila, width="stretch", hide_index=True)

    c1, c2 = st.columns(2)
    with c1.form("checkin"):
        st.markdown("**Check-in de paciente**")
        pacs = {p["nome"]: p["cpf"] for p in mongo.listar_pacientes()}
        nome = st.selectbox("Paciente", list(pacs))
        prio = st.radio("Prioridade", list(rc.PESO), index=2, horizontal=True)
        if st.form_submit_button("Entrar na fila (ZADD)"):
            rc.entrar_na_fila(pacs[nome], nome, prio); st.rerun()
    with c2:
        st.markdown("**Chamar próximo**")
        st.caption("ZPOPMIN é atômico: dois médicos nunca pegam o mesmo paciente.")
        if st.button("📣 Chamar próximo paciente", type="primary"):
            cpf = rc.chamar_proximo(med["crm"])
            if cpf:
                st.session_state.paciente = cpf
                st.success("Paciente chamado — abra a aba Prontuário.")
            else:
                st.info("Fila vazia.")
        st.dataframe(rc.em_atendimento(), width="stretch", hide_index=True)

    st.subheader("Agenda do dia")
    agenda, origem, ms = agenda_com_cache()
    st.caption(f"origem: **{origem}** · {ms:.1f} ms · TTL {rc.ttl(rc.CHAVE_AGENDA)} s "
               "· recarregue a página para ver o HIT do cache")
    st.dataframe(agenda, width="stretch", hide_index=True)


# ------------------------------------------------------------------ prontuário
def selecionar_paciente() -> dict | None:
    pacs = mongo.listar_pacientes()
    if not pacs:
        st.info("Nenhum paciente cadastrado. Rode `python -m scripts.seed`.")
        return None
    cpfs = [p["cpf"] for p in pacs]
    nomes = {p["cpf"]: p["nome"] for p in pacs}
    atual = st.session_state.get("paciente")
    idx = cpfs.index(atual) if atual in cpfs else 0
    cpf = st.selectbox("Paciente", cpfs, index=idx, format_func=lambda c: f"{nomes[c]} ({c})")
    st.session_state.paciente = cpf
    return mongo.obter_paciente(cpf)


def editar_diagnostico(pac: dict, med: dict, indice: int, consulta: dict, diag: dict) -> None:
    """Edição flexível de diagnóstico de uma consulta já registrada (Mongo + grafo)."""
    with st.popover("✏️ Editar diagnóstico"):
        atuais = [c for c in consulta.get("diagnosticos", []) if c in diag]
        novos = st.multiselect("CIDs desta consulta", list(diag), default=atuais,
                               format_func=lambda c: f"{c} — {diag[c]}", key=f"edit_{indice}")
        if st.button("Salvar alteração", key=f"salvar_{indice}"):
            try:
                anteriores = mongo.editar_diagnosticos(pac["cpf"], indice, novos, med)
                # Só tira do grafo o CID que não aparece em nenhuma outra consulta.
                outros = {c for i, k in enumerate(pac["prontuario"]["consultas"]) if i != indice
                          for c in k.get("diagnosticos", [])}
                removidos = [c for c in anteriores if c not in novos and c not in outros]
                adicionados = [c for c in novos if c not in anteriores]
                gc.atualizar_diagnosticos(pac["cpf"], removidos, adicionados)
                mongo.registrar_acesso(pac["cpf"], med, f"editou diagnóstico: {anteriores} → {novos}")
                st.session_state.msg = "Diagnóstico atualizado no MongoDB e sincronizado no Neo4j."
                st.rerun()
            except Exception as e:  # noqa: BLE001
                erro_amigavel(e)


def tela_prontuario(med):
    st.header("📋 Prontuário & Atendimento (MongoDB)")
    pac = selecionar_paciente()
    if not pac:
        return
    if msg := st.session_state.pop("msg", None):
        st.success(msg)

    # LGPD: registra uma vez por paciente aberto nesta sessão
    vistos = st.session_state.setdefault("acessos_registrados", set())
    if pac["cpf"] not in vistos:
        mongo.registrar_acesso(pac["cpf"], med, "abriu prontuário")
        vistos.add(pac["cpf"])

    diag = {d["cid"]: d["nome"] for d in gc.diagnosticos()}
    a, b = st.columns([2, 1])
    with a:
        st.subheader(pac["nome"])
        st.write(f"Nascimento: {pac['nascimento']} · Alergias: {', '.join(pac.get('alergias', [])) or 'nenhuma'}")
        consultas = pac.get("prontuario", {}).get("consultas", [])
        st.markdown(f"**Histórico** ({len(consultas)} consultas)")
        for i in reversed(range(len(consultas))):
            c = consultas[i]
            with st.container(border=True):
                st.write(f"{str(c['data'])[:16]} — {c['medico']['nome']} — {c.get('queixa', '')}")
                st.caption(f"CID: {', '.join(c.get('diagnosticos', [])) or '—'} · "
                           f"Rx: {', '.join(p['medicamento'] for p in c.get('prescricoes', [])) or '—'}")
                if c.get("alteracoes"):
                    ult = c["alteracoes"][-1]
                    st.caption(f"✏️ alterado por {ult['por']}: {ult['de']} → {ult['para']}")
                editar_diagnostico(pac, med, i, c, diag)
    with b:
        st.markdown("**Documento JSON (esquema flexível)**")
        st.json(pac, expanded=False)
        st.markdown("**Laudos anexados**")
        up = st.file_uploader("Anexar laudo/exame", type=["pdf", "png", "jpg"])
        if up and st.button("Salvar laudo no Mongo"):
            mongo.anexar_laudo(pac["cpf"], up.name, up.getvalue(), up.type)
            mongo.registrar_acesso(pac["cpf"], med, f"anexou laudo {up.name}")
            st.success("Laudo salvo.")
        for l in mongo.laudos_do_paciente(pac["cpf"]):
            st.caption(f"📎 {l['arquivo']} ({l['tamanho'] // 1024} KB)")
        with st.expander("🔐 Auditoria de acessos (LGPD)"):
            st.dataframe([{"quando": str(x["em"])[:19], "médico": x["medico"], "ação": x["acao"]}
                          for x in mongo.acessos_do_paciente(pac["cpf"])],
                         width="stretch", hide_index=True)

    st.divider()
    st.subheader("🩻 Nova consulta")
    queixa = st.text_input("Queixa principal")
    cids = st.multiselect("Diagnósticos (CID)", list(diag), format_func=lambda c: f"{c} — {diag[c]}")
    meds = st.multiselect("Prescrever medicamentos", gc.medicamentos())
    obs = st.text_area("Observações")

    # Alerta em tempo real vindo do grafo
    if meds:
        alertas = gc.alertas_prescricao(pac["cpf"], meds)
        if alertas:
            st.error(f"⚠️ {len(alertas)} alerta(s) de segurança detectado(s) pelo Neo4j")
            st.dataframe(alertas, width="stretch", hide_index=True)
        else:
            st.success("✅ Nenhuma interação ou alergia encontrada no grafo.")

    if st.button("Finalizar consulta e emitir receita", type="primary", disabled=not queixa):
        finalizar_consulta(pac, med, queixa, cids, meds, obs)

    if etapas := st.session_state.pop("etapas", None):
        st.markdown("**O que cada banco fez ao finalizar:**")
        for banco, texto, ok in etapas:
            st.markdown(f"{'✅' if ok else '❌'} **{banco}** — {texto}")


def finalizar_consulta(pac, med, queixa, cids, meds, obs) -> None:
    """Ordem importa: o Mongo (fonte da verdade) primeiro. Se ele falhar, nada mais é feito."""
    etapas = []
    rx = [{"medicamento": m, "posologia": "conforme orientação"} for m in meds]
    try:
        mongo.registrar_consulta(pac["cpf"], med, queixa, cids, rx, obs)
        mongo.marcar_agenda_atendida(pac["nome"])
        mongo.registrar_acesso(pac["cpf"], med, "registrou consulta")
        etapas.append(("MongoDB", "consulta gravada no prontuário ($push), agenda atualizada e auditoria", True))
    except Exception as e:  # noqa: BLE001
        erro_amigavel(e)
        return
    try:
        gc.registrar_atendimento(pac["cpf"], pac["nome"], med["crm"], cids, meds)
        etapas.append(("Neo4j", "grafo ganhou ATENDEU, DIAGNOSTICADO_COM e USA", True))
    except Exception as e:  # noqa: BLE001
        etapas.append(("Neo4j", f"falhou ({str(e)[:80]}); a consulta já está salva no Mongo "
                                "(consistência eventual)", False))
    try:
        rc.finalizar_atendimento(pac["cpf"])
        rc.invalidar(rc.CHAVE_AGENDA)
        etapas.append(("Redis", "paciente saiu da fila, contador +1 e cache da agenda invalidado", True))
    except Exception as e:  # noqa: BLE001
        etapas.append(("Redis", f"falhou ({str(e)[:80]})", False))

    st.session_state.etapas = etapas
    st.session_state.msg = "Consulta finalizada. RECEITA — " + (", ".join(meds) or "sem medicamentos")
    st.rerun()


# ------------------------------------------------------------------ grafo
def tela_mapa_clinico(med):
    st.header("🧠 Mapeamento Clínico & Alertas (Neo4j)")
    aba_pac, aba_epi = st.tabs(["Paciente", "📊 Histórico epidemiológico"])

    with aba_pac:
        pac = selecionar_paciente()
        if pac:
            arestas = gc.teia_paciente(pac["cpf"])
            cores = {"USA": "blue", "ALERGICO_A": "red", "DIAGNOSTICADO_COM": "darkgreen", "ATENDEU": "gray"}
            if arestas:
                dot = ["digraph G { rankdir=LR; node [shape=box, style=rounded];"]
                for a in arestas:
                    dot.append(f'"{a["origem"]}" -> "{a["destino"]}" '
                               f'[label="{a["rel"]}", color={cores.get(a["rel"], "black")}];')
                dot.append("}")
                st.graphviz_chart("\n".join(dot))

        st.subheader("Diagnósticos correlacionados em cadeia")
        diag = {d["cid"]: d["nome"] for d in gc.diagnosticos()}
        cid = st.selectbox("Diagnóstico de partida", list(diag), format_func=lambda c: f"{c} — {diag[c]}")
        prof = st.slider("Profundidade (saltos)", 1, 4, 2)
        st.dataframe(gc.diagnosticos_correlacionados(cid, prof), width="stretch", hide_index=True)

        with st.expander("Cypher usado"):
            st.code(gc.CYPHER_INTERACAO_USO_ATUAL.strip(), language="cypher")
            st.code("MATCH caminho = (d:Diagnostico {cid:$cid})-[:CORRELACIONADO_COM*1..2]->(o)\n"
                    "RETURN o.nome, length(caminho) AS saltos", language="cypher")

    with aba_epi:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Diagnósticos mais frequentes (Neo4j)**")
            epi = gc.epidemiologia()
            st.dataframe(epi, width="stretch", hide_index=True)
            if epi:
                st.bar_chart({e["cid"]: e["pacientes"] for e in epi})
        with c2:
            st.markdown("**Comorbidades — diagnósticos que aparecem juntos**")
            st.dataframe(gc.comorbidades(), width="stretch", hide_index=True)
            st.markdown("**Mesma consulta no MongoDB (aggregation pipeline)**")
            st.dataframe(mongo.diagnosticos_mais_registrados(), width="stretch", hide_index=True)

        diag = {d["cid"]: d["nome"] for d in gc.diagnosticos()}
        cid = st.selectbox("Pacientes com o mesmo diagnóstico", list(diag), key="epi_cid",
                           format_func=lambda c: f"{c} — {diag[c]}")
        st.dataframe(gc.pacientes_com_cid(cid), width="stretch", hide_index=True)
        with st.expander("Cypher usado"):
            for q in (gc.CYPHER_EPIDEMIOLOGIA, gc.CYPHER_COMORBIDADES, gc.CYPHER_MESMO_CID):
                st.code(q.strip(), language="cypher")


# ------------------------------------------------------------------ painel dos bancos
def tela_painel_bancos(med):
    st.header("🗄️ Painel dos Bancos — o que cada banco fez")
    st.caption("Mostra o estado dos 3 bancos e cada comando executado nesta sessão. Use na demo.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("🍃 MongoDB")
        for nome, total in mongo.contagens().items():
            st.metric(nome, total)
    with c2:
        st.subheader("🟥 Redis")
        info = rc.info()
        st.metric("chaves", info["chaves"])
        st.metric("memória usada", info["memoria"])
    with c3:
        st.subheader("🔵 Neo4j")
        est = gc.estatisticas()
        st.dataframe(est["nos"], width="stretch", hide_index=True)
        st.dataframe(est["relacionamentos"], width="stretch", hide_index=True)

    st.subheader("🔑 Chaves no Redis com TTL")
    padrao = st.selectbox("Filtro", ["*", "sessao:*", "fila:*", "atendimento:*", "cache:*", "contador:*"])
    st.dataframe(rc.chaves_com_ttl(padrao), width="stretch", hide_index=True)
    st.caption("TTL -1 = não expira · número positivo = segundos até a chave sumir sozinha")

    st.subheader("📜 Log de comandos")
    bancos = st.multiselect("Bancos", ["MongoDB", "Redis", "Neo4j"], default=["MongoDB", "Redis", "Neo4j"])
    log = [o for o in oplog.ultimas() if o["banco"] in bancos]
    st.dataframe(log, width="stretch", hide_index=True, height=420)


# ------------------------------------------------------------------ comparativo
COMPARATIVO = [
    {"": "Modelo", "MongoDB": "Documento (JSON/BSON)", "Redis": "Chave-valor em memória",
     "Neo4j": "Grafo (nós + relacionamentos)"},
    {"": "Neste sistema", "MongoDB": "Prontuários, médicos, laudos, agenda, auditoria",
     "Redis": "Login (token), fila de espera, quem está em atendimento, cache da agenda, contador",
     "Neo4j": "Pacientes, remédios, diagnósticos e como se ligam"},
    {"": "Ponto forte", "MongoDB": "Esquema flexível: cada paciente tem campos diferentes; tudo num documento, sem JOIN",
     "Redis": "Microssegundos; TTL apaga sozinho; Sorted Set ordena a fila; operações atômicas",
     "Neo4j": "Seguir relações é barato (index-free adjacency); caminhos de tamanho variável"},
    {"": "Ponto fraco", "MongoDB": "Cruzar relações entre muitos documentos fica caro ($lookup)",
     "Redis": "Limitado pela RAM; se reiniciar sem persistência, perde os dados; consultas simples",
     "Neo4j": "Ruim para guardar documentos grandes e para relatórios agregados de tudo"},
    {"": "Quando usar", "MongoDB": "Dado principal, permanente e com formato variável",
     "Redis": "Dado temporário, muito acessado ou que precisa expirar",
     "Neo4j": "Quando a pergunta é sobre conexões: recomendação, rotas, interações"},
    {"": "Consistência", "MongoDB": "Atômica por documento (fonte da verdade)",
     "Redis": "Temporária por design; perder a fila do dia é aceitável",
     "Neo4j": "Transações ACID; sincronizado após o Mongo (consistência eventual)"},
]

SQL_EQUIVALENTE = """SELECT n.nome, a.nome, c.risco
FROM paciente p
JOIN paciente_usa pu   ON pu.paciente_id = p.id
JOIN medicamento a     ON a.id = pu.med_id
JOIN contraindicacao c ON c.med_a = a.id OR c.med_b = a.id
JOIN medicamento n     ON n.id = CASE WHEN c.med_a = a.id THEN c.med_b ELSE c.med_a END
WHERE p.cpf = ? AND n.nome IN (?);"""


def tela_comparativo(med):
    st.header("⚖️ Comparativo dos bancos — por que três?")
    st.caption("Persistência poliglota: cada dado vai para o banco que faz melhor aquele trabalho.")
    st.dataframe(COMPARATIVO, width="stretch", hide_index=True)

    st.subheader("A mesma pergunta em dois mundos")
    st.write("*Algum remédio novo conflita com o que este paciente já toma?*")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Cypher (Neo4j)** — segue as arestas a partir do paciente")
        st.code(gc.CYPHER_INTERACAO_USO_ATUAL.strip(), language="cypher")
    with c2:
        st.markdown("**SQL equivalente** — vários JOINs e uma tabela de ligação")
        st.code(SQL_EQUIVALENTE, language="sql")

    st.subheader("Teste: e se o Redis reiniciar?")
    st.write("Mostra na prática por que a fila fica no Redis e o prontuário no MongoDB. "
             "A sua sessão é mantida para a demo continuar.")
    if st.button("💥 Simular reinício do Redis"):
        fila_antes = len(rc.fila())
        pac_antes = mongo.contagens()["pacientes"]
        apagadas = rc.simular_queda(st.session_state.token)
        st.warning(f"Redis: {apagadas} chaves apagadas — fila {fila_antes} → {len(rc.fila())} pacientes, "
                   "cache e contadores zerados.")
        st.success(f"MongoDB: prontuários {pac_antes} → {mongo.contagens()['pacientes']}. "
                   "Nada se perdeu; os pacientes só refazem o check-in.")


# ------------------------------------------------------------------ main
PAGINAS = {
    "Recepção & Fila": tela_recepcao,
    "Prontuário & Atendimento": tela_prontuario,
    "Mapa Clínico": tela_mapa_clinico,
    "Painel dos Bancos": tela_painel_bancos,
    "Comparativo dos bancos": tela_comparativo,
}


def main():
    with st.sidebar:
        st.subheader("Status dos bancos")
        for nome, erro in status_bancos().items():
            st.write(("🟢 " if erro is None else "🔴 ") + nome)
            if erro:
                st.caption(erro)

    med = medico_logado()
    if not med:
        tela_login(); return

    with st.sidebar:
        st.write(f"**{med['nome']}** · {med['especialidade']}")
        st.caption(f"Sessão Redis expira em {rc.ttl('sessao:' + st.session_state.token)} s")
        pagina = st.radio("Navegação", list(PAGINAS))
        if st.button("⏱️ Simular expiração da sessão", help="Muda o TTL do token para 5 s"):
            rc.simular_expiracao_sessao(st.session_state.token, 5)
            st.toast("TTL da sessão agora é 5 s. Espere e clique em qualquer coisa.")
        if st.button("Sair"):
            rc.encerrar_sessao(st.session_state.token)
            st.session_state.pop("token"); st.rerun()

        st.divider()
        st.caption("**Últimos comandos**")
        for o in oplog.ultimas(5):
            st.caption(f"`{o['hora']}` **{o['banco']}** {o['comando'][:60]}")

    # Tratamento de erros centralizado: se qualquer banco cair no meio da tela,
    # o usuário vê uma mensagem clara em vez de um traceback.
    try:
        PAGINAS[pagina](med)
    except Exception as e:  # noqa: BLE001
        erro_amigavel(e)


main()
