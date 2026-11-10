# Live relay (ghost cars)

`relay.py` passes each driver's position on to everyone else on the same stage, so the app can draw them
where they are right now. Standard library only (Python 3.9+), nothing stored. The protocol is at the top of
`relay.py`; the app's side is `client/acr_daily/livelink.py`.

## Run it

```bash
python3 relay.py --host 0.0.0.0 --port 8765
```

`GET /` answers how many drivers are connected. The app connects to `ws://<host>:8765/live` (the "Live server"
in the ghost car set-up; the default is the Raspberry Pi on the local network).

## On the Raspberry Pi, for good

Copy `relay.py` to `~/acr-live/` and `acr-live.service` to `~/.config/systemd/user/`, then:

```bash
systemctl --user daemon-reload && systemctl --user enable --now acr-live.service
sudo loginctl enable-linger indycheck      # keeps it running without anyone logged in
```

## For players outside the local network

Tailscale Funnel can publish it over HTTPS on the Pi's existing name (443 and 8443 are already Immich's):

```bash
sudo tailscale funnel --bg --https=10000 http://127.0.0.1:8765
```

The app's live server is then `wss://immich.tail0d617f.ts.net:10000/live`. Anyone can connect: names are
not checked yet (a ticket from the ACR Daily server would do it).
