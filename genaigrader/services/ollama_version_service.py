import logging
import ollama
import requests

logger = logging.getLogger(__name__)

# Import the same base URL used elsewhere in the project
from genaigrader.views.api_views import OLLAMA_BASE_URL

def get_ollama_version():
    """
    Get the current ollama version using the ollama library and API.
    
    Returns:
        str or None: Version string or None if unable to determine
    """
    try:
        # Extract host from OLLAMA_BASE_URL for the client
        # OLLAMA_BASE_URL is something like "http://localhost:11434"
        host = OLLAMA_BASE_URL
        
        client = ollama.Client(host=host)
        
        # Test if ollama is actually running by listing models
        models = client.list()
        
        if models is not None:  # Ollama is running
            # Try to get version from API endpoint directly
            try:
                version_url = f"{OLLAMA_BASE_URL}/api/version"
                response = requests.get(version_url, timeout=2)
                if response.status_code == 200:
                    version_data = response.json()
                    if 'version' in version_data:
                        return version_data['version']
            except Exception as e:
                logger.warning(f"Could not get version from API endpoint: {e}")
            
            # If we can connect to Ollama but can't get version, return None
            # We don't know what version it is
            logger.warning("Connected to Ollama but could not determine version")
            return None
        
    except Exception as e:
        logger.warning(f"Could not connect to ollama or determine version: {e}")
    
    return None

def get_evaluation_ollama_version(model_instance):
    """
    Get ollama version for an evaluation, but only for non-external models.
    
    Args:
        model_instance: The Model instance being used
    
    Returns:
        str or None: Ollama version for local models, None for external models
    """
    if model_instance.is_external:
        return None  # External models don't use ollama
    
    return get_ollama_version()
