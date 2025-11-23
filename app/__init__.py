from flask import Flask, render_template
import os
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix
from app.auth.routes import auth_bp
from app.users.routes import users_bp
from app.approvals.routes import approvals_bp
from app.models import db, FormTemplate
from app.utils.forms_config import FORM_TEMPLATES

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")

MOCK_MODE = not all([CLIENT_ID, CLIENT_SECRET, TENANT_ID])

if MOCK_MODE:
    print(" Running in DEMO MODE: Microsoft login is disabled.")

def seed_form_templates():
    """Insert form templates if they don't exist yet."""
    for f in FORM_TEMPLATES:
        if not FormTemplate.query.filter_by(form_code=f["form_code"]).first():
            db.session.add(FormTemplate(**f))
    db.session.commit()

def create_app():
    """Application factory pattern for Flask app."""
    load_dotenv()
    app = Flask(__name__,
                template_folder='ui/templates',
                static_folder='ui/css')

    # Ensure Flask respects X-Forwarded-* headers from reverse proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    #Secret key and server config
    app.secret_key = os.getenv("FLASK_SECRET_KEY")
    # Prefer https when building external URLs
    app.config["PREFERRED_URL_SCHEME"] = "https"

    #Add database config (new lines)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///app.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    # Uploads
    app.config["UPLOAD_FOLDER"] = "uploads/signatures"
    db.init_app(app)

    #Register existing blueprints
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(approvals_bp, url_prefix='/approvals')

    # Create tables and ensure upload directory when the app starts
    with app.app_context():
        db.create_all()
        seed_form_templates()
        # Ensure upload directory exists (relative to project root)
        base_dir = os.path.abspath(os.path.join(app.root_path, os.pardir, app.config["UPLOAD_FOLDER"]))
        os.makedirs(base_dir, exist_ok=True)

    # Home page route
    @app.route('/')
    def index():
        return render_template('home.html')

    return app
