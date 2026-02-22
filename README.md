# MotherSource AI

## Project Overview
MotherSource AI is a production-grade backend ecosystem and specialized, state-driven search and recommendation platform.

---

## Problem Statement
Traditional keyword search fails on complex maternal health queries, leaving a gap between maternal health initiatives and rural field outreach.

---

## Solution Approach
The platform leverages a **Hierarchical Retrieval-Augmented Generation (HRAG)** engine. This transforms unstructured project goals and complex clinical match-making data into precise matches, actionable outreach strategies, and reasoned intelligence.

---

## Target Users
The application serves as a mission-critical tool for connecting expectant mothers across Andhra Pradesh and Telangana with:

- Mothers
- Clinical healthcare channels  
- High-aligned NGOs  
- Primary Health Centres (PHCs)  
- Mission-aligned implementation and funding partners  

---

## Impact
MotherSource AI creates a tangible impact by bridging the critical gap between maternal health needs and healthcare infrastructure. It connects rural and expectant mothers directly to equipped clinical healthcare channels, high-capacity NGOs, and global funders.

By offloading semantic weighting to AI, the system ensures that every outreach and partnership initiated is grounded in data-driven alignment. This ultimately transforms complex clinical matchmaking data into actionable outreach strategies that support and scale maternal health initiatives.

---

# System Architecture Overview

The system utilizes a modern cloud-native **3-tier architecture**.

## 1️⃣ Client Tier
An interaction layer sending JSON-based requests via REST API.

## 2️⃣ API Gateway & Service Layer
Built on **FastAPI** for its asynchronous capabilities, this layer features:
- Modular architecture  
- Strict service separation  
- Dependency injection  

## 3️⃣ Data Layer
The platform uses a **Supabase Stack**, utilizing:
- PostgreSQL for relational metadata  
- pgvector for native vector storage and similarity search  

---

# Tech Stack

## Frontend
- React 19 (Vite)  
- Tailwind CSS 4  
- Framer Motion  

## Backend
- FastAPI  
- OpenAI (text-embedding-3-small and GPT-4o models)  

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
The system operates in three stages:
1. Metadata filtering for pruning  
2. Dense vector search utilizing cosine distance for retrieval  
3. LLM reasoning via GPT-4o for re-ranking and inference  

### Reasoning Protocol
The UI exposes the AI’s internal reasoning via an interactive **"Analyze Protocol"** trigger, explaining comparative alignment based on search parameters.

### Progressive Loading Design
A global interceptor obscures the workspace with high-fidelity animations during HRAG/LLM operations to maintain user engagement.

---

# API Documentation Summary

## Base URL
```
/api/v1
```

## Authentication Mechanism
Interactions operate via JSON-based requests over a REST API.

---

## Major Endpoints

### Channel Discovery
```
POST /api/v1/channels/search
```
Searches healthcare entities based on district and need, returning relevance scores and comparative reasoning.

### Partner Scouting
```
POST /api/v1/partners/search
```
Evaluates and scouts NGOs and Global Funders for project alignment.

### Outreach Generation
```
POST /api/v1/outreach/draft
```
Sends an entity ID and clinical parameters to generate tailored, context-aware outreach content.

---

# Database Schema Overview

## Relational Tables

### entities
Primary table for healthcare facilities, containing:
- id  
- title  
- location data  

### metadata
Child table for entities containing:
- num_beds  
- specialties  

### ngos / funders
Dedicated tables for partners containing:
- description  
- level attributes  

---

# Vector Implementation

- Embedding column type: `vector(1536)`  
- Indexing strategy: **HNSW (Hierarchical Navigable Small Worlds)**  

HNSW provides significantly faster lookup speeds for small to medium datasets compared to IVF.

---

# Performance Considerations

## Frontend Rendering Optimization
- Vite HMR ensures near-instant developer feedback cycles  
- Framer Motion popLayout optimizes DOM transitions  
- Selective hydration syncs only critical state objects to localStorage  

## Backend Retrieval
- HNSW indexing ensures sub-second retrieval from the vector space  

## Entity Resolution
- All entities are keyed by unique UUIDs  
- Custom merge logic deduplicates results when querying NGOs and Funders  

---

# Installation, Setup, Deployment, Security & Future Improvements

Installation commands, environment variable requirements, deployment procedures, security protocols, and contribution guidelines follow standard **React 19** and **FastAPI** conventions.

Codebase access requires adherence to cloud-native application deployment best practices.

---

**End of Document**
