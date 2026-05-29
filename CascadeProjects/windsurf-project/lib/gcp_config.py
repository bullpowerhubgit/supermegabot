"""
GCP Configuration Library
Shared configuration for all RudiBot tools
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_PATH = Path(__file__).parent.parent / "RudiBot-Secure-API" / "gcp-config.json"


class GCPConfig:
    """GCP Configuration singleton"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = None
            cls._instance.load_config()
        return cls._instance
    
    def load_config(self) -> None:
        """Load configuration from JSON file"""
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, 'r') as f:
                    self._config = json.load(f)
            else:
                print(f"Warning: GCP config not found at {CONFIG_PATH}")
                self._config = self.get_default_config()
        except Exception as e:
            print(f"Error loading GCP config: {e}")
            self._config = self.get_default_config()
    
    def get_default_config(self) -> Dict:
        """Return default configuration"""
        return {
            "project": {
                "id": "gen-lang-client-0895465231",
                "number": "1023902745882",
                "name": "Shopy"
            },
            "apis": {
                "enabled": []
            }
        }
    
    @property
    def project_id(self) -> str:
        """Get project ID"""
        return self._config.get("project", {}).get("id", "")
    
    @property
    def project_number(self) -> str:
        """Get project number"""
        return self._config.get("project", {}).get("number", "")
    
    @property
    def project_name(self) -> str:
        """Get project name"""
        return self._config.get("project", {}).get("name", "")
    
    @property
    def apis(self) -> List[Dict]:
        """Get enabled APIs"""
        return self._config.get("apis", {}).get("enabled", [])
    
    @property
    def api_list(self) -> List[str]:
        """Get list of API names"""
        return [api["name"] for api in self.apis]
    
    @property
    def billing_account(self) -> str:
        """Get billing account"""
        return self._config.get("project", {}).get("billing_account", "")
    
    def has_api(self, api_name: str) -> bool:
        """Check if API is enabled"""
        return api_name in self.api_list
    
    @property
    def auth_method(self) -> str:
        """Get authentication method"""
        return self._config.get("auth", {}).get("method", "gcloud")
    
    @property
    def is_cloud_shell(self) -> bool:
        """Check if running in Cloud Shell"""
        return self._config.get("auth", {}).get("cloud_shell", False)
    
    def to_dict(self) -> Dict:
        """Return full configuration as dict"""
        return self._config


# Singleton instance
gcp_config = GCPConfig()
