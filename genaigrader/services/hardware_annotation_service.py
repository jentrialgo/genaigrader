import logging
import json
import platform
import os
import ollama
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Import the same base URL used elsewhere in the project  
from genaigrader.views.api_views import OLLAMA_BASE_URL


def get_system_hardware_info() -> Dict[str, Optional[str]]:
    """
    Get basic system hardware information using Python standard library.
    
    Returns:
        Dict containing basic system information
    """
    try:
        return {
            'system': platform.system(),
            'machine': platform.machine(), 
            'processor': platform.processor(),
            'platform': platform.platform(),
            'cpu_count': os.cpu_count(),
        }
    except Exception as e:
        logger.warning(f"Could not get system hardware info: {e}")
        return {}


def get_ollama_hardware_info() -> Dict[str, Optional[str]]:
    """
    Get hardware information from ollama if available.
    
    Returns:
        Dict containing ollama hardware information or empty dict if not available
    """
    try:
        # Extract host from OLLAMA_BASE_URL for the client
        host = OLLAMA_BASE_URL
        client = ollama.Client(host=host)
        
        # Test if ollama is running by checking ps
        ps_info = client.ps()
        
        hardware_info = {}
        
        # Try to get system info from ollama API
        try:
            # Some ollama installations provide system info through ps or other endpoints
            if ps_info:
                hardware_info['ollama_running'] = True
                # ps_info typically contains model info and memory usage
                if 'models' in ps_info:
                    total_vram = 0
                    for model in ps_info.get('models', []):
                        if 'size_vram' in model:
                            total_vram += model['size_vram']
                    if total_vram > 0:
                        hardware_info['gpu_vram_mb'] = total_vram // (1024 * 1024)
            
            # Try to get additional system info from ollama version endpoint
            version_url = f"{OLLAMA_BASE_URL}/api/version"
            response = requests.get(version_url, timeout=2)
            if response.status_code == 200:
                version_data = response.json()
                hardware_info['ollama_version'] = version_data.get('version')
                
        except Exception as e:
            logger.debug(f"Could not get detailed ollama hardware info: {e}")
            
        return hardware_info
        
    except Exception as e:
        logger.debug(f"Could not connect to ollama for hardware info: {e}")
        return {}


def get_hardware_annotation(model_instance) -> Optional[str]:
    """
    Get standardized hardware annotation for an evaluation.
    
    Args:
        model_instance: The Model instance being used
        
    Returns:
        JSON string with hardware information or None for external models
    """
    if model_instance.is_external:
        return None  # External models don't need hardware annotation
    
    # Collect hardware information for local models
    hardware_info = {}
    
    # Get ollama-specific info first
    ollama_info = get_ollama_hardware_info()
    if ollama_info:
        hardware_info.update(ollama_info)
    
    # Get basic system info
    system_info = get_system_hardware_info()
    if system_info:
        hardware_info.update(system_info)
    
    # Return as JSON string if we have any info
    if hardware_info:
        try:
            return json.dumps(hardware_info, sort_keys=True)
        except Exception as e:
            logger.warning(f"Could not serialize hardware info to JSON: {e}")
    
    return None