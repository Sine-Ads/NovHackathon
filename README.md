Haemophilia Intelligence Radar

    AI-powered intelligence radar for haemophilia — detecting what changed, why it matters, who should act, and what to do next.

Overview

The Haemophilia Intelligence Radar converts scattered public information into structured, prioritized, and actionable intelligence.

Instead of simply summarizing articles, the system maintains a structured view of the haemophilia landscape, detects changes against previously known information, assesses their potential impact, and routes relevant signals to the appropriate business functions.

For every significant signal, the radar answers:

    What changed?
    Why does it matter?
    Who should review it?
    What action is required?

Core Features
Intelligence Monitoring

Collects information from curated public sources including clinical trial registries, scientific publications, regulatory agencies, HTA bodies, congresses, and selected company sources.
Change Detection

Maintains historical entity state and identifies meaningful changes across clinical, regulatory, competitive, and scientific developments.
Event Deduplication

Identifies multiple sources covering the same underlying development and consolidates them into a single canonical event.
Impact and Routing

Assesses signals against the haemophilia landscape and routes relevant intelligence to appropriate business functions including:

    Medical Affairs
    Regulatory
    Market Access / HEOR
    Clinical Development
    Commercial / Brand

Stakeholder Calibration

Captures stakeholder feedback on relevance, urgency, and routing and uses this feedback to improve future signal scoring and prioritization.
Actionable Intelligence

Converts intelligence signals into structured action artifacts containing ownership, urgency, recommended action, SLA, and lifecycle status.
Evidence and Provenance

Maintains source-level provenance for extracted claims and provides supporting evidence for generated intelligence. The system can abstain when available evidence is insufficient.
Silence Detection

Identifies expected developments that have not occurred, enabling the system to surface potentially important non-events.
Architecture

Public Sources
      |
      v
Ingestion
      |
      v
Deduplication and Event Clustering
      |
      v
Structured Extraction
      |
      v
Entity Resolution
      |
      v
Entity State Store
      |
      v
Change Detection
      |
      v
Impact Assessment
      |
      v
Routing and Urgency
      |
      v
Stakeholder Calibration
      |
      v
Signal Generation
      |
      v
Dashboard and Intelligence Assistant

The system uses structured storage for entity state, decisions, ownership, and stakeholder preferences, while retrieval is used for the underlying knowledge corpus.
Repository Structure

haemophilia-intelligence-radar/
|
├── backend/
│   ├── ingestion/
│   ├── intelligence/
│   ├── reasoning/
│   └── api/
|
├── frontend/
├── data/
│   ├── seed/
│   ├── fixtures/
│   └── gold_set/
|
├── contracts/
├── evaluation/
├── tests/
├── scripts/
├── docs/
|
├── docker-compose.yml
├── .env.example
└── README.md

Shared contracts define interfaces such as signal_card, action_artifact, extracted_event, and feedback, allowing different components to be developed and tested independently.
Technology Stack

    Backend: Python
    Database: PostgreSQL + pgvector
    AI: LLMs with structured outputs and retrieval
    Frontend: Next.js
    Data Sources: ClinicalTrials.gov, PubMed, FDA, EMA, HTA bodies, congress sources, and selected public company sources
    Scheduling: Cron / GitHub Actions

Evaluation

The system is evaluated across:

    Extraction accuracy
    Event deduplication
    Change detection
    Signal relevance
    Function routing
    Calibration improvement
    Source provenance

A labelled evaluation set is used to measure system performance and determine whether stakeholder calibration improves signal prioritization.
Project Status

Prototype / Hackathon Project

The project focuses on transforming external haemophilia intelligence into evidence-backed, prioritized, and actionable decisions.
