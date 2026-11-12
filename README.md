# Oracle graph-aware retrieval

A small notebook for a video demonstration: three memories about a meeting,
two typed links, and a controlled comparison of zero- versus two-hop retrieval.

## Run

Use Python 3.12. From this directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
```

Fill in `.env`, then launch:

```bash
python -m jupyterlab graph-aware-retrieval.ipynb
```

In VS Code, you can instead select `.venv/bin/python` as the notebook kernel.
Use **Run All** for each recording. No kernel restart is needed.

## What you need

- An Oracle AI Database supported by Oracle AI Agent Memory 26.8, with vector and
  SQL property graph support. The database user must be able to create the managed
  tables, indexes, and graph objects. See the
  [Oracle setup documentation](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/).

- Wallet authentication matches `oracle_image_similarity_openclip.ipynb`: set
  `ORACLE_USERNAME`, `ORACLE_PASSWORD`, and `DSN` (the wallet's TNS alias) in `.env`.
  Extract the wallet into `.wallet` in this project, or set `WALLET_DIRECTORY`.
  Both `config_dir` and `wallet_location` use that directory. The wallet password
  defaults to `ORACLE_PASSWORD`; set `WALLET_PASSWORD` if it differs. The memory
  SDK uses a connection pool with the same authentication arguments as the
  reference notebook's `oracledb.connect()`. `DB_DSN` remains a fallback for `DSN`.

- An embedding API key. The default embedding model is `text-embedding-3-small`
  with 1536 dimensions, matching Oracle's public example. Embedding calls can
  incur provider charges. Only synthetic meeting text and the query are embedded.
  No chat model is required.

The notebook uses the actual Oracle SDK and database; it has no offline simulation.
It stops with the names of missing settings if credentials are absent.

## References

- [Oracle release walkthrough](https://blogs.oracle.com/developers/whats-new-in-oracle-ai-agent-memory-graph-aware-retrieval-image-memory-and-enterprise-controls)
- [Linked-memory guide](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/int-graph-memory.html)
- [Search reference](https://docs.oracle.com/en/database/oracle/agent-memory/26.8/guide/api/search.html)
