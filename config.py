import os
import configparser
from typing import Dict, Any

def load_config() -> Dict[str, Any]:
    """Load configuration from config.ini file."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
    
    # Get actual Desktop path
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    
    # Create default config if it doesn't exist
    if not os.path.exists(config_path):
        config['API'] = {
            'solder_api_url': '',  # Empty instead of placeholder
            'modpack_name': '',  # Empty instead of placeholder
            'build_version': 'latest'
        }
        config['Paths'] = {
            'builds_dir': os.path.join(desktop_path, "Builds")
        }
        with open(config_path, 'w') as configfile:
            config.write(configfile)

    config.read(config_path)
    
    # Ensure builds_dir points to actual Desktop if not set
    if 'builds_dir' not in config['Paths'] or not config['Paths']['builds_dir']:
        config['Paths']['builds_dir'] = os.path.join(desktop_path, "Builds")
        with open(config_path, 'w') as configfile:
            config.write(configfile)

    return {
        'SOLDER_API_URL': config.get('API', 'solder_api_url'),
        'MODPACK_NAME': config.get('API', 'modpack_name'),
        'BUILD_VERSION': config.get('API', 'build_version'),
        'BUILDS_DIR': config.get('Paths', 'builds_dir')
    }

def save_config(config: Dict[str, Any]):
    """Save configuration to config.ini file."""
    config_parser = configparser.ConfigParser()
    config_parser['API'] = {
        'solder_api_url': config['SOLDER_API_URL'],
        'modpack_name': config['MODPACK_NAME'],
        'build_version': config['BUILD_VERSION']
    }
    config_parser['Paths'] = {
        'builds_dir': config['BUILDS_DIR']
    }
    config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
    with open(config_path, 'w') as configfile:
        config_parser.write(configfile)