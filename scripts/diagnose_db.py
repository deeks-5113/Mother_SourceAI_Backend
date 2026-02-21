import asyncio
import logging
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from modules.config import get_settings, get_supabase_client
from modules.database import ChannelRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnostics")

async def test_supabase():
    settings = get_settings()
    logger.info("Settings loaded. Supabase URL: %s", settings.supabase_url)
    
    try:
        supabase = get_supabase_client(settings)
        # Test basic connection
        logger.info("Testing basic connection...")
        response = supabase.table("entities").select("count", count="exact").limit(1).execute()
        logger.info("Basic connection successful. Row count: %s", response.count)
        
        # Test RPC existence
        logger.info("Testing RPC 'search_entities'...")
        # Dummy vector for testing
        dummy_vector = [0.1] * 1536
        try:
            rpc_response = supabase.rpc(
                "search_entities",
                {
                    "query_embedding": dummy_vector,
                    "filter_district": "NonExistent",
                    "filter_environment": "NonExistent",
                    "match_count": 1,
                }
            ).execute()
            logger.info("RPC call executed successfully (returned %d results).", len(rpc_response.data or []))
        except Exception as e:
            logger.error("RPC 'search_entities' failed: %s", e)
            logger.info("This might mean the function hasn't been created in Supabase. Run sql/setup_entities.sql in your Supabase SQL Editor.")
            
    except Exception as e:
        logger.error("Database connection failed: %s", e)

if __name__ == "__main__":
    asyncio.run(test_supabase())
