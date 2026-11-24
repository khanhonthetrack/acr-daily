#!/usr/bin/env python3
"""In-cluster GitOps rollout watcher for ACR Daily GKE clusters (standard library only, Python 3.9+).

Polls GitHub Container Registry (`ghcr.io/<owner>/acr-daily-server:<tag>`, built automatically on GitHub push by
`.github/workflows/deploy-gke.yml`) for new immutable image digests (`sha256:...`). Whenever a newly built image
appears, patches `Deployment/acr-relay` and `StatefulSet/acr-daily` (or `Deployment/acr-daily` on Edge clusters) via
the in-cluster Kubernetes API, triggering the 30-minute zero-drop RollingUpdate drain across all regions automatically
with zero external GCP IAM credentials required.
"""
import base64
import hashlib
import json
import os
import re
import signal
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

ACCEPT_MANIFESTS = ', '.join((
    'application/vnd.oci.image.index.v1+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.docker.distribution.manifest.v2+json',
))

SA_DIR = '/var/run/secrets/kubernetes.io/serviceaccount'


def fetch_ghcr_digest(repo_image, tag='main', read_token='', opener=urllib.request.urlopen):
    """Return 'sha256:<64hex>' for ghcr.io/<repo_image>:<tag>, or None if not published/public yet."""
    repo_clean = repo_image.strip().lower().removeprefix('ghcr.io/')
    if not re.match(r'^[a-z0-9_.-]+/[a-z0-9_.-]+$', repo_clean):
        raise ValueError('invalid GHCR repository name: %r' % repo_image)
    if not re.match(r'^[A-Za-z0-9_.-]{1,128}$', tag):
        raise ValueError('invalid GHCR tag: %r' % tag)

    tok_url = 'https://ghcr.io/token?service=ghcr.io&scope=repository:%s:pull' % urllib.parse.quote(repo_clean, safe='/')
    tok_headers = {'User-Agent': 'acr-rollout-watcher/1.0'}
    if read_token:
        b64 = base64.b64encode(('token:' + read_token.strip()).encode('utf-8')).decode('ascii')
        tok_headers['Authorization'] = 'Basic ' + b64

    try:
        with opener(urllib.request.Request(tok_url, headers=tok_headers), timeout=10) as r:
            tok_data = json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            return None
        raise
    bearer = tok_data.get('token') or tok_data.get('access_token') or ''
    if not bearer:
        return None

    man_url = 'https://ghcr.io/v2/%s/manifests/%s' % (repo_clean, urllib.parse.quote(tag, safe=''))
    man_headers = {
        'Accept': ACCEPT_MANIFESTS,
        'Authorization': 'Bearer ' + bearer,
        'User-Agent': 'acr-rollout-watcher/1.0',
    }
    try:
        req = urllib.request.Request(man_url, method='GET', headers=man_headers)
        with opener(req, timeout=12) as r:
            hdr_digest = (r.headers.get('Docker-Content-Digest') or '').strip().lower()
            body = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            return None
        raise

    if re.match(r'^sha256:[0-9a-f]{64}$', hdr_digest):
        return hdr_digest
    if body:
        return 'sha256:' + hashlib.sha256(body).hexdigest()
    return None


def build_image_patch_body(container_name, full_image):
    return {
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'name': container_name,
                            'image': full_image,
                        }
                    ]
                }
            }
        }
    }


class InClusterK8sClient:
    def __init__(self, api_base=None, sa_dir=SA_DIR):
        host = os.environ.get('KUBERNETES_SERVICE_HOST', 'kubernetes.default.svc')
        port = os.environ.get('KUBERNETES_SERVICE_PORT', '443')
        self.base = (api_base or ('https://%s:%s' % (host, port))).rstrip('/')
        self.sa_dir = sa_dir
        ca_file = os.path.join(sa_dir, 'ca.crt')
        self.ssl_ctx = ssl.create_default_context(cafile=ca_file) if os.path.exists(ca_file) else ssl.create_default_context()

    def _token(self):
        with open(os.path.join(self.sa_dir, 'token'), 'r', encoding='utf-8') as f:
            return f.read().strip()

    def namespace(self):
        env_ns = os.environ.get('POD_NAMESPACE', '').strip()
        if env_ns:
            return env_ns
        ns_file = os.path.join(self.sa_dir, 'namespace')
        if os.path.exists(ns_file):
            with open(ns_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return 'acr-daily'

    def get_workload_image(self, namespace, kind_plural, name, container_name):
        url = '%s/apis/apps/v1/namespaces/%s/%s/%s' % (self.base, namespace, kind_plural, name)
        req = urllib.request.Request(url, method='GET', headers={
            'Authorization': 'Bearer ' + self._token(),
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=10) as r:
            obj = json.loads(r.read().decode('utf-8'))
        containers = (((obj.get('spec') or {}).get('template') or {}).get('spec') or {}).get('containers') or []
        for c in containers:
            if c.get('name') == container_name:
                return c.get('image') or ''
        return ''

    def patch_workload_image(self, namespace, kind_plural, name, container_name, full_image):
        url = '%s/apis/apps/v1/namespaces/%s/%s/%s' % (self.base, namespace, kind_plural, name)
        payload = json.dumps(build_image_patch_body(container_name, full_image)).encode('utf-8')
        req = urllib.request.Request(url, data=payload, method='PATCH', headers={
            'Authorization': 'Bearer ' + self._token(),
            'Content-Type': 'application/strategic-merge-patch+json',
            'Accept': 'application/json',
        })
        with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))


def parse_targets(spec_str):
    """Parse 'deployments/acr-relay:relay,statefulsets/acr-daily:server' -> [(kind_plural, name, container), ...]."""
    out = []
    for raw in (spec_str or '').split(','):
        item = raw.strip()
        if not item:
            continue
        lhs, sep, container = item.partition(':')
        kind_plural, slash, name = lhs.partition('/')
        if not sep or not slash or kind_plural not in ('deployments', 'statefulsets') or not name or not container:
            raise ValueError('bad ROLLOUT_TARGETS entry: %r' % item)
        out.append((kind_plural, name, container))
    return out


def reconcile_once(k8s, namespace, repo_image, tag, targets, read_token='', opener=urllib.request.urlopen):
    digest = fetch_ghcr_digest(repo_image, tag=tag, read_token=read_token, opener=opener)
    if not digest:
        return False, 'no_published_ghcr_image'
    repo_clean = repo_image.strip().lower().removeprefix('ghcr.io/')
    desired = 'ghcr.io/%s@%s' % (repo_clean, digest)
    updated = []
    for kind_plural, name, container in targets:
        cur = k8s.get_workload_image(namespace, kind_plural, name, container)
        if cur != desired:
            k8s.patch_workload_image(namespace, kind_plural, name, container, desired)
            updated.append('%s/%s(%s)' % (kind_plural, name, container))
    if updated:
        return True, 'rolled_out %s -> %s' % (', '.join(updated), desired)
    return False, 'up_to_date (%s)' % digest[:19]


def main():
    repo_image = os.environ.get('GHCR_IMAGE', 'khanhonthetrack/acr-daily-server').strip()
    tag = os.environ.get('GHCR_TAG', 'main').strip() or 'main'
    interval_s = max(30, int(os.environ.get('ROLLOUT_POLL_INTERVAL_S', '90')))
    targets_spec = os.environ.get('ROLLOUT_TARGETS', 'deployments/acr-relay:relay,deployments/acr-daily:server')
    read_token = os.environ.get('GHCR_READ_TOKEN', '').strip()

    targets = parse_targets(targets_spec)
    k8s = InClusterK8sClient()
    ns = k8s.namespace()
    stop = False

    def _sig(*_a):
        nonlocal stop
        stop = True

    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, _sig)

    print('ACR Daily rollout watcher started: image=ghcr.io/%s:%s ns=%s targets=%s interval=%ds'
          % (repo_image, tag, ns, targets_spec, interval_s), flush=True)
    last_note = ''
    while not stop:
        try:
            changed, note = reconcile_once(k8s, ns, repo_image, tag, targets, read_token=read_token)
            if changed or note != last_note:
                print('[watcher] %s' % note, flush=True)
                last_note = note
        except Exception as e:
            print('[watcher] check warning: %s' % e, flush=True)
        for _ in range(interval_s):
            if stop:
                break
            time.sleep(1)


if __name__ == '__main__':
    main()
