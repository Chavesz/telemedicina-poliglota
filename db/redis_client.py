"""Redis — banco CHAVE-VALOR em memória.

Por que aqui? Tudo que é temporário e precisa responder em microssegundos:
  - sessao:{token}          STRING (JSON) com TTL 30 min  -> login expira sozinho
  - carrinho:{cliente_id}   HASH sku -> qtd, TTL 24 h     -> carrinho abandonado some
  - cache:produto:{sku}     STRING (JSON) TTL 60 s        -> cache-aside do Mongo
  - cache:busca:{termo}     STRING (JSON) TTL 60 s
  - ranking:mais_vistos     SORTED SET (sku, score=views) -> contador em tempo real
"""
import json
import uuid
import redis
from db.config import REDIS_URL

r = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)

TTL_SESSAO = 30 * 60
TTL_CARRINHO = 24 * 60 * 60
TTL_CACHE = 60


def ping() -> bool:
    return r.ping()


# ---------- Sessão / token de login ----------
def criar_sessao(cliente: dict) -> str:
    token = uuid.uuid4().hex
    r.setex(f"sessao:{token}", TTL_SESSAO, json.dumps(cliente, default=str))
    return token


def obter_sessao(token: str) -> dict | None:
    dado = r.get(f"sessao:{token}")
    if dado:
        r.expire(f"sessao:{token}", TTL_SESSAO)   # sliding expiration
        return json.loads(dado)
    return None


def ttl_sessao(token: str) -> int:
    return r.ttl(f"sessao:{token}")


def encerrar_sessao(token: str) -> None:
    r.delete(f"sessao:{token}")


# ---------- Carrinho ----------
def _k_cart(cid: str) -> str:
    return f"carrinho:{cid}"


def add_carrinho(cid: str, sku: str, qtd: int = 1) -> None:
    pipe = r.pipeline()
    pipe.hincrby(_k_cart(cid), sku, qtd)
    pipe.expire(_k_cart(cid), TTL_CARRINHO)
    pipe.execute()


def set_qtd(cid: str, sku: str, qtd: int) -> None:
    if qtd <= 0:
        r.hdel(_k_cart(cid), sku)
    else:
        r.hset(_k_cart(cid), sku, qtd)


def carrinho(cid: str) -> dict[str, int]:
    return {k: int(v) for k, v in r.hgetall(_k_cart(cid)).items()}


def limpar_carrinho(cid: str) -> None:
    r.delete(_k_cart(cid))


# ---------- Cache-aside ----------
def cache_get(chave: str):
    v = r.get(chave)
    return json.loads(v) if v else None


def cache_set(chave: str, valor, ttl: int = TTL_CACHE) -> None:
    r.setex(chave, ttl, json.dumps(valor, default=str))


def invalidar(chave: str) -> None:
    r.delete(chave)


# ---------- Ranking ----------
def registrar_view(sku: str) -> None:
    r.zincrby("ranking:mais_vistos", 1, sku)


def mais_vistos(n: int = 5) -> list[tuple[str, float]]:
    return r.zrevrange("ranking:mais_vistos", 0, n - 1, withscores=True)
