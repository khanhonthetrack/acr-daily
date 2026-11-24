#!/usr/bin/env python3
"""Seeds a new ACR Daily server with all stage routes and stageIds from an existing public server (default: https://acrdaily.com)."""
import json
import os
import sys
import urllib.parse
import urllib.request

SOURCE = (os.environ.get('ACR_DAILY_SOURCE') or 'https://acrdaily.com').rstrip('/')
TARGET = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get('ACR_DAILY_SERVER') or '').rstrip('/')
ADMIN_KEY = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('ACR_DAILY_ADMIN_KEY') or ''

if not TARGET or not ADMIN_KEY:
    sys.exit('Usage: python3 tools/seed_from_public.py <TARGET_SERVER_URL> <ADMIN_KEY>')


def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'ACR-Daily-admin/1.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def post_admin(path, body):
    req = urllib.request.Request(
        TARGET + path,
        data=json.dumps(body).encode('utf-8'),
        method='POST',
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + ADMIN_KEY,
            'User-Agent': 'ACR-Daily-admin/1.0',
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    routes = get_json(SOURCE + '/api/routes')
    print(f'Fetched {len(routes)} stage metadata entries from {SOURCE}/api/routes')
    seeded = 0
    for item in routes:
        track = item['track']
        q = urllib.parse.quote(track)
        detail = get_json(f'{SOURCE}/api/route?track={q}')
        pts = detail.get('route') or []
        if len(pts) < 20:
            print(f'  skip {track}: too few points ({len(pts)})')
            continue
        payload = {
            'track': track,
            'points': pts,
        }
        if item.get('estimated'):
            payload['source'] = 'game-files'
        res = post_admin('/api/admin/route', payload)
        if item.get('stageId'):
            post_admin('/api/admin/stage-id', {'track': track, 'stageId': item['stageId']})
        post_admin('/api/admin/pool', {'track': track, 'car': '*', 'enabled': True})
        seeded += 1
        print(f'  [{seeded}/{len(routes)}] {track:<38} {res.get("length", 0):>6} m  stageId={item.get("stageId") or "-"}')

    ahead = post_admin('/api/admin/schedule-ahead', {'repick': True})
    print(f'Done! Seeded {seeded} stages and scheduled {len(ahead.get("fixed") or [])} upcoming days.')


if __name__ == '__main__':
    main()
