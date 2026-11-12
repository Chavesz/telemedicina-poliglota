# Colocar o projeto online (grátis)

O app roda no **Streamlit Community Cloud** e conversa com os 3 bancos na nuvem, todos no plano gratuito.
Cada conta precisa ser criada por alguém do grupo (leva uns 20 minutos no total).

| Peça | Serviço gratuito | O que copiar |
|---|---|---|
| MongoDB | **MongoDB Atlas** (cluster M0) — cloud.mongodb.com | a *connection string* `mongodb+srv://usuario:senha@cluster.../` |
| Redis | **Redis Cloud** (30 MB) — redis.io/try-free, ou **Upstash** | a URL `redis://default:senha@host:porta` (Upstash: `rediss://...`) |
| Neo4j | **Neo4j AuraDB Free** — console.neo4j.io | `NEO4J_URI` (`neo4j+s://xxxx.databases.neo4j.io`), usuário e senha (a senha aparece **uma vez** na criação) |
| App | **Streamlit Community Cloud** — share.streamlit.io (login com o GitHub) | — |

## Passo a passo
1. **Atlas:** crie o cluster M0 → *Database Access* (crie usuário/senha) → *Network Access* → *Allow access from anywhere* (`0.0.0.0/0`, necessário porque o Streamlit Cloud não tem IP fixo) → *Connect* → *Drivers* → copie a string.
2. **Redis Cloud:** crie o banco free → copie *Public endpoint* e a senha do usuário `default` → monte `redis://default:SENHA@ENDPOINT`.
3. **AuraDB Free:** *New instance* → baixe/copie as credenciais na hora.
4. **Popular os bancos (uma vez, do seu PC):** crie um `.env` com os valores acima (modelo em `.env.example`) e rode:
   ```bash
   python -m scripts.seed
   ```
5. **Streamlit Cloud:** *Create app* → repositório `Chavesz/telemedicina-poliglota`, branch `main`, arquivo `app.py` → *Advanced settings* → Python 3.12 → em **Secrets** cole:
   ```toml
   MONGO_URI = "mongodb+srv://..."
   MONGO_DB = "telemedicina"
   REDIS_URL = "redis://default:...@...:porta"
   NEO4J_URI = "neo4j+s://xxxx.databases.neo4j.io"
   NEO4J_USERNAME = "neo4j"
   NEO4J_PASSWORD = "..."
   NEO4J_DATABASE = "neo4j"
   ```
6. *Deploy*. O endereço fica algo como `telemedicina-poliglota.streamlit.app`.

## Cuidados
- **Senhas só nos Secrets/.env**, nunca no código (o repositório é público).
- O AuraDB Free **pausa depois de 3 dias sem uso**, e o app do Streamlit Cloud "dorme" depois de um tempo parado. **Abra o app e o console do Aura uns 10 minutos antes de apresentar.**
- Para recomeçar a demo do zero, rode `python -m scripts.seed` de novo.
- O enunciado traz credenciais de um AuraDB do professor. **Não usem para o seed**: ele apaga todo o grafo (`MATCH (n) DETACH DELETE n`). Criem um Aura próprio.
- Plano B se a internet falhar: `docker compose up -d` + `python -m scripts.seed` + `streamlit run app.py` no notebook.
