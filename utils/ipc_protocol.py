"""
Inter-Process Communication Protocol for ExLibris Automator
Standardizes communication between Discord Bot, Flask GUI, Terminal, and Worker processes
"""

import os
import json
import time
from typing import Dict, Any, Optional, Literal
from .asset_type_utils import normalize_config_mode, normalize_asset_type_from_parser, config_mode_to_asset_type


class IPCProtocol:
    """
    Centralized handler for all IPC communication patterns.
    Ensures consistent message format and asset type normalization across all components.
    """
    
    # Message types
    REQUEST = "request"
    RESPONSE = "response"
    
    def __init__(self, working_dir: Optional[str] = None):
        """
        Initialize IPC protocol handler.
        
        Args:
            working_dir: Directory where control files are located (default: cwd)
        """
        self.working_dir = working_dir or os.getcwd()
    
    # ===== Core Message Handling =====
    
    @staticmethod
    def create_message(msg_type: Literal["request", "response"], 
                      operation: str, 
                      **kwargs) -> Dict[str, Any]:
        """
        Create a standardized message with timestamp and operation.
        
        Args:
            msg_type: Either "request" or "response"
            operation: Operation name (e.g., "add_citation", "set_asset_type")
            **kwargs: Additional data fields
            
        Returns:
            Dictionary with standardized message structure
        """
        message = {
            "type": msg_type,
            "operation": operation,
            "timestamp": time.time(),
        }
        message.update(kwargs)
        return message
    
    @staticmethod
    def is_response(data: Dict[str, Any]) -> bool:
        """Check if a message is a response (has 'success' or 'type'='response')."""
        return "success" in data or data.get("type") == IPCProtocol.RESPONSE
    
    def write_message(self, filename: str, data: Dict[str, Any]) -> bool:
        """
        Write a message to a control file.
        
        Args:
            filename: Name of the file to write
            data: Message data dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            filepath = os.path.join(self.working_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    def read_message(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Read a message from a control file.
        
        Args:
            filename: Name of the file to read
            
        Returns:
            Message data dictionary, or None if file doesn't exist or is invalid
        """
        try:
            filepath = os.path.join(self.working_dir, filename)
            if not os.path.exists(filepath):
                return None
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    def remove_file(self, filename: str) -> bool:
        """Remove a control file."""
        try:
            filepath = os.path.join(self.working_dir, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
            return True
        except Exception:
            return False
    
    def wait_for_response(self, filename: str, timeout: float = 5.0, 
                         poll_interval: float = 0.2) -> Optional[Dict[str, Any]]:
        """
        Wait for a response file to be written by checking for 'success' field.
        
        Args:
            filename: Name of the file to monitor
            timeout: Maximum wait time in seconds
            poll_interval: How often to check for updates (seconds)
            
        Returns:
            Response data if received within timeout, None otherwise
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            data = self.read_message(filename)
            if data and self.is_response(data):
                return data
            time.sleep(poll_interval)
        return None
    
    # ===== Asset Type Normalization =====
    
    @staticmethod
    def normalize_asset_type_input(asset_type: str, source: str = "user") -> str:
        """
        Normalize asset type from any source.
        
        Args:
            asset_type: Raw asset type string
            source: Source of the asset type ("user", "parser", "config")
            
        Returns:
            Normalized asset type suitable for the target context
        """
        if source == "parser":
            # Parser returns types like "conference_presentation" -> normalize to config mode
            return normalize_config_mode(asset_type)
        elif source == "config":
            # Config stores modes like "presentation" -> already normalized
            return normalize_config_mode(asset_type)
        else:  # user input
            # User input could be anything -> normalize to config mode
            return normalize_config_mode(asset_type)
    
    @staticmethod
    def asset_type_to_worker_format(asset_type: str) -> str:
        """
        Convert asset type to worker format (e.g., "presentation" -> "presentation").
        Worker uses the same format as config modes.
        """
        return normalize_config_mode(asset_type)
    
    @staticmethod
    def asset_type_to_display(asset_type: str) -> str:
        """Convert asset type to human-readable display format."""
        type_map = {
            "presentation": "Conference Presentation",
            "poster": "Conference Poster",
            "proceedings": "Conference Proceedings",
            "journal_article": "Journal Article",
            "book_chapter": "Book Chapter",
            "abstract": "Abstract",
            "technical_documentation": "Technical Documentation",
            "auto": "Auto (Detect Type)",
        }
        normalized = normalize_config_mode(asset_type)
        return type_map.get(normalized, normalized.replace("_", " ").title())
    
    # ===== High-Level Operations =====
    
    def send_citation_to_worker(self, channel_id: int, citation_text: str, 
                               asset_type: str, researcher: str,
                               citation_id: str, message_id: int, author: str,
                               parsed_data: Optional[Dict] = None) -> bool:
        """
        Send a citation to the worker for processing.
        Normalizes asset type before sending.
        
        Args:
            channel_id: Discord channel ID
            citation_text: Citation text to process
            asset_type: Asset type (will be normalized)
            researcher: Researcher name
            citation_id: Unique citation ID
            message_id: Discord message ID
            author: Author who submitted the citation
            parsed_data: Optional pre-parsed citation data
            
        Returns:
            True if message was sent successfully
        """
        control_file = f"citation_control_{channel_id}.json"
        normalized_type = self.asset_type_to_worker_format(asset_type)
        
        data = {
            "text": citation_text,
            "asset_type": normalized_type,
            "message_id": message_id,
            "citation_id": citation_id,
            "author": author,
            "researcher": researcher,
            "parsed": parsed_data
        }
        
        return self.write_message(control_file, data)
    
    def read_worker_status(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Read status from worker."""
        status_file = f"citation_status_{channel_id}.json"
        return self.read_message(status_file)
    
    def send_gui_request(self, operation: str, **kwargs) -> bool:
        """
        Send a request from GUI to bot.
        Asset types are automatically normalized if present.
        
        Args:
            operation: Operation name
            **kwargs: Additional request parameters
            
        Returns:
            True if request was sent successfully
        """
        # Normalize asset_type if present
        if "asset_type" in kwargs:
            kwargs["asset_type"] = normalize_config_mode(kwargs["asset_type"])
        
        filename = f"gui_{operation}.json"
        data = self.create_message(self.REQUEST, operation, **kwargs)
        return self.write_message(filename, data)
    
    def read_gui_response(self, operation: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Read response from bot for a GUI request.
        
        Args:
            operation: Operation name
            timeout: Maximum wait time in seconds
            
        Returns:
            Response data or None if timeout
        """
        filename = f"gui_{operation}.json"
        return self.wait_for_response(filename, timeout=timeout)
    
    def send_gui_response(self, operation: str, success: bool, **kwargs) -> bool:
        """
        Send a response from bot to GUI.
        
        Args:
            operation: Operation name
            success: Whether the operation succeeded
            **kwargs: Additional response data
            
        Returns:
            True if response was sent successfully
        """
        filename = f"gui_{operation}.json"
        data = self.create_message(self.RESPONSE, operation, success=success, **kwargs)
        return self.write_message(filename, data)
    
    # ===== Specific Operations =====
    
    def gui_add_citation(self, text: str, asset_type: Optional[str] = None) -> Dict[str, Any]:
        """
        GUI sends request to add a citation.
        
        Returns:
            Response dict with success status
        """
        request_data = {"text": text}
        if asset_type:
            request_data["asset_type"] = normalize_config_mode(asset_type)
        
        if not self.write_message("gui_add_citation.json", request_data):
            return {"success": False, "error": "Failed to write request"}
        
        response = self.wait_for_response("gui_add_citation.json", timeout=5.0)
        if response:
            self.remove_file("gui_add_citation.json")
            return response
        return {"success": False, "error": "Timeout waiting for response"}
    
    def gui_set_asset_type(self, asset_type: str) -> Dict[str, Any]:
        """
        GUI sends request to set asset type.
        Automatically normalizes the asset type.
        
        Returns:
            Response dict with success status
        """
        normalized = normalize_config_mode(asset_type)
        
        if not self.write_message("gui_set_asset_type.json", {"asset_type": normalized}):
            return {"success": False, "error": "Failed to write request"}
        
        response = self.wait_for_response("gui_set_asset_type.json", timeout=5.0)
        if response:
            return response
        return {"success": False, "error": "Timeout waiting for response"}
    
    def gui_set_researcher(self, researcher: str) -> Dict[str, Any]:
        """
        GUI sends request to set researcher.
        
        Returns:
            Response dict with success status
        """
        if not self.write_message("gui_set_researcher.json", {"researcher": researcher}):
            return {"success": False, "error": "Failed to write request"}
        
        response = self.wait_for_response("gui_set_researcher.json", timeout=5.0)
        if response:
            return response
        return {"success": False, "error": "Timeout waiting for response"}


# Singleton instance for global access
_protocol_instance = None

def get_protocol(working_dir: Optional[str] = None) -> IPCProtocol:
    """Get or create the global IPC protocol instance."""
    global _protocol_instance
    if _protocol_instance is None or (working_dir and working_dir != _protocol_instance.working_dir):
        _protocol_instance = IPCProtocol(working_dir)
    return _protocol_instance
