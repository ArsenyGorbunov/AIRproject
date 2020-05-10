import os
import flask
import requests
import sys
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
from googleapiclient.http import MediaIoBaseDownload

import io
import json
import re

import json
import datetime
from flask import Flask, url_for, redirect, \
    render_template, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, login_user, \
    logout_user, current_user, UserMixin
from requests.exceptions import HTTPError
from requests_oauthlib import OAuth2Session
from flask_wtf import FlaskForm
from wtforms import StringField, FileField
from wtforms.validators import DataRequired
from googletrans import Translator

from notebook_parse import parse_ipynb
import nltk
import math
from collections import Counter
nltk.download('punkt')

from process import update_inverted_index, find

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    """Base config"""
    APP_NAME = "Test Google Login"
    SECRET_KEY = os.environ.get("SECRET_KEY") or "somethingsecret"

class DevConfig(Config):
    """Dev config"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, "test.db")

class ProdConfig(Config):
    """Production config"""
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, "prod.db")

config = {
    "dev": DevConfig,
    "prod": ProdConfig,
    "default": DevConfig
}

"""APP creation and configuration"""
# initiate the flask app 
app = Flask(__name__)
# app.secret_key = b'replace secret key'
# remove warning notifications
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config.from_object(config['dev'])
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.session_protection = "strong"

# create class that represents a table in database
db.metadata.clear()

""" DB Models """
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    id = db.Column('user_id', db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    avatar = db.Column(db.String(200))
    credentials = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow())
    user_notebooks = db.relationship('Notebook', backref="user", lazy='dynamic')
    user_indicies = db.relationship('Index', backref="user", lazy='dynamic')

class Notebook(db.Model):
    __tablename__ = 'notebooks'
    id = db.Column('notebook_id', db.Integer, primary_key=True) 
    colab_id = db.Column(db.String(50))
    creation_time = db.Column(db.String(50))
    name = db.Column(db.String(50))
    raw_data = db.Column(db.JSON)
    processed_data = db.Column(db.JSON)
    link = db.Column(db.String(50))
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))

class Index(db.Model):
    __tablename__ = 'indicies'
    id = db.Column('indicies_id', db.Integer, primary_key=True) 
    inverted_index = db.Column(db.JSON)
    doc_lengths = db.Column(db.JSON)
    doc_index = db.Column(db.JSON)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id'))

db.create_all()
# This variable specifies the name of a file that contains the OAuth 2.0
# information for this application, including its client_id and client_secret.
CLIENT_SECRETS_FILE = "client_secret.json" # нужно будет убрать в системные переменные 

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account and requires requests to use an SSL connection.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly', \
        'https://www.googleapis.com/auth/userinfo.profile', \
        'https://www.googleapis.com/auth/userinfo.email',\
        'https://www.googleapis.com/auth/drive']
API_SERVICE_NAME = 'drive'
API_VERSION = 'v3'

def create_database_instance(item,drive,in_database):
    file = (item['id'], item['name'])
    data = gdrive_download_file(drive, file)
    notebook = Notebook()
    notebook.name = item['name']
    notebook.raw_data = data
    notebook.processed_data = parse_ipynb(data)
    notebook.creation_time = item['modifiedTime']
    notebook.user_id = current_user.id
    notebook.link = item['webViewLink']
    notebook.colab_id = item['id']
    db.session.add(notebook)
    db.session.commit()
    print(f'{item["name"]} added to database')
    in_database.append(item)

class button_class():
        def __init__(self, name, button1text, button2text, button3text, link):
            self.name = name
            self.button1text = button1text
            self.button1hash = hash(name + '1') 
            self.button2text = button2text
            self.button2hash = hash(name + '2')
            self.button3text = button3text
            self.button3hash = hash(name + '3')
            self.link = link 

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
""" OAuth Session creation """

@app.route('/')
@login_required
def index():
    data = []
    query = Notebook.query.filter_by(user_id=current_user.id)

    for item in query:
        notebook_json = item.processed_data
        doc = button_class(item.name, notebook_json['functions'], notebook_json['classes'], notebook_json['loops'], item.link)  
        data.append(doc)  
    if data == []:
        data = ['no notebooks']
    return render_template('frontpage.html', data = data)

@app.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow.redirect_uri = flask.url_for('callback', _external=True)
    auth_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type='offline',
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes='true')
    # google = get_google_auth()
    # auth_url, state = google.authorization_url(
    #     Auth.AUTH_URI, access_type='offline')
    session['state'] = state
    return render_template('login.html', auth_url=auth_url)

@app.route('/authorize')
def authorize():
    # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
    # flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
    #     CLIENT_SECRETS_FILE, scopes=SCOPES)
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=['profile', 'email'] )
    # The URI created here must exactly match one of the authorized redirect URIs
    # for the OAuth 2.0 client, which you configured in the API Console. If this
    # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
    # error.
    flow.redirect_uri = flask.url_for('callback', _external=True)
    authorization_url, state = flow.authorization_url(
        # Enable offline access so that you can refresh an access token without
        # re-prompting the user for permission. Recommended for web server apps.
        access_type='offline',
        # Enable incremental authorization. Recommended as a best practice.
        include_granted_scopes='true')
    print(f'state {state}')
    # Store the state so the callback can verify the auth server response.
    flask.session['state'] = state
    return flask.redirect(authorization_url)

@app.route('/callback')
def callback():
    if current_user is not None and current_user.is_authenticated:
        return redirect(url_for('index'))
    if 'error' in request.args:
        if request.args.get('error') == 'access_denied':
            return 'You denied access.'
        return 'Error encountered.'
    if 'code' not in request.args and 'state' not in request.args:
        return redirect(url_for('login'))
    else:
        # Specify the state when creating the flow in the callback so that it can
        # verified in the authorization server response.
        state = flask.session['state']

        flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, scopes=None, state=state)
        flow.redirect_uri = flask.url_for('callback', _external=True)

        # Use the authorization server's response to fetch the OAuth 2.0 tokens.
        authorization_response = flask.request.url
        flow.fetch_token(authorization_response=authorization_response)
        sess = flow.authorized_session()
        # here i take credentials 
        credentials = flow.credentials
        # add them to json
        flask.session['credentials'] = credentials_to_dict(credentials)
        # now take user information 
        resp = sess.get('https://www.googleapis.com/userinfo/v2/me')
        # if we fail to identify our user, we create a new one
        if resp.status_code == 200:
            # transform user data to json and 
            user_data = resp.json()
            # now we try to find user by email  
            email = user_data['email']
            user = User.query.filter_by(email=email).first()
            if user is None:
                # print('creating new user')
                user = User()
                user.email = user_data['email']
            user.name = user_data['name']
            user.credentials = json.dumps(flask.session['credentials'])
            user.avatar = user_data['picture']
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('index'))
        return 'Could not fetch your information.'

def credentials_to_dict(credentials):
    return {'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
            }

@app.route('/revoke')
def revoke():
    if 'credentials' not in flask.session:
        return ('You need to <a href="/authorize">authorize</a> before ' +
                'testing the code to revoke credentials.')

    credentials = google.oauth2.credentials.Credentials(
        **flask.session['credentials'])

    revoke = requests.post('https://oauth2.googleapis.com/revoke',
                           params={'token': credentials.token},
                           headers={'content-type': 'application/x-www-form-urlencoded'})

    status_code = getattr(revoke, 'status_code')
    if status_code == 200:
        return('Credentials successfully revoked.' + print_index_table())
    else:
        return('An error occurred.' + print_index_table())

@app.route('/clear')
def clear_credentials():
    if 'credentials' in flask.session:
        del flask.session['credentials']
    return ('Credentials have been cleared.<br><br>' +
            print_index_table())

@app.route('/parsing', methods=('GET', 'POST'))
def parsing():
    if current_user is not None and current_user.is_authenticated:
        update = request.args.get('update')
        if 'credentials' not in flask.session:
            return flask.redirect('authorize')

        # Load credentials from the session.
        credentials = google.oauth2.credentials.Credentials(
            **flask.session['credentials'])

        # revoke = requests.post('https://oauth2.googleapis.com/revoke',
        #                        params={'token': credentials.token},
        #                        headers={'content-type': 'application/x-www-form-urlencoded'})
        # status_code = getattr(revoke, 'status_code')
        # if status_code == 200:
        #     return('Credentials successfully revoked.' + print_index_table())
        # else:
        #     return('An error occurred.' + print_index_table())

        drive = googleapiclient.discovery.build(
            API_SERVICE_NAME, API_VERSION, credentials=credentials)

        # results = drive.files().list(q="mimeType='application/x-ipynb+json'",\
        #      fields="nextPageToken, files(id, name, createdTime, mimeType)").execute()
        results = drive.files().list(q="mimeType='application/vnd.google.colaboratory' or mimeType='application/x-ipynb+json'",\
             fields="nextPageToken, files(id, name, modifiedTime, webViewLink, mimeType)").execute()
        # results = drive.files().list(fields="nextPageToken, files(id, name, createdTime, mimeType)").execute()

        items = results.get('files', [])    

        refresh = []
        in_database = []
        new = []

        for item in items: # loop over list of all notebooks in google drive 
            query = Notebook.query.filter_by(user_id=current_user.id, colab_id=item['id']).first() # search for this notebook in 'notebooks' table 
            if query is not None: # if we have this exact notebook id in our database
                if query.creation_time == item['modifiedTime']: # here is the condition when we don't do any changes in databases 
                    in_database.append(item) # just add it to database
                    # print(f'{item["name"]} in database')
                else: # else we have to modifiy our index and change functions, classes and loops, and modification time 
                    if update == 'False': # if we don't wanna to update
                        refresh.append(item) # just store it to refresh list 
                        # print(f'{item["name"]} in database and need to be refreshed')
                    else: # if we want actually update our database
                        file = (item['id'], item['name']) # download data from google drive  
                        data = gdrive_download_file(drive, file)
                        query.raw_data =  data
                        query.processed_data = parse_ipynb(data)
                        db.session.commit() # here we change information about notebook
                        # now let's modifie the index 
                        files_data = {}
                        files_data[item['id']] = (query.processed_data['text'], item['name'])  # here is our new text 
                        index = Index.query.filter_by(user_id=current_user.id).first() # now we take the index
                        index.inverted_index, index.doc_lengths, index.doc_index = update_inverted_index(
                                                                                                        files_data, \
                                                                                                        index.doc_lengths, \
                                                                                                        index.inverted_index, \
                                                                                                        index.doc_index)
                        db.session.commit() 
                        query.creation_time = item['modifiedTime'] # change creation_time 
                        db.session.commit() # if something goes wrong next time we will update this notebook again 
                        in_database.append(item)
                        # print(f'{item["name"]} refreshed')
            else:  # we see this notebook for first time
                if update == 'False':
                    new.append(item)
                    # print(f'{item["name"]} not in database')
                else: 
                    file = (item['id'], item['name'])
                    data = gdrive_download_file(drive, file)
                    notebook = Notebook() # create new database instance
                    notebook.name = item['name']
                    notebook.raw_data = data
                    notebook.processed_data = parse_ipynb(data)
                    notebook.creation_time = item['modifiedTime']
                    notebook.user_id = current_user.id
                    notebook.link = item['webViewLink']
                    notebook.colab_id = item['id']
                    files_data = {}
                    files_data[item['id']] = (notebook.processed_data['text'], item['name'])  # here is our new text 
                    index = Index.query.filter_by(user_id=current_user.id).first()
                    if index is not None:
                        # print(f'inputs for {item["name"]} len {index.doc_lengths} ind {index.doc_index}')
                        inverted_index, doc_lengths, doc_index = update_inverted_index(
                                                                                                        files_data, \
                                                                                                        index.doc_lengths, \
                                                                                                        index.inverted_index, \
                                                                                                        index.doc_index)
                        index.inverted_index = inverted_index
                        db.session.commit()
                        index.doc_lengths = doc_lengths
                        db.session.commit()
                        index.doc_index = doc_index
                        db.session.commit()
                        # print(f'for {item["name"]} len {index.doc_lengths} ind {index.doc_index}')
                        # db.session.add(index)
                        # index = db.session.merge(index)
                        # print(f'index for {item["name"]} was created')
                        # in_database.append(item)
                    else: 
                        # print('im here')
                        doc_lengths = {}
                        inverted_index = {}
                        doc_index = {}
                        index = Index()
                        index.user_id = current_user.id
                        index.inverted_index, index.doc_lengths, index.doc_index = update_inverted_index(
                                                                                                        files_data, \
                                                                                                        doc_lengths, \
                                                                                                        inverted_index, \
                                                                                                        doc_index)
                        # print(f'for {item["name"]} len {index.doc_lengths} ind {index.doc_index}')
                        db.session.add(index)                                                                              
                        db.session.commit()
                    db.session.add(notebook)
                    db.session.commit() # I have a weak point here 
                    in_database.append(item)
                    # print(f'{item["name"]} added to database')
        # index = Index.query.filter_by(user_id=current_user.id).first()
        # if index != None:
        #     print(f'######### {index.inverted_index}')
        #     print(f'len######### {index.doc_lengths}')
        #     print(f'index######### {index.doc_index}')
        flask.session['credentials'] = credentials_to_dict(credentials)
        return render_template('second_page.html', new = new, refresh = refresh, in_database = in_database)
    else:
        return redirect(url_for('index'))

def gdrive_download_file(drive_service, file): 
    # downloads file and saves it under the path
    request = drive_service.files().get_media(fileId=file[0])
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    data = json.load(fh)
    return data
    
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/search', methods=('GET', 'POST'))
def search():
    query = request.args.get('q')
    if query == '':
        data = []
        table = Notebook.query.filter_by(user_id=current_user.id)
        for item in table:
            notebook_json = item.processed_data
            doc = button_class(item.name, notebook_json['functions'], notebook_json['classes'], notebook_json['loops'], item.link)  
            data.append(doc)

        return render_template('frontpage.html', data = data)

    else: 
        table = Index.query.filter_by(user_id=current_user.id).first()
        if table is None:
            data = ['no notebooks']
            return render_template('frontpage.html', data = data)
        else:
            translator = Translator()
            translation = translator.translate(query, src = 'ru', dest = 'en')
            query = translation.text.lower()

            related_documents = find(
                            query,\
                            table.inverted_index,\
                            table.doc_lengths,\
                            table.doc_index
                            )

            data = []
            table = Notebook.query.filter_by(user_id=current_user.id)
            for item in table:
                if item.name in related_documents:
                    notebook_json = item.processed_data
                    doc = button_class(item.name, notebook_json['functions'], notebook_json['classes'], notebook_json['loops'], item.link)  
                    data.append(doc)

            return render_template('frontpage.html', data = data)

