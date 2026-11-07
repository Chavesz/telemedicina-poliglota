"""MongoDB — banco orientado a DOCUMENTOS.

Por que aqui? Produtos têm especificações diferentes entre si (um notebook tem
'ram', uma camisa tem 'tamanho'). Documento JSON aceita esse esquema flexível
sem ALTER TABLE. Pedidos também são documentos: o pedido guarda uma "foto"
dos itens e preços no momento da compra (histórico permanente).
"""
from datetime import datetime, timezone
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
from db.config import MONGO_URI, MONGO_DB

_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
db = _client[MONGO_DB]
produtos = db["produtos"]
clientes = db["clientes"]
pedidos = db["pedidos"]


def ping() -> bool:
    _client.admin.command("ping")
    return True


def buscar_produtos(texto: str = "", categoria: str | None = None) -> list[dict]:
    filtro: dict = {}
    if texto:
        filtro["$text"] = {"$search": texto}          # usa o índice de texto
    if categoria:
        filtro["categoria"] = categoria
    docs = list(produtos.find(filtro).limit(50))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


def obter_produto(sku: str) -> dict | None:
    d = produtos.find_one({"sku": sku})
    if d:
        d["_id"] = str(d["_id"])
    return d


def categorias() -> list[str]:
    return sorted(produtos.distinct("categoria"))


def autenticar(email: str, senha: str) -> dict | None:
    # Demo acadêmica: senha em texto. Em produção usar hash (bcrypt).
    return clientes.find_one({"email": email, "senha": senha}, {"senha": 0})


def salvar_pedido(cliente: dict, itens: list[dict]) -> str:
    total = round(sum(i["preco"] * i["qtd"] for i in itens), 2)
    doc = {
        "cliente": {"id": cliente["cliente_id"], "nome": cliente["nome"], "email": cliente["email"]},
        "itens": itens,                       # snapshot embutido (desnormalizado)
        "total": total,
        "status": "PAGO",
        "criado_em": datetime.now(timezone.utc),
    }
    return str(pedidos.insert_one(doc).inserted_id)


def pedidos_do_cliente(cliente_id: str) -> list[dict]:
    return list(pedidos.find({"cliente.id": cliente_id}).sort("criado_em", DESCENDING))
