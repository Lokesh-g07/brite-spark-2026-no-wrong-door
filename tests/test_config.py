import pytest
import os
import importlib

def test_config_validation():
    """Test that invalid config values raise a ValueError on module import."""
    # Temporarily set an invalid environment variable
    os.environ["XML_MAX_ATTEMPTS"] = "0"
    
    with pytest.raises(ValueError, match="XML_MAX_ATTEMPTS must be >= 1"):
        import app.config
        importlib.reload(app.config)
        
    # Clean up and test a valid reload
    os.environ["XML_MAX_ATTEMPTS"] = "3"
    importlib.reload(app.config)
    assert app.config.XML_MAX_ATTEMPTS == 3
