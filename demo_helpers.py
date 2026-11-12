"""Connection setup and result presentation for the recording notebook."""

import os
from html import escape
from importlib.metadata import version
from pathlib import Path

import oracledb
import pandas as pd
from dotenv import load_dotenv
from IPython.display import HTML, display
from oracleagentmemory.core import (
    MemoryExtractionConfig,
    MemoryLinkExtractionMode,
    OracleAgentMemory,
    OracleDBMemoryStore,
    SchemaPolicy,
    SearchStrategy,
)
from oracleagentmemory.core.embedders import Embedder


# Reserved IDs belong only to this recording demo. Reset never scans other data.
RUN_ID = 'oracle-retrieval-meeting-v1'
USER_ID = f'meeting-demo-{RUN_ID}'
AGENT_ID = 'meeting-assistant'
DEMO_MEMORY_IDS = {label: f'{RUN_ID}-{label}' for label in ('A', 'B', 'C')}
DEMO_LINK_IDS = [f'{RUN_ID}-supersedes', f'{RUN_ID}-refines']


def pool_is_open(db_pool):
    if db_pool is None:
        return False
    try:
        db_pool.opened
    except oracledb.Error as exc:
        if exc.args and getattr(exc.args[0], 'full_code', None) == 'DPY-1002':
            return False
        raise
    return True


def close_pool(db_pool):
    if pool_is_open(db_pool):
        db_pool.close(force=True)


async def reset_links(memory):
    for relation_id in DEMO_LINK_IDS:
        await memory.delete_record_link_async(relation_id=relation_id)


async def reset_demo(memory):
    # Remove relationships before their endpoints; absent IDs are harmless.
    await reset_links(memory)
    for record_id in DEMO_MEMORY_IDS.values():
        await memory.delete_memory_async(record_id)


async def start_demo(previous_pool=None):
    close_pool(previous_pool)
    memory, db_pool = connect_memory()
    try:
        await reset_demo(memory)
    except Exception:
        close_pool(db_pool)
        raise
    return memory, db_pool


def connect_memory():
    load_dotenv('.env', override=True)
    pd.set_option('display.max_colwidth', None)
    pd.set_option('display.max_columns', None)
    oracledb.defaults.program = 'devrel-developerhub-graph-aware-retrieval-agent-memory'

    assert version('oracleagentmemory') == '26.8.0', 'Install requirements.txt, then restart the kernel.'

    # Match the wallet authentication used in the image-similarity notebook.
    # Legacy names remain supported for an existing .env.
    ORACLE_USERNAME = os.getenv('ORACLE_USERNAME') 
    ORACLE_PASSWORD = os.getenv('ORACLE_PASSWORD')
    DSN = os.getenv('DSN') or os.getenv('DB_DSN')
    WALLET_DIRECTORY = Path(os.getenv('WALLET_DIRECTORY') or '.wallet').expanduser().resolve()
    WALLET_PASSWORD = os.getenv('WALLET_PASSWORD') or ORACLE_PASSWORD

    required = {
        'ORACLE_USERNAME': ORACLE_USERNAME,
        'ORACLE_PASSWORD': ORACLE_PASSWORD,
        'DSN': DSN,
        'EMBEDDING_API_KEY': os.getenv('EMBEDDING_API_KEY'),
    }
    missing = [name for name, value in required.items() if not value or not value.strip()]
    if missing:
        raise RuntimeError('Fill these values in .env, then rerun: ' + ', '.join(missing))
    if not WALLET_DIRECTORY.is_dir():
        raise FileNotFoundError('Oracle Wallet directory not found. Set WALLET_DIRECTORY in .env.')

    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    EMBEDDING_DIMENSION = int(os.getenv('EMBEDDING_DIMENSION', '1536'))
    MEMORY_STORE_ID = os.getenv('MEMORY_STORE_ID', 'MEETINGDEMO')
    if not MEMORY_STORE_ID.isascii() or not MEMORY_STORE_ID.isalnum() or not MEMORY_STORE_ID[0].isalpha():
        raise ValueError('Use an ASCII letter followed by letters/digits for MEMORY_STORE_ID.')

    # A pool uses the same wallet authentication arguments as oracledb.connect().
    connection_options = dict(
        user=ORACLE_USERNAME,
        password=ORACLE_PASSWORD,
        dsn=DSN,
        config_dir=str(WALLET_DIRECTORY),
        wallet_location=str(WALLET_DIRECTORY),
        wallet_password=WALLET_PASSWORD,
        min=1,
        max=2,
        increment=1,
    )

    embedding_options = dict(
        model=EMBEDDING_MODEL,
        api_key=os.environ['EMBEDDING_API_KEY'],
        embedding_dimension=EMBEDDING_DIMENSION,
        max_input_tokens=512,
        normalize=True,
    )
    if os.getenv('EMBEDDING_API_BASE'):
        embedding_options['api_base'] = os.environ['EMBEDDING_API_BASE']

    db_pool = oracledb.create_pool(**connection_options)
    try:
        with db_pool.acquire() as connection:
            with connection.cursor() as cursor:
                assert cursor.execute('SELECT 1 FROM dual').fetchone()[0] == 1

        embedder = Embedder(**embedding_options)
        store = OracleDBMemoryStore(
            pool=db_pool,
            embedder=embedder,
            vector_dim=EMBEDDING_DIMENSION,
            memory_store_id=MEMORY_STORE_ID,
            schema_policy=SchemaPolicy.CREATE_IF_NECESSARY,
            search_strategy=SearchStrategy.VECTOR,
        )
        memory = OracleAgentMemory(
            store=store,
            memory_extraction_config=MemoryExtractionConfig(
                extract_memories=False,
                enable_context_summary=False,
                memory_link_extraction_mode=MemoryLinkExtractionMode.DISABLED,
            ),
        )
    except Exception:
        db_pool.close(force=True)
        raise

    return memory, db_pool


def direct_table(results, label_by_id):
    return pd.DataFrame([
        {
            'Rank': rank,
            'Record': label_by_id[result.id],
            'Vector distance (lower is closer)': round(result.distance, 4),
            'Status': result.status.value,
            'Memory': result.content,
        }
        for rank, result in enumerate(results, 1)
    ])


def tree_rows(results, label_by_id):
    """Read the SDK's recursive (RecordRelation, SearchResult) pairs."""
    rows = []
    def walk(result, depth=0, parent=None, relation=None):
        label = label_by_id[result.id]
        edge_label = 'direct match'
        if relation is not None:
            # The stored direction may differ from the direction of traversal.
            edge_label = (
                relation.relation_type
                if relation.source_record_id == parent.id
                else relation.opposite_relation_type
            )
        rows.append({
            'Depth': depth,
            'Record': label,
            'From': label_by_id[parent.id] if parent else '-',
            'Relationship': edge_label,
            'Status': result.status.value,
            'Memory': result.content,
        })
        for child_relation, child in result.linked_results or []:
            walk(child, depth + 1, result, child_relation)
    for root in results:
        walk(root)
    return rows

def result_cards(title, results, label_by_id):
    cards = []
    for row in tree_rows(results, label_by_id):
        historical = row['Status'] == 'invalid'
        color = '#9a6700' if historical else '#137754'
        relation = 'Direct match' if row['Depth'] == 0 else (
            f"{row['From']} → {row['Relationship']} → {row['Record']}"
        )
        cards.append(
            f'<div style="margin:12px 0 12px {row["Depth"] * 18}px;'
            f'padding:15px;background:#f8fafc;border-left:4px solid {color};border-radius:6px">'
            f'<div style="font-size:13px;color:#475569">{escape(relation)}</div>'
            f'<div style="font-size:19px;margin:8px 0">{escape(row["Memory"])}</div>'
            f'<div style="font-size:12px;color:{color}">{escape(row["Record"])} · '
            f'{"HISTORICAL" if historical else "CURRENT"}</div></div>'
        )
    return f'<section style="flex:1;min-width:280px"><h3>{escape(title)}</h3>{"".join(cards)}</section>'



def show_comparison(flat_results, graph_results, label_by_id):
    display(HTML(
        '<div style="display:flex;gap:28px;flex-wrap:wrap;color:#0f172a;'
        'background:white;padding:24px;border-radius:12px;font-family:system-ui">'
        + result_cards('Direct retrieval · 0 hops', flat_results, label_by_id)
        + result_cards('Graph-aware retrieval · 2 hops', graph_results, label_by_id)
        + '</div>'
    ))


async def cleanup(memory, db_pool, delete=True):
    """Delete this run's data and close the pool; calling again is harmless."""
    if not pool_is_open(db_pool):
        return
    try:
        if delete:
            await reset_demo(memory)
    finally:
        close_pool(db_pool)
