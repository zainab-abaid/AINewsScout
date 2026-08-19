# Genie Research Context for Probe Scouting

## Purpose

Use this file only as background when screening AI newsletter emails for possible Genie probes.

It tells you:

- what Genie has already investigated;
- what kinds of technical developments tend to catch our attention; and
- which areas are currently higher priority.

The priority areas are **not a whitelist**. A strong, hands-on GenAI engineering topic outside them may still be selected.

---

# Previous Genie probes and hands-on investigations

## 1. Custom RAG versus managed RAG

We compared a custom RAG pipeline with managed RAG approaches for question answering over technical PDFs. The main idea was to test whether control over parsing, chunking, retrieval and reranking could outperform convenient off-the-shelf configurations.

## 2. Reinforcement fine-tuning with limited data

We tested Amazon Bedrock Reinforcement Fine-Tuning to understand whether reinforcement-based model improvement could work with less data and when it may be worth using. This was model-improvement research, but future training topics are mainly relevant when they connect clearly to agent or GenAI application engineering.

## 3. Vector RAG versus agentic search versus long-context prompting

We compared three ways of answering questions over source-code repositories: vector RAG, an agent that searched the filesystem, and putting a large codebase directly into a long context window. We examined accuracy, latency, scaling behaviour and what happened as the search space grew.

## 4. Where to optimise a RAG pipeline

We ran controlled comparisons of RAG components, especially chunking and reranking strategies, over a technical-document Q&A workload. A key interest was whether preserving document structure and hierarchy improved retrieval and answer quality.

## 5. Prompt compression in enterprise document Q&A

We tested LLMLingua-2 on long RAG prompts to see whether reducing tokens improved cost and latency without damaging accuracy. Compression reduced token volume but removed useful structure, lowered accuracy and introduced extra processing cost and latency.

## 6. PDF-to-Markdown parser benchmark

We benchmarked multiple PDF parsing approaches across different document types and structural quality dimensions. The focus was not merely text extraction, but preservation of hierarchy, reading order, tables, figures and code needed by downstream RAG and agentic-search systems.

## 7. GenieParse

We built an open-source PDF-to-Markdown accelerator combining OCR with targeted post-processing for headings, tables, figures, code and cleanup. The idea was that document parsing should be treated as a first-class engineering layer rather than a generic preprocessing step.

## 8. Recursive Language Models versus RAG

We compared DSPy-style Recursive Language Models with a basic vector RAG pipeline for code and technical-document Q&A. RLM produced higher accuracy on complex or sparse questions, but at substantially greater cost and latency, highlighting the importance of context assembly and workload fit.

## 9. Hallucination-detection tooling

We compared tools and methods for detecting hallucinations in generated answers, including UpTrain, using an evaluation set with known outcomes. The broader interest was practical, measurable evaluation tooling rather than general commentary about hallucinations.

## 10. Multi-document RAG strategies

We investigated approaches for answering questions that require evidence across multiple documents rather than retrieving one isolated chunk. The focus was on retrieval and synthesis strategies that can be implemented and compared experimentally.

## 11. Agentic search and DCI-Agent-style retrieval

We explored agent-driven search methods that iteratively inspect and navigate information instead of relying only on one vector-retrieval step. We were interested in whether active search improved answer accuracy, and what latency and cost trade-offs it introduced.

## 12. RAG architecture comparisons

We compared alternative RAG system designs and the practical trade-offs between them. The recurring question was which architecture is most appropriate for a particular corpus, query type, accuracy requirement and production constraint.

## 13. Supervised fine-tuning and reinforcement learning for tool use

We experimented with SFT/RL workflows on open models such as Qwen or Mistral and evaluated whether tool-calling behaviour improved. This is relevant as precedent for hands-on agent learning and evaluation, not as an instruction to prioritise generic foundation-model tuning.

## 14. Quantity take-off from construction documents

We investigated using GenAI and document-processing methods to extract construction quantities from complex documents. This represented interest in measurable, document-heavy applied AI workflows with difficult tables, layouts and domain-specific outputs.

## 15. LLM routing for coding harnesses

We built a proof of concept over the Pi.dev open harness that classifies coding tasks and routes them into model capability tiers. The work examined deterministic routing rules, task complexity, cost, latency and how a router could sit behind a company-controlled gateway.

---

# Related Genie artifacts the scout should know about

These were not necessarily published as numbered probes, but they represent existing Genie work and may affect novelty or suggest extensions.

## GenAI Evaluation Guide

A repeatable evaluation framework covering application and model quality, retrieval, tool calls, memory, agent steps, safety, performance, cost and capability fit. New evaluation tools, benchmarks and trace-analysis techniques are especially relevant when they can strengthen this framework.

## Agentic RAG reference architecture

A reusable architecture for agents that search and reason across multiple information sources. Candidate tools or methods that improve orchestration, retrieval, verification, memory or evaluation may extend this work.

## Enterprise harness and control-plane direction

Current R&D is shaping an enterprise layer around coding agents and open harnesses. It includes shared skills and workflows, policies, hooks, verification, monitoring, auditability, routing, budgets, escalation, credentials, dashboards and trace-driven improvement.

---

# Current higher-priority research areas

A candidate that clearly belongs to one of these areas should be tagged **High Priority Research Area** when it also has a plausible hands-on investigation path.

## Harness engineering and AI development agents

Coding-agent harnesses, open harnesses, plugins, skills, subagents, hooks, MCP integrations, reusable workflows, context files, policy files, verification steps and methods for making AI-assisted development more reliable.

## Enterprise control over AI development workflows

Control planes, governance, policy enforcement, audit trails, shared resources, approved workflows, credential centralisation, access control, developer budgets, escalation, dashboards and organisation-wide measurement of AI-assisted engineering.

## LLM gateways and model routing

Model routers, capability classification, cheapest-capable-model routing, fallback, escalation, privacy and eligibility rules, context-window constraints, budget enforcement, caching-aware routing and evaluation of routing decisions on end-to-end task outcomes.

## Inference engineering

Speculative decoding, serving systems, batching, caching, quantisation, inference optimisation, local or private model serving, latency/cost engineering and tools that improve practical model execution. A speculative-decoding experiment is already planned.

## Comparing LLM routers

Frameworks, algorithms and benchmarks for routing requests among multiple models are an explicit planned probe area. We are interested in router quality, calibration, task-success impact, full-session cost, latency, model onboarding and deterministic enterprise constraints.

## GenAI application and agent evaluation

Evaluation libraries, test-generation methods, LLM judges, deterministic evaluators, benchmarks, observability systems, trace analysis, trajectory evaluation, tool-call evaluation, memory evaluation, retrieval evaluation, regression testing, failure taxonomies and production feedback loops.

## Trace-driven improvement over time

Methods that turn agent traces and failures into reusable rules, skills, policies, automated checks, deterministic guardrails, regression tests or training data. Especially relevant are approaches that progressively replace expensive LLM checks with cheaper deterministic checks.

## RAG, retrieval and agentic search

New retrieval libraries, rerankers, indexes, hybrid search, structured retrieval, graph retrieval, multi-document reasoning, code search, active/agentic search, recursive context exploration and practical comparisons among retrieval architectures.

## PDF parsing and intelligent document processing

PDF-to-Markdown systems, OCR, layout analysis, table extraction, figure handling, reading order, structure preservation, document benchmarks and downstream effects on RAG or agents.

## Agent memory and context management

Short- and long-term agent memory, episodic or semantic memory, memory stores, retrieval policies, context compression, context selection, durable state, cross-session consistency and evaluation of memory usefulness.

## Context engineering

Prompt and context construction, long-context methods, recursive language models, context compression, dynamic context loading, repository navigation and techniques for selecting or organising information before an LLM call.

## Guardrails, verification and AI system reliability

Policy engines, structured checks, runtime constraints, output verification, secure tool use, permissions, sandboxing, deterministic validation and methods that make agents or GenAI applications safer and more predictable.

## Shared enterprise AI resources

Repositories and distribution systems for prompts, skills, plugins, MCP configurations, workflows, evaluation suites and reusable engineering practices that teams can push to and pull from their development harnesses.

## GenAI observability and LLMOps

Tracing, dashboards, production monitoring, cost and latency analysis, quality drift, experiment tracking, prompt/version management and operational tooling for LLM applications and agents.

## Synthetic data and evaluation-data creation

Tools and methods for creating representative test sets, adversarial cases, agent tasks, ground truth and regression suites, especially where quality can be measured.

## Practical reinforcement learning for agents

RL libraries, reward design, trace-based learning, tool-use training and agent improvement are relevant when they enable an accessible hands-on experiment. Generic pretraining or fine-tuning news without an application-engineering connection remains low priority.

## Multimodal and document-centric AI systems

Tools and methods for combining text, images, tables, diagrams, audio or video when they support a concrete application or measurable experiment rather than a general product announcement.

---

# What is generally not useful

Do not select material merely because it concerns:

- funding, valuation, acquisition or market dynamics;
- executive or company news;
- broad AI predictions or opinion;
- generic model launches and leaderboard claims;
- product marketing without enough technical access or detail;
- regulation or policy without a concrete technical experimentation angle; or
- model tuning that has no clear connection to agents, GenAI applications, tooling or evaluation.

A newsletter item can still contain a relevant technical candidate inside an otherwise irrelevant business-news section. Extract the technical item and ignore the rest.
