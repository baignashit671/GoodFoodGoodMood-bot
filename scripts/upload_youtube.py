"""Upload the release's MP4 to YouTube with metadata.json. Used by .github/workflows/publish-foodscience.yml.
  python scripts/upload_youtube.py <dir with *.mp4 and metadata.json>
Env: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (or GOOGLE_CREDENTIALS json), EXPECTED_CHANNEL_ID (optional guard).
metadata.json may set "language" (default "en"; "hi" for Hindi).
Writes url=<watch link> to $GITHUB_OUTPUT.
"""
import glob, json, os, sys, time
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

d = sys.argv[1]
meta = json.load(open(os.path.join(d, 'metadata.json')))
video = glob.glob(os.path.join(d, '*.mp4'))[0]

# credentials: YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN, or one GOOGLE_CREDENTIALS JSON (as printed by reauth_youtube.py)
if os.environ.get('GOOGLE_CREDENTIALS', '').strip():
    g = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    os.environ.setdefault('YT_CLIENT_ID', g['client_id']); os.environ.setdefault('YT_CLIENT_SECRET', g['client_secret']); os.environ.setdefault('YT_REFRESH_TOKEN', g['refresh_token'])
creds = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'], token_uri='https://oauth2.googleapis.com/token',
                    client_id=os.environ['YT_CLIENT_ID'], client_secret=os.environ['YT_CLIENT_SECRET'])
yt = build('youtube', 'v3', credentials=creds, cache_discovery=False)

# Guard: make sure the token belongs to the right channel (needs a youtube/readonly scope; skipped if not granted).
want = os.environ.get('EXPECTED_CHANNEL_ID')
if want:
    try:
        mine = yt.channels().list(part='id,snippet', mine=True).execute().get('items', [])
        ids = [c['id'] for c in mine]
        print('token channel(s):', [(c['id'], c['snippet']['title']) for c in mine])
        if ids and want not in ids:
            sys.exit(f'Refusing to upload: token is for {ids}, expected {want}')
    except HttpError as e:
        print('channel check skipped (scope):', e.resp.status)

title = meta['title'][:100]
body = {
    'snippet': {'title': title, 'description': meta.get('description', ''), 'tags': meta.get('tags', [])[:15],
                'categoryId': str(meta.get('category_id', '27')), 'defaultLanguage': meta.get('language', 'en'), 'defaultAudioLanguage': meta.get('language', 'en')},
    'status': {'privacyStatus': meta.get('privacy', 'public'), 'selfDeclaredMadeForKids': False, 'embeddable': True,
               'license': 'youtube'},
}
req = yt.videos().insert(part='snippet,status', body=body, notifySubscribers=True,
                         media_body=MediaFileUpload(video, mimetype='video/mp4', chunksize=8 * 1024 * 1024, resumable=True))
resp, tries = None, 0
while resp is None:
    try:
        status, resp = req.next_chunk()
        if status: print(f'uploaded {int(status.progress() * 100)}%')
    except HttpError as e:
        if e.resp.status in (500, 502, 503, 504) and tries < 5:
            tries += 1; time.sleep(2 ** tries); continue
        raise
url = f"https://www.youtube.com/watch?v={resp['id']}"
print('published', url)
with open(os.environ.get('GITHUB_OUTPUT', '/dev/null'), 'a') as f:
    f.write(f'url={url}\n')
