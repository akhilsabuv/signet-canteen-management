from flask import Flask
from .blueprints.auth import auth_bp
from .blueprints.system import system_bp
from .blueprints.reports import reports_bp
from .blueprints.live import live_bp

def create_app():
    app = Flask(__name__)
    # ... existing configuration ...
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(live_bp)
    
    return app 