"""Redis — banco CHAVE-VALOR em memória.

Por que aqui? Tudo que é temporário e muda o tempo todo:
  - sessao:{token}        STRING (JSON do médico), TTL 30 min -> login expira sozinho
  - fila:espera           SORTED SET  cpf -> score (prioridade + hora de chegada)
  - fila:info:{cpf}       HASH  nome, prioridade, chegada
  - atendimento:{cpf}     STRING  crm do médico que está atendendo (TTL 1 h)
  - cache:agenda:hoje     STRING (JSON), TTL 5 min -> cache da agenda do Mongo
  - contador:atendidos_hoje  INCR
Se o Redis reiniciar perde a fila do dia — aceitável; o prontuário (Mongo) não.
"""
import json
import time
import uuid
import redis
from db.config import REDIS_URL

r = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3)

TTL_SESSAO = 30 * 60
TTL_ATENDIMENTO = 60 * 60
TTL_AGENDA = 5 * 60
FILA = "fila:espera"
# Menor score = atendido antes. A prioridade "pesa" mais que a hora de chegada.
PESO = {"Emergência": 0, "Urgente": 1, "Normal": 2}


def ping() -> bool:
    return r.ping()


def ttl(chave: str) -> int:
    return r.ttl(chave)


# ---------- Sessão / token de login ----------
def criar_sessao(medico: dict) -> str:
    token = uuid.uuid4().hex
    r.setex(f"sessao:{token}", TTL_SESSAO, json.dumps(medico))
    return token


def obter_sessao(token: str) -> dict | None:
    dado = r.get(f"sessao:{token}")
    if dado:
        r.expire(f"sessao:{token}", TTL_SESSAO)   # sliding expiration: renova a cada uso
        return json.loads(dado)
    return None


def encerrar_sessao(token: str) -> None:
    r.delete(f"sessao:{token}")


# ---------- Fila de espera (Sorted Set) ----------
def entrar_na_fila(cpf: str, nome: str, prioridade: str) -> None:
    score = PESO[prioridade] * 1e10 + time.time()
    pipe = r.pipeline()
    pipe.zadd(FILA, {cpf: score})
    pipe.hset(f"fila:info:{cpf}", mapping={"nome": nome, "prioridade": prioridade,
                                           "chegada": time.strftime("%H:%M:%S")})
    pipe.execute()


def fila() -> list[dict]:
    out = []
    for pos, cpf in enumerate(r.zrange(FILA, 0, -1), 1):
        out.append({"posição": pos, "cpf": cpf, **r.hgetall(f"fila:info:{cpf}")})
    return out


def chamar_proximo(crm: str) -> str | None:
    """ZPOPMIN é atômico: dois médicos nunca chamam o mesmo paciente."""
    res = r.zpopmin(FILA)
    if not res:
        return None
    cpf = res[0][0]
    r.setex(f"atendimento:{cpf}", TTL_ATENDIMENTO, crm)
    return cpf


def em_atendimento() -> list[dict]:
    out = []
    for k in r.scan_iter("atendimento:*"):
        cpf = k.split(":", 1)[1]
        out.append({"cpf": cpf, "nome": r.hget(f"fila:info:{cpf}", "nome"), "crm": r.get(k)})
    return out


def finalizar_atendimento(cpf: str) -> None:
    r.delete(f"atendimento:{cpf}", f"fila:info:{cpf}")
    r.zrem(FILA, cpf)
    r.incr("contador:atendidos_hoje")


def atendidos_hoje() -> int:
    return int(r.get("contador:atendidos_hoje") or 0)


# ---------- Cache-aside ----------
def cache_get(chave: str):
    v = r.get(chave)
    return json.loads(v) if v else None


def cache_set(chave: str, valor, ttl_s: int) -> None:
    r.setex(chave, ttl_s, json.dumps(valor, default=str))
