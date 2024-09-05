import os
import requests
from flask import Flask, redirect, request, jsonify, render_template
from dotenv import load_dotenv, set_key
from base64 import b64encode
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler

load_dotenv()

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///spotify_tracks.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Define Track model
class Track(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    artist = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    duration_ms = db.Column(db.Integer, nullable=False)

# Create the database
with app.app_context():
    db.create_all()

# Spotify credentials and setup
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI')

# Get tokens from .env file
access_token = os.getenv('SPOTIFY_ACCESS_TOKEN')
refresh_token = os.getenv('SPOTIFY_REFRESH_TOKEN')
token_expires_at = datetime.fromisoformat(os.getenv('SPOTIFY_TOKEN_EXPIRES_AT', datetime.utcnow().isoformat()))

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

def fetch_and_store_current_track():
    # Fetch current track info from Spotify API
    response = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers={
        'Authorization': f'Bearer {access_token}'
    })
    track_info = response.json()

    if not track_info.get('is_playing'):
        return

    # Extract track details
    track_name = track_info['item']['name']
    artist_name = ', '.join(artist['name'] for artist in track_info['item']['artists'])
    duration_ms = track_info['item']['duration_ms']
    progress_ms = track_info['progress_ms']

    with app.app_context():
        # Check if the track is the same as the last one stored
        last_track = Track.query.order_by(Track.timestamp.desc()).first()
        
        if last_track:
            last_track_name = last_track.name
            last_artist_name = last_track.artist
            last_track_timestamp = last_track.timestamp

            # Calculate end time of the last track
            last_track_end_time = last_track_timestamp + timedelta(milliseconds=last_track.duration_ms)

            # If the track is the same as the last one stored
            if track_name == last_track_name and artist_name == last_artist_name:
                # Check if the current time is greater than the end time of the last track
                if datetime.utcnow() < last_track_end_time:
                    return

        # Store the new track
        track = Track(name=track_name, artist=artist_name, duration_ms=duration_ms)
        db.session.add(track)
        db.session.commit()


# Schedule the background task
scheduler.add_job(fetch_and_store_current_track, 'interval', seconds=1)

# Step 1: Redirect to Spotify authorization URL
@app.route('/login')
def login():
    scope = 'user-read-currently-playing'
    auth_url = 'https://accounts.spotify.com/authorize'
    response_type = 'code'
    auth_query_parameters = {
        'client_id': SPOTIFY_CLIENT_ID,
        'response_type': response_type,
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'scope': scope
    }
    url_args = '&'.join([f"{key}={value}" for key, value in auth_query_parameters.items()])
    return redirect(f"{auth_url}?{url_args}")

# Step 2: Handle Spotify callback and get tokens
@app.route('/callback')
def callback():
    global access_token, refresh_token, token_expires_at
    code = request.args.get('code')
    token_url = 'https://accounts.spotify.com/api/token'
    headers = {
        'Authorization': 'Basic ' + b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode(),
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': SPOTIFY_REDIRECT_URI
    }
    response = requests.post(token_url, headers=headers, data=data)
    if response.status_code != 200:
        return "Error getting Spotify token", 400

    tokens = response.json()
    access_token = tokens.get('access_token')
    refresh_token = tokens.get('refresh_token')
    expires_in = tokens.get('expires_in')
    token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Save tokens to .env file
    set_key('.env', 'SPOTIFY_ACCESS_TOKEN', access_token)
    set_key('.env', 'SPOTIFY_REFRESH_TOKEN', refresh_token)
    set_key('.env', 'SPOTIFY_TOKEN_EXPIRES_AT', token_expires_at.isoformat())

    return redirect('/')

# Step 3: Refresh the access token if needed
def refresh_access_token(force=False):
    global access_token, refresh_token, token_expires_at
    if force or datetime.utcnow() >= token_expires_at:
        token_url = 'https://accounts.spotify.com/api/token'
        headers = {
            'Authorization': 'Basic ' + b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode(),
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }
        response = requests.post(token_url, headers=headers, data=data)
        if response.status_code == 200:
            tokens = response.json()
            access_token = tokens.get('access_token')
            expires_in = tokens.get('expires_in')
            token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # Update tokens in .env file
            set_key('.env', 'SPOTIFY_ACCESS_TOKEN', access_token)
            set_key('.env', 'SPOTIFY_TOKEN_EXPIRES_AT', token_expires_at.isoformat())
            print("Refreshed token")
        else:
            print("Failed to refresh token")
            print(response)

# Step 4: Fetch currently playing track
@app.route('/currently-playing')
def currently_playing():
    global access_token
    if not access_token:
        return "Not authenticated", 401

    refresh_access_token()  # Refresh token if needed

    headers = {'Authorization': f"Bearer {access_token}"}
    response = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers=headers)
    if response.status_code == 200 and response.content:
        return jsonify(response.json())
    elif response.status_code == 204:
        return jsonify({"message": "No track is currently playing."})
    else:
        return "Error fetching currently playing track", 400

# Route to fetch all stored tracks
@app.route('/tracks')
def tracks():
    all_tracks = Track.query.all()
    return jsonify([{
        'name': track.name,
        'artist': track.artist,
        'timestamp': track.timestamp
    } for track in all_tracks])

default_limit=10

@app.route('/', methods=['GET', 'POST'])
def home():
    refresh_access_token()
    # Default values
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', default_limit, type=int)

    # Fetch current track info from Spotify API
    response = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers={
        'Authorization': f'Bearer {access_token}'
    })
    current_track_info = response.json()

    # Extract current track details
    current_track = None
    if current_track_info.get('is_playing'):
        current_track = {
            'name': current_track_info['item']['name'],
            'artist': ', '.join(artist['name'] for artist in current_track_info['item']['artists']),
            'album_cover': current_track_info['item']['album']['images'][0]['url']  # Assuming first image is the album cover
        }

    # Fetch all stored tracks with pagination
    all_tracks = Track.query.order_by(Track.timestamp.desc()).paginate(page=page, per_page=limit, error_out=False)

    # Create track list with timestamps formatted
    tracks = [{
        'name': track.name,
        'artist': track.artist,
        'timestamp': track.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for track in all_tracks.items]

    return render_template('index.html', tracks=tracks, page=page, total_pages=all_tracks.pages, current_track=current_track, limit=limit, default_limit=default_limit)

@app.route('/current-track')
def current_track():
    refresh_access_token()
    # Fetch current track info from Spotify API
    response = requests.get('https://api.spotify.com/v1/me/player/currently-playing', headers={
        'Authorization': f'Bearer {access_token}'
    })
    track_info = response.json()

    current_track = None
    if track_info.get('is_playing'):
        current_track = {
            'name': track_info['item']['name'],
            'artist': ', '.join(artist['name'] for artist in track_info['item']['artists']),
            'album_cover': track_info['item']['album']['images'][0]['url']  # Assuming first image is the album cover
        }

    return jsonify({'current_track': current_track})

@app.route('/track-list')
def track_list():
    # Fetch all stored tracks with pagination
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', default_limit, type=int)
    all_tracks = Track.query.order_by(Track.timestamp.desc()).paginate(page=page, per_page=limit, error_out=False)

    # Create track list with timestamps formatted
    tracks = [{
        'name': track.name,
        'artist': track.artist,
        'timestamp': track.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for track in all_tracks.items]

    return jsonify({'tracks': tracks, 'total_pages': all_tracks.pages})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False)

