# Features Implemented — MotherSource AI Backend

This document outlines the core capabilities and features implemented in the current codebase.

## 1. Mother Onboarding Finder (Core Service)
A specialized search engine designed to identify the most effective healthcare channels for maternal health outreach in specific Indian districts.

## 2. Hybrid RAG (Retrieval-Augmented Generation)
- **Vector Search**: Uses `pgvector` in Supabase to perform semantic similarity searches based on outreach needs.
- **Contextual Filtering**: Filters results by `district` and `demographic` (Urban/Rural/General).
- **LLM Ranking**: Integrates with GPT-4o to analyze candidate entities and rank them by relevance.
- **Reasoning Generation**: Provides comparative logic explaining why each entity was selected and ranked at its specific position.

## 3. Data Ingestion Pipeline
- **JSON Processing**: A robust script (`ingest_hrag.py`) to flatten complex, nested healthcare document structures.
- **Automated Embedding**: Generates high-dimensional embeddings for text chunks using OpenAI's embedding models.
- **Supabase Integration**: Direct ingestion of processed chunks into the `entities` table with vector support.

## 4. Scalable API Layer
- **FastAPI Framework**: High-performance asynchronous API endpoints.
- **Pydantic Validation**: Strict schema enforcement for all incoming requests and outgoing responses.
- **CORS Support**: Configured for cross-origin requests, enabling frontend integration.

## 5. Technical Infrastructure
- **Dependency Injection**: Clean separation of configurations (Supabase, OpenAI) using FastAPI dependencies.
- **Environment Management**: Configuration-driven approach via `.env` files.
- **Logging**: Detailed logging for debugging and monitoring service performance.
