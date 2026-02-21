import json
import os
import sys
import logging
from typing import List, Dict, Any
from pathlib import Path

# Add project root to sys.path to allow importing from app
sys.path.append(str(Path(__file__).parent.parent))

from modules.config import get_settings
from openai import OpenAI
from supabase import create_client, Client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s"
)
logger = logging.getLogger("ingest_hrag")

def get_embedding(client: OpenAI, text: str, model: str, dimensions: int) -> List[float]:
    """Generate embedding for a given text using OpenAI."""
    try:
        response = client.embeddings.create(
            input=[text.replace("\n", " ")],
            model=model,
            dimensions=dimensions
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error("Error generating embedding: %s", e)
        return []

def flatten_hrag_structure(data: Dict[str, Any], district: str, environment: str) -> List[Dict[str, Any]]:
    """Flatten the nested HRAG structure into individual chunks with metadata."""
    flattened_data = []
    
    def traverse(node: Dict[str, Any]):
        current_level = node.get("level", "")
        current_title = node.get("title", "")
        current_summary = node.get("semantic_summary", "")
        
        # If this node has chunks, add them
        if "chunks" in node:
            for chunk in node["chunks"]:
                item = {
                    "level": current_level,
                    "title": current_title,
                    "semantic_summary": current_summary,
                    "content": chunk.get("text", ""),
                    "source_id": chunk.get("source_id", ""),
                    "district": district,
                    "environment": environment
                }
                flattened_data.append(item)
        
        # Recurse into children
        if "children" in node:
            for child in node["children"]:
                traverse(child)

    for entry in data.get("document_structure", []):
        traverse(entry)
        
    return flattened_data

def ingest_file(file_path: str, district: str, environment: str, supabase: Client, openai_client: OpenAI, settings: Any):
    """Process and ingest a single HRAG JSON file."""
    logger.info("Processing file: %s (District: %s, Env: %s)", file_path, district, environment)
    
    if not os.path.exists(file_path):
        logger.warning("File not found: %s", file_path)
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    flattened_items = flatten_hrag_structure(data, district, environment)
    logger.info("Found %d chunks in %s", len(flattened_items), file_path)
    
    for item in flattened_items:
        # Generate embedding for the title + content for better contextual retrieval
        text_to_embed = f"{item['title']}: {item['content']}"
        embedding = get_embedding(
            openai_client, 
            text_to_embed, 
            settings.embedding_model, 
            settings.embedding_dimensions
        )
        
        if not embedding:
            logger.error("Skipping chunk %s due to embedding failure.", item['source_id'])
            continue
            
        item['embedding'] = embedding
        
        # Insert into Supabase 'entities' table
        try:
            supabase.table("entities").insert(item).execute()
            logger.debug("Inserted chunk %s", item['source_id'])
        except Exception as e:
            logger.error("Error inserting chunk %s: %s", item['source_id'], e)

def main():
    settings = get_settings()
    
    if not all([settings.supabase_url, settings.supabase_key, settings.openai_api_key]):
        logger.error("Missing critical configuration in .env. check SUPABASE_URL, SUPABASE_KEY, and OPENAI_API_KEY.")
        return

    # Initialize Clients
    supabase = create_client(settings.supabase_url, settings.supabase_key)
    openai_client = OpenAI(api_key=settings.openai_api_key)
    
    # Configuration for ingestion
    # Note: In a real production scenario, these might be passed via CLI arguments
    ingestion_configs = [
        {"path": "data/sample1.json", "district": "All Districts", "environment": "General"},
        {"path": "data/sample2.json", "district": "Srikakulam", "environment": "Urban"},
        {"path": "data/sample3.json", "district": "Krishna", "environment": "Urban"},
    ]
    
    for config in ingestion_configs:
        ingest_file(
            config["path"], 
            config["district"], 
            config["environment"], 
            supabase, 
            openai_client,
            settings
        )
    
    logger.info("Ingestion process completed.")

if __name__ == "__main__":
    main()
