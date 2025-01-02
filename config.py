import os
import configparser
from typing import Dict, Any

def load_config() -> Dict[str, Any]:
    """Load configuration from config.ini file."""
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'config.ini')
    
    # Get actual Desktop path
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
    
    # Default values with placeholders
    defaults = {
        'API': {
            'solder_api_url': 'http://example.com/api/modpack/',  # Placeholder URL
            'modpack_name': 'your-modpack-name',  # Placeholder modpack name
            'build_version': 'latest'
        },
        'Paths': {
            'builds_dir': os.path.join(desktop_path, "Builds")  # Use actual Desktop path
        }
    }

    # Create default config if it doesn't exist
    if not os.path.exists(config_path):
        config['API'] = {
            'solder_api_url': 'http://example.com/api/modpack/  ; Replace with your Solder API URL',
            'modpack_name': 'your-modpack-name  ; Replace with your modpack name',
            'build_version': 'latest  ; Replace with the desired build version or keep as "latest"'
        }
        config['Paths'] = {
            'builds_dir': os.path.join(desktop_path, "Builds  ; Replace with your builds directory path")
        }
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        print("Default config.ini generated. Please fill in the required information and run the script again.")
        return None
    else:
        config.read(config_path)
        # Check if placeholders are still present
        if 'example.com' in config['API']['solder_api_url'] or 'your-modpack-name' in config['API']['modpack_name']:
            print("Please fill in the required information in config.ini and run the script again.")
            return None
        # Always ensure builds_dir points to actual Desktop
        config['Paths']['builds_dir'] = os.path.join(desktop_path, "Builds")
        with open(config_path, 'w') as configfile:
            config.write(configfile)

    return {
        'SOLDER_API_URL': config.get('API', 'solder_api_url'),
        'MODPACK_NAME': config.get('API', 'modpack_name'),
        'BUILD_VERSION': config.get('API', 'build_version'),
        'BUILDS_DIR': config.get('Paths', 'builds_dir')
    }