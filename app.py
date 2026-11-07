"""Loja Poliglota — Streamlit orquestrando MongoDB + Redis + Neo4j.

Rodar:  streamlit run app.py
Fluxo da demo: Login (Redis) -> Catálogo (Mongo + cache Redis) -> Carrinho (Redis)
               -> Recomendações (Neo4j) -> Checkout (Mongo + Neo4j + limpa Redis)
"""
import time
import streamlit as st
from db import mongo, redis_client as rc, neo4j_client as gc

st.set_page_config(page_title="Loja Poliglota", page_icon="🛒", layout="wide")


# ------------------------------------------------------------------ status
def status_bancos() -> dict[str, str | None]:
    """Testa cada banco; retorna None se ok ou a mensagem de erro."""
    res = {}
    for nome, fn in [("MongoDB", mongo.ping), ("Redis", rc.ping), ("Neo4j", gc.ping)]:
        try:
            fn(); res[nome] = None
        except Exception as e:  # noqa: BLE001 — queremos mostrar qualquer falha
            res[nome] = str(e)[:120]
    return res


# ------------------------------------------------------------------ login
def tela_login():
    st.title("🛒 Loja Poliglota")
    st.caption("Login gera um token salvo no **Redis** com TTL de 30 min.")
    with st.form("login"):
        email = st.text_input("E-mail", "ana@demo.com")
        senha = st.text_input("Senha", "123", type="password")
        if st.form_submit_button("Entrar"):
            try:
                cli = mongo.autenticar(email, senha)
            except Exception as e:
                st.error(f"MongoDB indisponível: {e}"); return
            if not cli:
                st.error("Credenciais inválidas."); return
            cli.pop("_id", None)
            st.session_state.token = rc.criar_sessao(cli)
            st.rerun()


def usuario_logado() -> dict | None:
    token = st.session_state.get("token")
    if not token:
        return None
    try:
        return rc.obter_sessao(token)
    except Exception as e:
        st.error(f"Redis indisponível: {e}")
        return None


# ------------------------------------------------------------------ catálogo
def produto_com_cache(sku: str) -> tuple[dict | None, str]:
    """Cache-aside: tenta Redis; se não houver, lê Mongo e grava no Redis."""
    chave = f"cache:produto:{sku}"
    if (p := rc.cache_get(chave)):
        return p, "Redis (cache HIT)"
    p = mongo.obter_produto(sku)
    if p:
        rc.cache_set(chave, p)
    return p, "MongoDB (cache MISS)"


def tela_catalogo(cli):
    st.header("📦 Catálogo")
    c1, c2 = st.columns([3, 1])
    termo = c1.text_input("Buscar", placeholder="notebook, jbl, livro...")
    cats = ["(todas)"] + mongo.categorias()
    cat = c2.selectbox("Categoria", cats)
    cat = None if cat == "(todas)" else cat

    chave = f"cache:busca:{termo.lower()}:{cat}"
    t0 = time.perf_counter()
    lista = rc.cache_get(chave)
    origem = "Redis (cache HIT)"
    if lista is None:
        lista = mongo.buscar_produtos(termo, cat)
        rc.cache_set(chave, lista)
        origem = "MongoDB (cache MISS)"
    ms = (time.perf_counter() - t0) * 1000
    st.caption(f"{len(lista)} produtos · origem: **{origem}** · {ms:.1f} ms · TTL {rc.TTL_CACHE}s")

    for p in lista:
        with st.container(border=True):
            a, b, c = st.columns([4, 1, 1])
            a.markdown(f"**{p['nome']}** · {p['marca']} · _{p['categoria']}_")
            a.json(p["specs"], expanded=False)
            b.metric("Preço", f"R$ {p['preco']:.2f}")
            if c.button("Adicionar", key=f"add{p['sku']}"):
                rc.add_carrinho(cli["cliente_id"], p["sku"])
                rc.registrar_view(p["sku"])
                st.toast(f"{p['nome']} no carrinho (Redis HINCRBY)")

    with st.expander("🔥 Mais vistos (Redis Sorted Set)"):
        for sku, score in rc.mais_vistos():
            st.write(f"{sku} — {int(score)} interações")


# ------------------------------------------------------------------ carrinho
def itens_carrinho(cli) -> list[dict]:
    itens = []
    for sku, qtd in rc.carrinho(cli["cliente_id"]).items():
        p, _ = produto_com_cache(sku)
        if p:
            itens.append({"sku": sku, "nome": p["nome"], "preco": p["preco"], "qtd": qtd})
    return itens


def tela_carrinho(cli):
    st.header("🛍️ Carrinho (Redis)")
    chave = f"carrinho:{cli['cliente_id']}"
    st.caption(f"Chave `{chave}` · HASH · TTL restante: {rc.r.ttl(chave)} s")
    itens = itens_carrinho(cli)
    if not itens:
        st.info("Carrinho vazio."); return
    for i in itens:
        a, b, c = st.columns([4, 1, 1])
        a.write(f"{i['nome']} — R$ {i['preco']:.2f}")
        nova = b.number_input("Qtd", 0, 99, i["qtd"], key=f"q{i['sku']}", label_visibility="collapsed")
        if nova != i["qtd"]:
            rc.set_qtd(cli["cliente_id"], i["sku"], nova); st.rerun()
        if c.button("Remover", key=f"rm{i['sku']}"):
            rc.set_qtd(cli["cliente_id"], i["sku"], 0); st.rerun()
    st.subheader(f"Total: R$ {sum(i['preco'] * i['qtd'] for i in itens):.2f}")
    st.code(rc.r.hgetall(chave), language="json")


# ------------------------------------------------------------------ recomendação
def tela_recomendacoes(cli):
    st.header("🧠 Recomendações (Neo4j)")
    try:
        recs = gc.recomendar_para_cliente(cli["cliente_id"])
    except Exception as e:
        st.error(f"Neo4j indisponível: {e}"); return

    st.subheader("Clientes com perfil similar também compraram")
    if recs:
        st.dataframe(recs, use_container_width=True)
    else:
        st.info("Sem histórico ainda (cold start) — mostrando populares de Informática.")
        st.dataframe(gc.populares_da_categoria("Informática"), use_container_width=True)

    st.subheader("Quem comprou isso também comprou…")
    skus = [p["sku"] for p in mongo.buscar_produtos()]
    sku = st.selectbox("Produto", skus)
    st.dataframe(gc.quem_comprou_tambem_comprou(sku), use_container_width=True)

    st.subheader("Seu grafo")
    arestas = gc.subgrafo_cliente(cli["cliente_id"])
    if arestas:
        dot = ["digraph G { rankdir=LR; node [style=filled];"]
        for a in arestas:
            dot.append(f'"{a["cliente"]}" -> "{a["produto"]}" [label="COMPROU"];')
            dot.append(f'"{a["outro"]}" -> "{a["produto"]}" [label="COMPROU", color=gray];')
        dot.append("}")
        st.graphviz_chart("\n".join(dict.fromkeys(dot)))

    with st.expander("Cypher usado"):
        st.code("""MATCH (eu:Cliente {id:$cid})-[:COMPROU]->(:Produto)<-[:COMPROU]-(similar:Cliente)
MATCH (similar)-[:COMPROU]->(rec:Produto)
WHERE NOT (eu)-[:COMPROU]->(rec)
RETURN rec.nome, count(DISTINCT similar) AS similares
ORDER BY similares DESC LIMIT 5""", language="cypher")


# ------------------------------------------------------------------ checkout
def tela_checkout(cli):
    st.header("💳 Checkout")
    itens = itens_carrinho(cli)
    if not itens:
        st.info("Carrinho vazio."); return
    st.table(itens)
    if st.button("Finalizar pedido", type="primary"):
        try:
            pid = mongo.salvar_pedido(cli, itens)                          # 1. persiste (Mongo)
            gc.registrar_compra(cli["cliente_id"], cli["nome"], itens)     # 2. grafo aprende (Neo4j)
            rc.limpar_carrinho(cli["cliente_id"])                          # 3. limpa sessão (Redis)
            st.success(f"Pedido {pid} salvo no MongoDB. Grafo atualizado. Carrinho limpo.")
            st.json(mongo.pedidos.find_one({}, sort=[("criado_em", -1)], projection={"_id": 0}), expanded=True)
        except Exception as e:
            st.error(f"Falha no checkout: {e}")

    st.subheader("Histórico de pedidos (MongoDB)")
    for p in mongo.pedidos_do_cliente(cli["cliente_id"]):
        st.write(f"{p['criado_em']:%d/%m %H:%M} — R$ {p['total']:.2f} — {len(p['itens'])} itens")


# ------------------------------------------------------------------ main
def main():
    with st.sidebar:
        st.subheader("Status dos bancos")
        for nome, erro in status_bancos().items():
            st.write(("🟢 " if erro is None else "🔴 ") + nome)
            if erro:
                st.caption(erro)

    cli = usuario_logado()
    if not cli:
        tela_login(); return

    with st.sidebar:
        st.write(f"Olá, **{cli['nome']}**")
        st.caption(f"Sessão Redis expira em {rc.ttl_sessao(st.session_state.token)} s")
        pagina = st.radio("Navegação", ["Catálogo", "Carrinho", "Recomendações", "Checkout"])
        if st.button("Sair"):
            rc.encerrar_sessao(st.session_state.token)
            st.session_state.pop("token"); st.rerun()

    {"Catálogo": tela_catalogo, "Carrinho": tela_carrinho,
     "Recomendações": tela_recomendacoes, "Checkout": tela_checkout}[pagina](cli)


main()
