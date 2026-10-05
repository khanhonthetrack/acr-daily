import json, os, sys, urllib.request
base = os.environ.get('ACR_DAILY_SERVER', 'https://acr-daily.acr-daily-server.workers.dev').rstrip('/')
key = os.environ['ACR_DAILY_ADMIN_KEY']
existing = {r['track'] for r in json.load(urllib.request.urlopen(urllib.request.Request(base + '/api/routes', headers={'User-Agent': 'ACR-Daily-admin'})))}
def post(path, body):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method='POST',
                                 headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'ACR-Daily-admin'})
    return json.load(urllib.request.urlopen(req, timeout=60))
routes = json.load(open('game_routes.json', encoding='utf-8'))
done = []
for r in routes:
    track = r['track']
    if r['env'] == 'AlsaceS2Munster' and r['key'] == 'SHORT1_REVERSE':
        track = 'Alsace Forêt de Munster'      # "Alsace Forêt" is Saverne's Full Forward; the start line tells them apart
    if track in existing:
        print('keep driven route:', track); continue
    body = {'track': track, 'points': r['points'], 'source': 'game-files'}
    if r['stageIdConfirmed']:
        body['stageId'] = r['stageId']
    a = post('/api/admin/route', body)
    b = post('/api/admin/pool', {'track': track, 'car': '*'})
    done.append((track, a.get('length'), a.get('checkpoints'), body.get('stageId', '-')))
for d in done: print('added %-36s %6s m  %3s checkpoints  id %s' % d)
print(len(done), 'stages added')

