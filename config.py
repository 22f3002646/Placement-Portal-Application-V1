import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///instance/placement_portal.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
