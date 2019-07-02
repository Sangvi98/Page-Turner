import os
import requests

from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, logging
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from wtforms import Form, StringField, TextAreaField, PasswordField, validators, RadioField
from passlib.hash import sha256_crypt 
from functools import wraps 
from flask_sqlalchemy import SQLAlchemy
import statistics 
import simplejson as json

#creating the application object 
app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=True
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))
database=SQLAlchemy(app)


@app.route("/")
def index():
    return render_template('home.html')

@app.route("/home", methods=["GET","POST"])
def home():
	return render_template(login.html)

# @app.route("/login", methods=["GET","POST"])
# def login():

class RegisterForm(Form):
	name = StringField('Name', [validators.Length(min=1, max=50)])
	username = StringField('Username', [validators.Length(min=4, max=25)])
	email = StringField('Email',[validators.Length(min=6, max=50)])
	password = PasswordField('Password', [
			validators.DataRequired(),
			validators.EqualTo('confirm', message='Passwords do not match')
		])
	confirm = PasswordField('Confirm Password')

@app.route('/register', methods=['GET', 'POST'])
def register():
	form = RegisterForm(request.form)
	if request.method == 'POST' and form.validate():
		name = form.name.data
		email = form.email.data
		username = form.username.data
		password = sha256_crypt.encrypt(str(form.password.data))
		if db.execute("SELECT * FROM users WHERE username = :username", {"username":username}).rowcount != 0: 
			flash('That username is already taken', 'danger')
		else:
			db.execute("INSERT INTO users(name, email, username, password) VALUES(:name, :email, :username, :password)", {
				"name":name, "email":email, "username":username, "password":password})
			db.commit()
			flash('You are now registered and can log in', 'success')
			return redirect(url_for('login'))
	return render_template('register.html', form=form)

#User Login 
@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		#getting user information
		username = request.form['username']
		password_candidate = request.form['password']
		# password_candidate = sha256_crypt.encrypt(str(password_candidate))

		result = db.execute("SELECT * FROM users WHERE username = :username", {"username":username}).first()

		if db.execute("SELECT * FROM users WHERE username = :username", {"username":username}).rowcount != 0:
			#get stored hash 
			password = result.password
			if sha256_crypt.verify(password_candidate, password):
				#passes 
				session['logged_in'] = True
				session['username'] = username
				flash('You are now logged in', 'success')
				return redirect(url_for('browse'))
			else: 
				error = 'Invalid password'
				return render_template('login.html', error=error)

		else: 
			error = 'Username not found'
			return render_template('login.html', error=error)
	return render_template('login.html')

#check if the user is logged in 
def is_logged_in(f):
	@wraps(f)
	def wrap(*args, **kwargs):
		if 'logged_in' in session:
			return f(*args, **kwargs)
		else: 
			flash('Unauthorized, please log in', 'danger')
			return redirect(url_for('login'))
	return wrap

@app.route('/logout')
@is_logged_in
def logout():
	session.clear()
	flash('You are now logged out', 'success')
	return redirect(url_for('index'))

@app.route('/browse', methods=['GET','POST'])
def browse():
	if request.method == 'POST':
	#searchval = request.form['search']
		query = request.form['search']
		query = query.lower()
		query = '%' + query + '%'
		booksSearch = db.execute("SELECT * FROM books WHERE LOWER(title) LIKE :search OR LOWER(isbn) LIKE :search OR LOWER(author) LIKE :search",
			{"search": query}).fetchall()
		for book in booksSearch:
			print(book.title)
		if len(booksSearch) == 0:
			flash('No matching results', 'danger')
		return render_template('browse.html', books=booksSearch)
	return render_template('browse.html')

@app.route('/book/<int:book_id>', methods=['GET', 'POST'])
@is_logged_in
def book(book_id):
	book = db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).first()
	app.logger.info(book.title)
	res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "7OJj9liuJX1PeOn5pRW1A", "isbns": book.isbn})
	data = res.json()
	data = data['books'][0]

	review = db.execute("SELECT * FROM reviews WHERE author = :author AND bookIsbn = :isbn",
		{"author":session['username'], "isbn":book.isbn}).rowcount
	reviews = db.execute("SELECT * FROM reviews WHERE bookIsbn = :isbn",
		{"isbn":book.isbn}).fetchall()
	if review == 0: 
		canReview = True
	else: 
		canReview = False
	return render_template('book.html', book=book, goodreadsinfo=data, canReview=canReview, reviews=reviews)

@app.route('/book/<int:book_id>/addReview', methods=['GET', 'POST'])
@is_logged_in
def addReview(book_id):
	book = db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).first()
	bookTitle = book.title
	bookIsbn = book.isbn
	if request.method == 'POST':
		body = request.form['body']
		rating = request.form['rating']
		author = session['username']
		db.execute("INSERT INTO reviews (body, author, rating, bookTitle, bookIsbn) VALUES (:body, :author, :rating, :bookTitle, :bookIsbn )"
			, {"body": body,
			   "author": author,
			   "rating": rating,
			   "bookTitle": bookTitle,
			   "bookIsbn": bookIsbn})
		db.commit()
		flash('Review Added', 'success')
		return redirect(url_for('book', book_id=book.id))
	return render_template('addReview.html')

@app.route("/api/books/<string:isbn>")
def book_api(isbn):
	isbn = isbn
	booksSearch = db.execute("SELECT * FROM books WHERE isbn = :isbn",
			{"isbn": isbn}).first()
	reviewcount = db.execute("SELECT * FROM reviews WHERE bookIsbn = :isbn", {"isbn":isbn}).rowcount
	reviewavg = db.execute("SELECT AVG(rating) FROM reviews WHERE bookIsbn = :isbn", {"isbn":isbn}).first()
	reviewavg = reviewavg[0]
	if reviewavg == None:
		reviewavg = 0
	#reviewavg = str(reviewavg)
	if booksSearch is None:
		return jsonify({"error": "Invalid book_id"}), 422

	return jsonify({
            "title": booksSearch.title,
            "author": booksSearch.author,
            "year": booksSearch.year,
            "isbn": booksSearch.isbn,
            "review_count": reviewcount,
            "average_score": reviewavg
        })


if __name__=='__main__':
	app.run(debug=True)
		

