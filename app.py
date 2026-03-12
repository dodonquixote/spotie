from flask import Flask, render_template, request, jsonify, redirect
import requests
import base64
import os
import secrets
import time
import urllib.parse

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__)

# Spotify API credentials
SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'http://localhost:8000/callback')
SPOTIFY_SCOPES = 'user-read-currently-playing user-read-playback-state'

# n8n webhook URL for adding to queue
N8N_WEBHOOK_URL = '#ADD YOUR N8N WEBHOOK URL HERE'

# Cache for Spotify Client Credentials token (for search)
_token_cache = {
    'token': None,
    'expires_at': 0
}

# User token — loaded from .env at startup
_user_token = {
    'access_token': None,
    'refresh_token': os.environ.get('SPOTIFY_REFRESH_TOKEN', '') or None,
    'expires_at': 0
}
_oauth_state = None


def get_spotify_token():
    """Get Spotify access token using Client Credentials flow."""
    # Check if we have a valid cached token
    if _token_cache['token'] and time.time() < _token_cache['expires_at']:
        return _token_cache['token']
    
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    
    # Encode credentials
    credentials = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    # Request token
    token_url = 'https://accounts.spotify.com/api/token'
    headers = {
        'Authorization': f'Basic {encoded_credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {'grant_type': 'client_credentials'}
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        token_data = response.json()
        
        # Cache the token
        _token_cache['token'] = token_data['access_token']
        _token_cache['expires_at'] = time.time() + token_data['expires_in'] - 60  # Refresh 1 min early
        
        return _token_cache['token']
    except Exception as e:
        print(f"Error getting Spotify token: {e}")
        return None


def search_spotify(query, limit=10):
    """Search for tracks on Spotify."""
    token = get_spotify_token()
    if not token:
        return {'error': 'Spotify credentials not configured'}
    
    search_url = 'https://api.spotify.com/v1/search'
    headers = {
        'Authorization': f'Bearer {token}'
    }
    params = {
        'q': query,
        'type': 'track',
        'limit': limit,
        'market': 'ID'  # Indonesia market
    }
    
    try:
        response = requests.get(search_url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        tracks = []
        for item in data.get('tracks', {}).get('items', []):
            # Get album image (smallest available)
            images = item.get('album', {}).get('images', [])
            image_url = images[-1]['url'] if images else None
            
            # Format duration
            duration_ms = item.get('duration_ms', 0)
            minutes = duration_ms // 60000
            seconds = (duration_ms % 60000) // 1000
            duration = f"{minutes}:{seconds:02d}"
            
            tracks.append({
                'id': item['id'],
                'title': item['name'],
                'artist': ', '.join([a['name'] for a in item.get('artists', [])]),
                'album': item.get('album', {}).get('name', ''),
                'duration': duration,
                'image_url': image_url,
                'spotify_url': item.get('external_urls', {}).get('spotify', ''),
                'uri': item.get('uri', '')
            })
        
        return {'tracks': tracks}
    except Exception as e:
        print(f"Error searching Spotify: {e}")
        return {'error': str(e)}


def add_to_queue_n8n(spotify_link):
    """Send track link to n8n webhook to add to queue."""
    try:
        print(f"Sending to n8n: {spotify_link}")
        # Using GET request with query parameter
        response = requests.get(
            N8N_WEBHOOK_URL,
            params={'spotify_link': spotify_link},
            timeout=10
        )
        print(f"n8n response: {response.status_code} - {response.text}")
        response.raise_for_status()
        return {'success': True, 'message': 'Track added to queue'}
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'Request timeout'}
    except requests.exceptions.RequestException as e:
        print(f"Error adding to queue: {e}")
        return {'success': False, 'error': str(e)}


def get_user_token():
    """Get valid user OAuth access token, refreshing if needed."""
    if not _user_token['refresh_token']:
        return None
    if not _user_token['access_token'] or time.time() >= _user_token['expires_at']:
        return _refresh_user_token()
    return _user_token['access_token']


def _refresh_user_token():
    """Refresh the user OAuth access token."""
    if not _user_token['refresh_token']:
        return None
    credentials = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    try:
        response = requests.post(
            'https://accounts.spotify.com/api/token',
            headers={
                'Authorization': f'Basic {encoded_credentials}',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            data={
                'grant_type': 'refresh_token',
                'refresh_token': _user_token['refresh_token']
            }
        )
        response.raise_for_status()
        token_data = response.json()
        _user_token['access_token'] = token_data['access_token']
        _user_token['expires_at'] = time.time() + token_data['expires_in'] - 60
        if 'refresh_token' in token_data:
            _user_token['refresh_token'] = token_data['refresh_token']
        print('User access token refreshed.')
        return _user_token['access_token']
    except Exception as e:
        print(f"Error refreshing user token: {e}")
        return None


# Auto-bootstrap: if refresh token is in env, get an access token immediately
def _bootstrap_user_token():
    if _user_token['refresh_token']:
        print('Refresh token found, bootstrapping user access token...')
        _refresh_user_token()

_bootstrap_user_token()


@app.route('/')
def index():
    """Render the main page."""
    return render_template('music-queue-manager.html')


@app.route('/setup')
def setup():
    """One-time setup: authorize Spotify and get a refresh token."""
    global _oauth_state
    _oauth_state = secrets.token_hex(16)
    params = {
        'client_id': SPOTIFY_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': SPOTIFY_REDIRECT_URI,
        'state': _oauth_state,
        'scope': SPOTIFY_SCOPES,
        'show_dialog': 'true'
    }
    auth_url = 'https://accounts.spotify.com/authorize?' + urllib.parse.urlencode(params)
    return redirect(auth_url)


@app.route('/callback')
def callback():
    """Handle Spotify OAuth callback and save refresh token to .env."""
    global _oauth_state
    error = request.args.get('error')
    if error:
        return f'<p>Error: {error}</p>', 400

    code = request.args.get('code')
    state = request.args.get('state')

    if not state or state != _oauth_state:
        return '<p>Error: state mismatch</p>', 400

    credentials = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    try:
        response = requests.post(
            'https://accounts.spotify.com/api/token',
            headers={
                'Authorization': f'Basic {encoded_credentials}',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': SPOTIFY_REDIRECT_URI
            }
        )
        response.raise_for_status()
        token_data = response.json()
        _user_token['access_token'] = token_data['access_token']
        _user_token['refresh_token'] = token_data.get('refresh_token')
        _user_token['expires_at'] = time.time() + token_data['expires_in'] - 60

        # Save refresh token to .env file
        refresh_token = token_data.get('refresh_token', '')
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        _save_refresh_token_to_env(env_path, refresh_token)

        return f'''
        <html><body style="font-family:sans-serif;padding:40px;background:#0a0a0f;color:#f0f0f5">
        <h2 style="color:#1db954">Setup berhasil!</h2>
        <p>Refresh token disimpan ke <code>.env</code>.</p>
        <p>Refresh token: <code style="word-break:break-all">{refresh_token}</code></p>
        <p><a href="/" style="color:#1db954">Kembali ke app</a></p>
        </body></html>
        '''
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return f'<p>Error: {e}</p>', 500


def _save_refresh_token_to_env(env_path, refresh_token):
    """Write or update SPOTIFY_REFRESH_TOKEN in the .env file."""
    try:
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                lines = f.readlines()
            found = False
            new_lines = []
            for line in lines:
                if line.startswith('SPOTIFY_REFRESH_TOKEN='):
                    new_lines.append(f'SPOTIFY_REFRESH_TOKEN={refresh_token}\n')
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f'SPOTIFY_REFRESH_TOKEN={refresh_token}\n')
            with open(env_path, 'w') as f:
                f.writelines(new_lines)
        else:
            with open(env_path, 'w') as f:
                f.write(f'SPOTIFY_REFRESH_TOKEN={refresh_token}\n')
        print(f'Refresh token saved to {env_path}')
    except Exception as e:
        print(f'Could not save refresh token to .env: {e}')


@app.route('/api/auth-status')
def api_auth_status():
    """Check if user token is available."""
    token = get_user_token()
    return jsonify({'authenticated': token is not None})


@app.route('/api/now-playing')
def api_now_playing():
    """Get currently playing track."""
    token = get_user_token()
    if not token:
        return jsonify({'error': 'Not authenticated', 'login_url': '/login'}), 401
    try:
        response = requests.get(
            'https://api.spotify.com/v1/me/player/currently-playing',
            headers={'Authorization': f'Bearer {token}'},
            params={'market': 'ID'},
            timeout=5
        )
        if response.status_code == 204:
            return jsonify({'is_playing': False, 'item': None})
        response.raise_for_status()
        data = response.json()
        item = data.get('item', {})
        images = item.get('album', {}).get('images', [])
        image_url = images[0]['url'] if images else None
        duration_ms = item.get('duration_ms', 0)
        progress_ms = data.get('progress_ms', 0)
        minutes_d = duration_ms // 60000
        seconds_d = (duration_ms % 60000) // 1000
        minutes_p = progress_ms // 60000
        seconds_p = (progress_ms % 60000) // 1000
        return jsonify({
            'is_playing': data.get('is_playing', False),
            'progress_ms': progress_ms,
            'duration_ms': duration_ms,
            'progress_str': f"{minutes_p}:{seconds_p:02d}",
            'duration_str': f"{minutes_d}:{seconds_d:02d}",
            'title': item.get('name', ''),
            'artist': ', '.join([a['name'] for a in item.get('artists', [])]),
            'album': item.get('album', {}).get('name', ''),
            'image_url': image_url,
            'spotify_url': item.get('external_urls', {}).get('spotify', '')
        })
    except Exception as e:
        print(f"Error getting now playing: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/search')
def api_search():
    """Search for tracks on Spotify."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'tracks': []})
    
    limit = min(int(request.args.get('limit', 10)), 20)
    result = search_spotify(query, limit)
    return jsonify(result)


@app.route('/api/queue', methods=['POST'])
def api_add_to_queue():
    """Add a track to the queue via n8n webhook."""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data provided'}), 400
    
    spotify_link = data.get('spotify_link')
    if not spotify_link:
        return jsonify({'success': False, 'error': 'No spotify_link provided'}), 400
    
    result = add_to_queue_n8n(spotify_link)
    status_code = 200 if result.get('success') else 500
    return jsonify(result), status_code


@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    has_credentials = bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET)
    return jsonify({
        'status': 'ok',
        'spotify_configured': has_credentials
    })


if __name__ == '__main__':
    # Check if credentials are set
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("\n⚠️  WARNING: Spotify credentials not set!")
        print("Set environment variables:")
        print("  - SPOTIFY_CLIENT_ID")
        print("  - SPOTIFY_CLIENT_SECRET")
        print("\nYou can get these from https://developer.spotify.com/dashboard\n")
    
    app.run(debug=True, port=8000)
