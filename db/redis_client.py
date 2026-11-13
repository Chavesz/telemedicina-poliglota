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
from db.oplog import registrar

try:
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=3, socket_connect_timeout=3)
except ValueError:  # URL mal preenchida: o app abre e mostra o Redis em vermelho em vez de quebrar
    r = redis.Redis(host="redis-url-invalida", socket_timeout=1, socket_connect_timeout=1)

TTL_SESSAO = 30 * 60
TTL_ATENDIMENTO = 60 * 60
TTL_AGENDA = 5 * 60
FILA = "fila:espera"
CHAVE_AGENDA = "cache:agenda:hoje"
# Menor score = atendido antes. A prioridade "pesa" mais que a hora de chegada.
PESO = {"Emergência": 0, "Urgente": 1, "Normal": 2}


def ping() -> bool:
    return r.ping()


def ttl(chave: str) -> int:
    return r.ttl(chave)


def info() -> dict:
    try:  # alguns Redis gerenciados (ex.: Upstash) bloqueiam o comando INFO
        memoria = r.info("memory").get("used_memory_human", "?")
    except redis.RedisError:
        memoria = "n/d"
    return {"chaves": r.dbsize(), "memoria": memoria}


def simular_queda(manter_token: str) -> int:
    """Para a demo: apaga todo o estado temporário (como se o Redis reiniciasse),
    menos a sessão de quem está apresentando. Retorna quantas chaves sumiram."""
    apagadas = 0
    for k in list(r.scan_iter("*")):
        if k != f"sessao:{manter_token}":
            r.delete(k)
            apagadas += 1
    registrar("Redis", f"DEL * (simulação de reinício: {apagadas} chaves apagadas, sessão mantida)")
    return apagadas


def chaves_com_ttl(padrao: str = "*", limite: int = 200) -> list[dict]:
    """Chaves, tipo e TTL — para mostrar no Painel dos Bancos."""
    saida = []
    for k in r.scan_iter(match=padrao, count=100):
        saida.append({"chave": k, "tipo": r.type(k), "ttl (s)": r.ttl(k)})
        if len(saida) >= limite:
            break
    return sorted(saida, key=lambda x: x["chave"])


# ---------- Sessão / token de login ----------
def criar_sessao(medico: dict) -> str:
    token = uuid.uuid4().hex
    r.setex(f"sessao:{token}", TTL_SESSAO, json.dumps(medico))
    registrar("Redis", f"SETEX sessao:{token[:8]}… {TTL_SESSAO} '{{crm: {medico['crm']}, ...}}'")
    return token


def obter_sessao(token: str) -> dict | None:
    dado = r.get(f"sessao:{token}")
    if dado:
        r.expire(f"sessao:{token}", TTL_SESSAO)   # sliding expiration: renova a cada uso
        registrar("Redis", f"GET sessao:{token[:8]}… ; EXPIRE {TTL_SESSAO}")
        return json.loads(dado)
    return None


def encerrar_sessao(token: str) -> None:
    r.delete(f"sessao:{token}")
    registrar("Redis", f"DEL sessao:{token[:8]}…")


def simular_expiracao_sessao(token: str, segundos: int = 5) -> None:
    """Para a demo: encurta o TTL e mostra o login expirando sozinho."""
    r.expire(f"sessao:{token}", segundos)
    registrar("Redis", f"EXPIRE sessao:{token[:8]}… {segundos}  (simulação)")


# ---------- Fila de espera (Sorted Set) ----------
def entrar_na_fila(cpf: str, nome: str, prioridade: str) -> None:
    score = PESO[prioridade] * 1e10 + time.time()
    pipe = r.pipeline()
    pipe.zadd(FILA, {cpf: score})
    pipe.hset(f"fila:info:{cpf}", mapping={"nome": nome, "prioridade": prioridade,
                                           "chegada": time.strftime("%H:%M:%S")})
    pipe.execute()
    registrar("Redis", f"ZADD {FILA} {score:.0f} {cpf} ; HSET fila:info:{cpf} nome '{nome}' prioridade {prioridade}")


def fila() -> list[dict]:
    registrar("Redis", f"ZRANGE {FILA} 0 -1 ; HGETALL fila:info:{{cpf}}")
    out = []
    for pos, cpf in enumerate(r.zrange(FILA, 0, -1), 1):
        out.append({"posição": pos, "cpf": cpf, **r.hgetall(f"fila:info:{cpf}")})
    return out


def chamar_proximo(crm: str) -> str | None:
    """ZPOPMIN é atômico: dois médicos nunca chamam o mesmo paciente."""
    res = r.zpopmin(FILA)
    registrar("Redis", f"ZPOPMIN {FILA}")
    if not res:
        return None
    cpf = res[0][0]
    r.setex(f"atendimento:{cpf}", TTL_ATENDIMENTO, crm)
    registrar("Redis", f"SETEX atendimento:{cpf} {TTL_ATENDIMENTO} {crm}")
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
    registrar("Redis", f"DEL atendimento:{cpf} fila:info:{cpf} ; ZREM {FILA} {cpf} ; INCR contador:atendidos_hoje")


def atendidos_hoje() -> int:
    return int(r.get("contador:atendidos_hoje") or 0)


# ---------- Cache-aside ----------
def cache_get(chave: str):
    v = r.get(chave)
    registrar("Redis", f"GET {chave} -> {'HIT' if v else 'MISS'}")
    return json.loads(v) if v else None


def cache_set(chave: str, valor, ttl_s: int) -> None:
    r.setex(chave, ttl_s, json.dumps(valor, default=str))
    registrar("Redis", f"SETEX {chave} {ttl_s} <json>")


def invalidar(chave: str) -> None:
    """Cache invalidation: o dado mudou no Mongo, então a cópia no Redis é apagada."""
    r.delete(chave)
    registrar("Redis", f"DEL {chave}  (invalidação de cache)")
