from flask import Flask
from .blueprints.live import live_bp

def create_app():
    app = Flask(__name__)
    # ... existing configuration ...
    
    # Register blueprints
    app.register_blueprint(live_bp)
    # ... other blueprints ... 
    
    return app 