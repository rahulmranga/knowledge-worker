# Competitive Analysis

Last verified: 2026-05-21.

This document positions `knowledge-worker` against adjacent tools without using
private graph data. It is scoped to public-demo-safe claims and should be
rechecked before major release announcements.

## Positioning

`knowledge-worker` is personal AI memory with source-backed claims. It is built
for the individual practitioner who wants durable context across AI sessions,
but still wants every durable claim to point back to a source excerpt and pass a
human review step before merge.

That puts it on a different diagonal from team chat-to-wiki systems, linked-note
PKM tools, generic vector memory, and graph database demos. The overlap is real:
all of these systems preserve or retrieve knowledge. The difference is the
promotion model: in `knowledge-worker`, the LLM proposes, provenance and review
decide.

## Comparison Matrix

| Dimension | `knowledge-worker` | Beever Atlas | Linked-note PKM tools | Generic RAG/vector memory | Graph DB demo |
|---|---|---|---|---|---|
| Primary user | Solo AI practitioner | Team/workspace-first, with an open source edition also described for individuals | Note-taker or researcher | App developer adding memory/retrieval | Developer learning graph storage |
| Input source | Markdown notes, including notes converted from JSON, JSONL, or chat exports, and reviewed candidate files | Team and personal chat streams; docs describe Slack, Discord, Teams, Telegram, and related connectors | Markdown notes, blocks, pages, backlinks | Text chunks from app data, docs, chats, or transcripts | Structured sample data |
| Durable memory unit | Typed node plus typed edge, both tied to provenance | Extracted facts, entities, relationships, generated wiki pages, vector/graph memory | Linked note, page, or block | Vector chunk, embedding, metadata record | Entity node and relationship |
| Claim promotion model | LLM proposals must pass deterministic validation and human review before merge | Automatic extraction pipeline with quality gates and generated wiki output | User-authored notes and links | Usually automatic indexing plus retrieval-time ranking | Manual loading or scripted fixtures |
| Provenance model | Required `MENTIONED_IN` edge with source id and literal excerpt for durable claims | Citation-bearing answers and wiki content from source conversations | Human-authored citation habits, not generally enforced by the tool | Provider- or app-specific; often not a hard invariant | Depends on demo schema |
| Curation model | Manual review with optional confidence-based auto-accept before graph merge | Automated extraction, clustering, and wiki generation | Manual writing and linking | Automatic ingestion and retrieval | Manual schema design |
| Path/query support | CLI `query`, `path`, `audit`, and compact `context` export | Natural-language Q&A, semantic memory, graph memory, and MCP/API surface | Backlinks and visual graph views | Semantic similarity search | Cypher, AQL, Gremlin, or demo-specific queries |
| Local/private shape | Single local JSON graph by default; private graphs loaded by path/env | Self-hosted Docker stack; public docs describe Weaviate and Neo4j as core memory systems | Local vaults are common, sync varies | Varies by provider and app | Local or hosted graph database |
| MCP/agent integration | Experimental local MCP wrapper in `ollama_proxy/server.py` | Public docs describe first-class MCP support | Usually third-party plugins | Provider-dependent | Manual integration |
| Benchmarkability | Offline demo graph benchmarks with no API key | Public docs and repos are inspectable, but no shared benchmark fixture is assumed here | Hard to compare across vaults | Varies by implementation | Demo-specific |
| Best use case | Preserving the thread of your own reasoning across AI sessions | Recovering and querying conversational knowledge from teams/workspaces | Long-form human-authored knowledge management | Adding semantic recall to an app | Teaching graph concepts |
| Not designed for | Multi-user team chat ingestion, cloud sync, enterprise permissions | Provenance-first personal review-before-merge workflows | Enforced LLM claim provenance | Human review and proof guarantees by default | Production personal memory workflow |

## Beever Atlas Notes

Beever Atlas is the closest named comparison because it combines chat ingestion,
knowledge graph storage, wiki generation, and MCP support. The public docs frame
it as a way to capture knowledge from team conversations, automatically extract
and structure that knowledge, and retrieve sourced answers. The same public
materials also describe an open source edition for individuals, so this document
uses "team/workspace-first" instead of saying it is not usable personally.

The product stack and workflow are intentionally larger than
`knowledge-worker`: Beever Atlas public docs describe a dual-memory architecture
using Weaviate for semantic memory and Neo4j for graph memory, a six-stage
pipeline from sync through wiki generation, Docker deployment, and first-class
MCP support. `knowledge-worker` deliberately starts smaller: one local graph
file, explicit provenance invariants, and review before merge.

## Source Notes

- Beever Atlas public docs: https://docs.beever.ai/atlas
- Beever Atlas GitHub repository: https://github.com/Beever-AI/beever-atlas
- PR Newswire announcement, 2026-05-08: https://www.prnewswire.com/news-releases/hong-kongs-votee-ai-and-torontos-beever-ai-open-source-beever-atlas--turns-your-telegram-discord-mattermost-microsoft-teams-and-slack-chats-into-a-living-wiki-302766908.html

## Maintenance Notes

- Re-verify competitor claims before changing this document.
- Add named rows for specific RAG/vector memory or PKM tools only after a
  source pass for each named tool.
- Keep this page factual. The differentiator should be obvious from the matrix:
  local personal memory, required provenance, and human review before merge.
