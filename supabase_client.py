import logging
from supabase import Client, create_client
from modules.config import get_settings

logger = logging.getLogger(__name__)

def get_supabase_client() -> Client:
    """
    Returns a configured Supabase client instance.
    This can be used in root-level scripts or as a standalone provider.
    """
    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_key:
        logger.error("Supabase URL or Key not found in environment settings.")
        raise ValueError("Missing Supabase configuration.")
    
    return create_client(settings.supabase_url, settings.supabase_key)

# Singleton instance for simple root-level access
supabase_client = get_supabase_client()
