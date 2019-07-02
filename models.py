from flask_sqlalchemy import SQLAlchemy
from application import db
from flask import Flask 

db = SQLAlchemy(app)
db.create_all()

class User(db.Model):
	__tablename__="users"
	id = db.Column(db.Integer, primary_key=True)
	username = db.Column(db.String, nullable=False)
	password = db.Column(db.String, nullable=False)
