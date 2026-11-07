"""Telemedicina Poliglota — Streamlit orquestrando MongoDB + Redis + Neo4j.

Rodar:  streamlit run app.py
Fluxo da demo:
  Login (token no Redis c/ TTL) -> Recepção: fila de espera (Redis Sorted Set)
  -> Chamar paciente -> Prontuário (Mongo) -> Prescrever: alertas (Neo4j)
  -> Finalizar: grava consulta (Mongo) + atualiza grafo (Neo4j) + tira da fila (Redis)
"""
import time
import streamlit as st
from db import mongo, redis_client as rc, neo4j_client as gc

st.set_page_config(page_title="Telemedicina Poliglota", page_icon="🩺", layout="wide")


def status_bancos() -> dict[str, str | None]:
    """Testa cada banco; None = ok, senão a mensagem de erro."""
    res = {}
    for nome, fn in [("MongoDB", mongo.ping), ("Redis", rc.ping), ("Neo4j", gc.ping)]:
        try:
            fn(); res[nome] = None
        except Exception as e:  # noqa: BLE001 — mostrar qualquer falha na tela
            res[nome] = str(e)[:120]
    return res


# ------------------------------------------------------------------ login
def tela_login():
    st.title("🩺 Telemedicina Poliglota")
    st.caption("O login gera um token guardado no **Redis** com TTL de 30 min.")
    with st.form("login"):
        email = st.text_input("E-mail", "ana@clinica.com")
        senha = st.text_input("Senha", "123", type="password")
        if st.form_submit_button("Entrar"):
            try:
                med = mongo.autenticar(email, senha)
            except Exception as e:
                st.error(f"MongoDB indisponível: {e}"); return
            if not med:
                st.error("Credenciais inválidas."); return
            st.session_state.token = rc.criar_sessao(med)
            st.rerun()


def medico_logado() -> dict | None:
    token = st.session_state.get("token")
    if not token:
        return None
    try:
        return rc.obter_sessao(token)
    except Exception as e:
        st.error(f"Redis indisponível: {e}")
        return None


# ------------------------------------------------------------------ recepção
def agenda_com_cache() -> tuple[list[dict], str, float]:
    t0 = time.perf_counter()
    agenda = rc.cache_get("cache:agenda:hoje")
    origem = "Redis (cache HIT)"
    if agenda is None:
        agenda = mongo.agenda_do_dia()
        rc.cache_set("cache:agenda:hoje", agenda, rc.TTL_AGENDA)
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
    st.dataframe(fila, use_container_width=True, hide_index=True)

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
        st.dataframe(rc.em_atendimento(), use_container_width=True, hide_index=True)

    st.subheader("Agenda do dia")
    agenda, origem, ms = agenda_com_cache()
    st.caption(f"origem: **{origem}** · {ms:.1f} ms · TTL {rc.ttl('cache:agenda:hoje')} s")
    st.dataframe(agenda, use_container_width=True, hide_index=True)


# ------------------------------------------------------------------ prontuário
def selecionar_paciente() -> dict | None:
    pacs = mongo.listar_pacientes()
    cpfs = [p["cpf"] for p in pacs]
    nomes = {p["cpf"]: p["nome"] for p in pacs}
    atual = st.session_state.get("paciente")
    idx = cpfs.index(atual) if atual in cpfs else 0
    cpf = st.selectbox("Paciente", cpfs, index=idx, format_func=lambda c: f"{nomes[c]} ({c})")
    st.session_state.paciente = cpf
    return mongo.obter_paciente(cpf)


def tela_prontuario(med):
    st.header("📋 Prontuário & Atendimento (MongoDB)")
    pac = selecionar_paciente()
    if not pac:
        return
    a, b = st.columns([2, 1])
    with a:
        st.subheader(pac["nome"])
        st.write(f"Nascimento: {pac['nascimento']} · Alergias: {', '.join(pac.get('alergias', [])) or 'nenhuma'}")
        consultas = pac.get("prontuario", {}).get("consultas", [])
        st.markdown(f"**Histórico** ({len(consultas)} consultas)")
        for c in reversed(consultas):
            with st.container(border=True):
                st.write(f"{str(c['data'])[:16]} — {c['medico']['nome']} — {c.get('queixa', '')}")
                st.caption(f"CID: {', '.join(c.get('diagnosticos', []))} · "
                           f"Rx: {', '.join(p['medicamento'] for p in c.get('prescricoes', []))}")
    with b:
        st.markdown("**Documento JSON (esquema flexível)**")
        st.json(pac, expanded=False)
        st.markdown("**Laudos anexados**")
        up = st.file_uploader("Anexar laudo/exame", type=["pdf", "png", "jpg"])
        if up and st.button("Salvar laudo no Mongo"):
            mongo.anexar_laudo(pac["cpf"], up.name, up.getvalue(), up.type)
            st.success("Laudo salvo.")
        for l in mongo.laudos_do_paciente(pac["cpf"]):
            st.caption(f"📎 {l['arquivo']} ({l['tamanho'] // 1024} KB)")

    st.divider()
    st.subheader("🩻 Nova consulta")
    diag = {d["cid"]: d["nome"] for d in gc.diagnosticos()}
    queixa = st.text_input("Queixa principal")
    cids = st.multiselect("Diagnósticos (CID)", list(diag), format_func=lambda c: f"{c} — {diag[c]}")
    meds = st.multiselect("Prescrever medicamentos", gc.medicamentos())
    obs = st.text_area("Observações")

    # Alerta em tempo real vindo do grafo
    if meds:
        alertas = gc.alertas_prescricao(pac["cpf"], meds)
        if alertas:
            st.error(f"⚠️ {len(alertas)} alerta(s) de segurança detectado(s) pelo Neo4j")
            st.dataframe(alertas, use_container_width=True, hide_index=True)
        else:
            st.success("✅ Nenhuma interação ou alergia encontrada no grafo.")

    if st.button("Finalizar consulta e emitir receita", type="primary", disabled=not queixa):
        try:
            rx = [{"medicamento": m, "posologia": "conforme orientação"} for m in meds]
            mongo.registrar_consulta(pac["cpf"], med, queixa, cids, rx, obs)        # 1. prontuário
            gc.registrar_atendimento(pac["cpf"], pac["nome"], med["crm"], cids, meds)  # 2. grafo
            rc.finalizar_atendimento(pac["cpf"])                                  # 3. fila
            st.success("Consulta salva no MongoDB, grafo atualizado no Neo4j e fila atualizada no Redis.")
            st.code("RECEITA\n" + f"Paciente: {pac['nome']}\nMédico: {med['nome']} ({med['crm']})\n"
                    + "\n".join(f"- {m}" for m in meds))
        except Exception as e:
            st.error(f"Falha ao finalizar: {e}")


# ------------------------------------------------------------------ grafo
def tela_mapa_clinico(med):
    st.header("🧠 Mapeamento Clínico & Alertas (Neo4j)")
    pac = selecionar_paciente()
    if not pac:
        return
    arestas = gc.teia_paciente(pac["cpf"])
    cores = {"USA": "blue", "ALERGICO_A": "red", "DIAGNOSTICADO_COM": "darkgreen", "ATENDEU": "gray"}
    if arestas:
        dot = ["digraph G { rankdir=LR; node [shape=box, style=rounded];"]
        for a in arestas:
            dot.append(f'"{a["origem"]}" -> "{a["destino"]}" [label="{a["rel"]}", color={cores.get(a["rel"], "black")}];')
        dot.append("}")
        st.graphviz_chart("\n".join(dot))

    st.subheader("Diagnósticos correlacionados em cadeia")
    diag = {d["cid"]: d["nome"] for d in gc.diagnosticos()}
    cid = st.selectbox("Diagnóstico de partida", list(diag), format_func=lambda c: f"{c} — {diag[c]}")
    prof = st.slider("Profundidade (saltos)", 1, 4, 2)
    st.dataframe(gc.diagnosticos_correlacionados(cid, prof), use_container_width=True, hide_index=True)

    with st.expander("Cypher usado"):
        st.code(gc.CYPHER_INTERACAO_USO_ATUAL.strip(), language="cypher")
        st.code("MATCH caminho = (d:Diagnostico {cid:$cid})-[:CORRELACIONADO_COM*1..2]->(o)\n"
                "RETURN o.nome, length(caminho) AS saltos", language="cypher")


# ------------------------------------------------------------------ main
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
        pagina = st.radio("Navegação", ["Recepção & Fila", "Prontuário & Atendimento", "Mapa Clínico"])
        if st.button("Sair"):
            rc.encerrar_sessao(st.session_state.token)
            st.session_state.pop("token"); st.rerun()

    {"Recepção & Fila": tela_recepcao, "Prontuário & Atendimento": tela_prontuario,
     "Mapa Clínico": tela_mapa_clinico}[pagina](med)


main()
