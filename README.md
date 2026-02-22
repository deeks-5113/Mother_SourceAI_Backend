# MotherSource AI – Project Documentation

## Project Overview
MotherSource AI is a production-grade backend ecosystem and specialized, state-driven search and recommendation platform.

---

## Problem Statement
There is a gap between maternal health initiatives and rural field outreach, and traditional keyword search fails on complex maternal health queries.

---

## Solution Approach
The platform leverages a **Hierarchical Retrieval-Augmented Generation (HRAG)** engine to transform unstructured project goals and complex clinical match-making data into precise matches, actionable outreach strategies, and reasoned intelligence.

---

## Target Users
The application serves as a mission-critical tool for connecting expectant mothers across Andhra Pradesh and Telangana with:

- Mothers
- Clinical healthcare channels  
- High-aligned NGOs  
- Primary Health Centres (PHCs)  
- Mission-aligned implementation and funding partners  

---

# System Architecture Overview

The system utilizes a **3-tier architecture**.

## 1️⃣ Client Tier
An interaction layer sending JSON-based requests via REST API.

## 2️⃣ API Gateway & Service Layer
Built on **FastAPI**, this layer:
- Handles asynchronous operations  
- Follows modular architecture  
- Implements strict service separation  
- Uses dependency injection  

## 3️⃣ Data Layer
Powered by the **Supabase Stack**, utilizing:
- PostgreSQL for relational metadata  
- pgvector for native vector storage and similarity search  

---

## Data Flow Pipeline

1. Client request enters FastAPI endpoint  
2. Query embeddings generated using `text-embedding-3-small`  
3. Candidate retrieval via Supabase pgvector using HNSW indexing  
4. Candidates passed to GPT-4o reasoning layer  
5. JSON API response returned to client  

---

# Tech Stack

## Frontend
- React 19 (Vite)
- Tailwind CSS 4
- Framer Motion

## Backend
- FastAPI
- OpenAI (text-embedding-3-small and GPT-4o)

## Database
- Supabase PostgreSQL
- pgvector (HNSW Indexing)

---

# Features

## Core Features

### Onboarding Search
Identifies hospitals and health centres equipped to handle specific outreach needs.

### Partner Scouting
Matches project goals with high-capacity NGOs and Global Funders.

### Smart Outreach
Generates persona-driven, multi-channel communication to convert matches into active partnerships.

---

## Advanced Features

### Intelligence Pipeline (HRAG)
Three-stage process:
1. Metadata filtering for pruning  
2. Dense vector search using cosine similarity  
3. LLM reasoning via GPT-4o for re-ranking and inference  

### Reasoning Protocol
UI exposes AI reasoning via an interactive **"Analyze Protocol"** trigger explaining comparative alignment.

### Progressive Loading Design
Global interceptor overlays high-fidelity animations during HRAG/LLM execution to maintain engagement.

---

# Folder Structure

## Frontend Structure
- Centralized Engine Provider (`useEngine.tsx`) for global state management  
- `apiService` for backend communication  
- UI Components:
  - AuroraHero
  - EntityCard
  - ReasoningChain
  - OutreachCopilot

## Backend Structure
Strict separation into modules:
- Onboarding  
- Partners  
- Outreach  

Adheres to the **Single Responsibility Principle**.

---

# API Documentation Summary

## Base URL
```
/api/v1
```

## Authentication Mechanism
JSON-based REST API interactions.

---

## Major Endpoints

### Channel Discovery
```
POST /api/v1/channels/search
```
Searches healthcare entities based on district and need.  
Returns relevance scores and comparative reasoning.

### Partner Scouting
```
POST /api/v1/partners/search
```
Evaluates and scouts NGOs and Global Funders for project alignment.

### Outreach Generation
```
POST /api/v1/outreach/draft
```
Generates tailored outreach content based on entity ID and clinical parameters.

---

# Database Schema Overview

## Relational Tables

### entities
Primary table for healthcare facilities:
- id
- title
- location data

### metadata
Child table containing:
- num_beds
- specialties

### ngos / funders
Dedicated tables containing:
- description
- level attributes

---

## Vector Implementation

- Embedding column type: `vector(1536)`
- Indexing Strategy: **HNSW (Hierarchical Navigable Small Worlds)**

HNSW provides significantly faster lookup speeds for small to medium datasets compared to IVF.

---

# Performance Considerations

## Frontend Optimization
- Vite HMR for rapid feedback cycles  
- Framer Motion popLayout to prevent layout thrashing  
- Selective hydration for optimized localStorage sync  

## Backend Retrieval
- HNSW indexing ensures sub-second vector retrieval  

## Entity Resolution
- UUID-based entity keys  
- Custom merge logic prevents duplicate NGO/Funder results  

---

# Installation, Setup, Deployment & Security

Installation commands, environment variables, deployment processes, and security configurations follow the standardized best practices of:

- React 19  
- FastAPI  
- Cloud-native application deployment  

Codebase access requires adherence to established DevOps and infrastructure standards.

---

# Future Improvements

Future enhancements will align with:
- Scalable vector database optimization  
- Expanded HRAG reasoning layers  
- Extended NGO/Funder intelligence mapping  
- Advanced outreach personalization models  

---

**End of Documentation**
