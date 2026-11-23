"""Snapshot the channel's public numbers so each daily Claude run can learn what works.
  python scripts/channel_stats.py   (run from the folder holding _published.md + results/, e.g. foodscience/;
  env GOOGLE_CREDENTIALS json or env YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN)
Writes stats/latest.json: channel subscribers/views + every published Short (from results/*.json) with
views, likes, comments, hours since upload, views per hour, and the style/topic from _published.md.
"""
import datetime, glob, json, os, re
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

if os.environ.get('GOOGLE_CREDENTIALS', '').strip():
    g = json.loads(os.environ['GOOGLE_CREDENTIALS'])
    os.environ.setdefault('YT_CLIENT_ID', g['client_id']); os.environ.setdefault('YT_CLIENT_SECRET', g['client_secret']); os.environ.setdefault('YT_REFRESH_TOKEN', g['refresh_token'])
creds = Credentials(None, refresh_token=os.environ['YT_REFRESH_TOKEN'], token_uri='https://oauth2.googleapis.com/token',
                    client_id=os.environ['YT_CLIENT_ID'], client_secret=os.environ['YT_CLIENT_SECRET'])
yt = build('youtube', 'v3', credentials=creds, cache_discovery=False)

log = {}
for line in (open('_published.md', encoding='utf-8') if os.path.exists('_published.md') else []):
    m = re.match(r'- (\S+) \| (.*?) \| (.*?) \| (.*?) \| (\S+)', line.strip())
    if m: log[m.group(5).split('v=')[-1]] = {'date': m.group(1), 'topic': m.group(2), 'style': m.group(3)}

ids = []
for f in sorted(glob.glob('results/*.json')):
    r = json.load(open(f)); vid = r.get('url', '').split('v=')[-1]
    if vid and r.get('privacy', 'public') == 'public' and vid not in ids: ids.append(vid)
for vid in log:
    if vid not in ids: ids.append(vid)
# ALL_UPLOADS=1: also include the channel's latest uploads that this repo didn't publish (e.g. another bot's Shorts),
# so the runs can compare their own Shorts with everything else on the channel.
if os.environ.get('ALL_UPLOADS') == '1':
    up = yt.channels().list(part='contentDetails', mine=True).execute()['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    for it in yt.playlistItems().list(part='contentDetails', playlistId=up, maxResults=30).execute().get('items', []):
        vid = it['contentDetails']['videoId']
        if vid not in ids: ids.append(vid); log.setdefault(vid, {'source': 'other'})

now = datetime.datetime.now(datetime.timezone.utc); videos = []
for i in range(0, len(ids), 50):
    for it in yt.videos().list(part='snippet,statistics,contentDetails', id=','.join(ids[i:i + 50])).execute().get('items', []):
        s, sn = it['statistics'], it['snippet']
        pub = datetime.datetime.fromisoformat(sn['publishedAt'].replace('Z', '+00:00')); hrs = max(1, (now - pub).total_seconds() / 3600)
        v = int(s.get('viewCount', 0))
        videos.append({'id': it['id'], 'url': f"https://www.youtube.com/watch?v={it['id']}", 'title': sn['title'], 'published': sn['publishedAt'],
                       'duration': it['contentDetails']['duration'], 'category_id': sn.get('categoryId'),
                       'views': v, 'likes': int(s.get('likeCount', 0)), 'comments': int(s.get('commentCount', 0)),
                       'hours_live': round(hrs, 1), 'views_per_hour': round(v / hrs, 1), **log.get(it['id'], {})})
videos.sort(key=lambda x: x['published'], reverse=True)
ch = yt.channels().list(part='statistics', mine=True).execute()['items'][0]['statistics']
out = {'updated': now.strftime('%Y-%m-%dT%H:%MZ'), 'channel': {k: int(v) for k, v in ch.items() if str(v).isdigit()}, 'videos': videos}
os.makedirs('stats', exist_ok=True); json.dump(out, open('stats/latest.json', 'w'), indent=1)
print(json.dumps(out['channel']), len(videos), 'videos')
