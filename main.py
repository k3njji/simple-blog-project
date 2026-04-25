from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from forms import CreatePostForm, RegisterForm, LoginForm, AddComment
import os
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

'''
Make sure the required packages are installed: 
Open the Terminal in PyCharm (bottom left). 

On Windows type:
python -m pip install -r requirements.txt

On MacOS type:
pip3 install -r requirements.txt

This will install the packages from the requirements.txt for this project.
'''

app = Flask(__name__)
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '0'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "font-src 'self' https: data:;"
    )
    return response
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
ckeditor = CKEditor(app)
Bootstrap5(app)

# TODO: Configure Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)

# CREATE DATABASE
class Base(DeclarativeBase):
    pass

database_url = os.environ.get('DATABASE_URL')

if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)

# database_url = 'sqlite:///C:/Projects/Blogs/instance/posts.db'

app.config['SQLALCHEMY_DATABASE_URI'] = database_url

db = SQLAlchemy(model_class=Base)
db.init_app(app)

def user_or_ip():
    if current_user.is_authenticated:
        return str(current_user.id)
    return get_remote_address()

limiter = Limiter(
    user_or_ip,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)


# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)

    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    author: Mapped["User"] = relationship("User", back_populates="posts")

    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="post")


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    names: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String, nullable=False)

    posts: Mapped[list["BlogPost"]] = relationship("BlogPost", back_populates="author")
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="user")


class Comment(db.Model):
    __tablename__ = 'comments'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    comment: Mapped[str] = mapped_column(Text, nullable=False)

    post_id: Mapped[int] = mapped_column(ForeignKey('blog_posts.id'))
    post: Mapped["BlogPost"] = relationship("BlogPost", back_populates="comments")

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    user: Mapped["User"] = relationship("User", back_populates="comments")

# TODO: Create a User table for all your registered users. 

with app.app_context():
    db.create_all()


# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per minute")
def register():
    form = RegisterForm()
    if not current_user.is_authenticated:
        if form.validate_on_submit():

            existing_user = db.session.execute(
                db.select(User).where(User.email == form.email.data)
            ).scalar()

            if existing_user:
                flash("Email already registered. Please login.")
                return redirect(url_for('login'))

            new_user = User(
                names=form.name.data,
                email=form.email.data,
                password=generate_password_hash(
                    form.password.data,
                    method='pbkdf2:sha256',
                    salt_length=8
                )
            )

            db.session.add(new_user)
            db.session.commit()

            return redirect(url_for('get_all_posts'))

        return render_template("register.html", form=form)
    else:
        abort(403)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def login():
    form = LoginForm()
    if not current_user.is_authenticated:
        if request.method == 'POST':
            print(1)
            if form.validate_on_submit():
                user = db.session.execute(
                    db.select(User).where(User.email == form.email.data)
                ).scalar()
                print(2)
                if user and check_password_hash(user.password, form.password.data):
                    print(3)
                    login_user(user)
                    return redirect(url_for('get_all_posts'))
                else:
                    flash("Invalid email or password")
                    return redirect(url_for('login'))

        return render_template("login.html", form=form)
    else:
        abort(403)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():

    page = request.args.get('page', 1, type=int)
    per_page = 10

    pagination = db.paginate(
        db.select(BlogPost).order_by(BlogPost.date.desc()),
        page=page,
        per_page=per_page,
        error_out=False
    )

    # result = db.session.execute(db.select(BlogPost))
    posts = pagination.items
    # print(posts)   # <-- add this
    return render_template("index.html", all_posts=posts, pagination=pagination)

# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>")
def show_post(post_id):
    comment = AddComment()
    requested_post = db.get_or_404(BlogPost, post_id)
    print(requested_post)
    return render_template("post.html", post=requested_post, form=comment)


# TODO: Use a decorator so only an admin user can create a new post
@app.route("/new-post", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def add_new_post():
    if current_user.is_authenticated:
        form = CreatePostForm()
        if request.method == 'POST':
            if form.validate_on_submit():
                new_post = BlogPost(
                    title=form.title.data,
                    subtitle=form.subtitle.data,
                    body=form.body.data,
                    img_url=form.img_url.data,
                    author=current_user,
                    date=date.today().strftime("%B %d, %Y")
                )
                db.session.add(new_post)
                db.session.commit()
                return redirect(url_for("get_all_posts"))
        return render_template("make-post.html", form=form)
    else:
        abort(403)

@app.route('/new-comment/<int:post_id>', methods=['POST'])
@limiter.limit("10 per minute")
def add_comment(post_id):
    if request.method == 'POST':
        post = db.get_or_404(BlogPost, post_id)
        print(1)

        if not current_user.is_authenticated:
            flash("Please login to comment")
            return redirect(url_for('login'))

        form = AddComment()

        if form.validate_on_submit():
            new_comment = Comment(
                comment=form.comment.data,
                user=current_user,
                post=post
            )

            db.session.add(new_comment)
            db.session.commit()

        return redirect(url_for('show_post', post_id=post.id))
    else:
        return redirect(url_for('show_post', post_id=post.id))


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    if (current_user.is_authenticated and current_user.id == post.author_id):
        post = db.get_or_404(BlogPost, post_id)
        edit_form = CreatePostForm(
            title=post.title,
            subtitle=post.subtitle,
            img_url=post.img_url,
            author=post.author,
            body=post.body
        )
        if edit_form.validate_on_submit():
            post.title = edit_form.title.data
            post.subtitle = edit_form.subtitle.data
            post.img_url = edit_form.img_url.data
            post.author = current_user
            post.body = edit_form.body.data
            db.session.commit()
            return redirect(url_for("show_post", post_id=post.id))
        return render_template("make-post.html", form=edit_form, is_edit=True)
    else:
        abort(404)

@app.route("/delete/<int:post_id>")
def delete_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    if current_user.is_authenticated and current_user.id == post.author_id:
        post_to_delete = db.get_or_404(BlogPost, post_id)
        db.session.delete(post_to_delete)
        db.session.commit()
        return redirect(url_for('get_all_posts'))
    else:
        abort(403)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


if __name__ == "__main__":
    app.run()