"""A crew's links and voice, for both modes (copilot.py: the daily for two; casual.py: up to four in a lobby).

The driver is the hub: one link (copilotlink.Link, its own socket) to each co-driver; a co-driver has one, to the driver.
Voice goes out over every link (a link that is not direct, through the live relay, once for all of them); what the
driver hears from one co-driver is played and passed on to the others, tagged with the speaker's seat (0 the driver,
1..3 the co-drivers), so everyone hears everyone and the pages can show who is talking. The driver's car samples go
straight to each co-driver the same way.
"""
import json

from .copilotlink import Link
from .voice import Voice


class Crew:
    """app: the app (its ghostcars.live is the relay's link); me: my seat; driver: whether I am the crew's driver;
    publish(to_steam_id, json string): my link details to that member (the lobby's signal); partners: [(steam id, seat)];
    voice_args: what Voice is made with (settings); on_status(steam_id, text): a member's status line."""

    def __init__(self, app, me, driver, publish, partners, voice_args, on_status=None, link_factory=Link, voice_factory=Voice):
        self.app, self.me, self.driver = app, me, driver
        self.publish, self.on_status = publish, on_status
        self.links = {}                              # steam id -> Link
        self.seats = {}                              # steam id -> seat
        self._wired = None
        self._link_factory = link_factory
        for sid, seat in partners:
            self.add(sid, seat)
        self.voice = voice_factory(self.send_voice, seat=me, **voice_args)

    # ---- the links
    def relay(self):
        return getattr(getattr(self.app, 'ghostcars', None), 'live', None)

    def add(self, sid, seat):
        if sid in self.links:
            self.seats[sid] = seat
            return
        self.seats[sid] = seat

        def samples(m):
            r = self.relay()
            if r is not None:
                r.take_direct(m)

        self.links[sid] = self._link_factory(
            lambda d, sid=sid: self.publish(sid, json.dumps(d, separators=(',', ':'))), samples,
            lambda p, who, sid=sid: self._voice_in(sid, p, who), self.relay,
            on_status=lambda s, sid=sid: self.on_status and self.on_status(sid, s))
        self.links[sid].peer_sid = str(sid)           # (from the start: the relay's crew messages are told apart by it, so
                                                      # one member's relayed voice is never taken for another's)

    def drop(self, sid):
        link = self.links.pop(sid, None)
        self.seats.pop(sid, None)
        if link is not None:
            link.close()

    def sync(self, partners):
        """The members now (steam id, seat): links added for new ones, closed for those gone."""
        want = dict(partners)
        for sid in list(self.links):
            if sid not in want:
                self.drop(sid)
        for sid, seat in want.items():
            self.add(sid, seat)

    def signals(self, signals):
        """The lobby's details addressed to me ({from steam id: json string})."""
        for sid, data in (signals or {}).items():
            link = self.links.get(sid)
            if link is not None and data:
                link.peer(data, sid)

    def first(self):
        return next(iter(self.links.values()), None)

    def modes(self):
        return [l.mode() for l in self.links.values()]

    # ---- the voice
    def send_voice(self, packet, who=None):
        """My voice, or (the driver) a co-driver's passed on, to every link but `skip`: straight where there is a way,
        else through the relay once."""
        self._fan(packet, self.me if who is None else who, None)

    def _fan(self, packet, who, skip):
        relay_once = False
        for sid, link in list(self.links.items()):
            if sid == skip:
                continue
            if link.direct:
                link.send_voice(packet, who, relay=False)
            elif not relay_once:
                relay_once = True
                link.send_voice(packet, who)             # (the relay's crew message goes to the room: once is enough)

    def _voice_in(self, sid, packet, who):
        v = self.voice
        if self.driver:
            who = self.seats.get(sid, who)               # (the hub knows who it came from)
            self._fan(packet, who, sid)                  # ... and passes it on to the others
        if v is not None:
            v.heard(packet, who)

    # ---- status lines (copilot.py: the game's own co-driver; the driver's clock)
    def send_status(self, s):
        relay_once = False
        for link in list(self.links.values()):
            if link.direct:
                link.send_status(s, relay=False)
            elif not relay_once:
                relay_once = True                      # (the relay's crew message goes to the whole room: once is enough)
                link.send_status(s)

    # ---- the relay's link tied to ours
    def wire(self):
        """The relay's link (it can be made again: ghost cars switched, a reconnect) tied to ours: the driver's samples
        sent straight too, the crew's messages (voice, status) to the links."""
        live = self.relay()
        if live is None or self._wired is live:
            return
        self._wired = live
        me = self.app.s

        def crew_in(sid, b):
            for link in list(self.links.values()):
                link.crew(sid, b)
        live.on_crew = crew_in
        if self.driver:
            def tee(m):
                data = dict(m, sid=me.get('steamId') or '', name=me.get('name') or '', car=getattr(live, 'car', '') or '')
                for link in list(self.links.values()):
                    link.send_samples(data)
            live.tee = tee
        else:
            live.tee = None

    def close(self):
        live = self.relay()
        if live is not None:
            live.tee, live.on_crew, live.direct_sid = None, None, None
        if self.voice is not None:
            self.voice.close()
        for link in self.links.values():
            link.close()
        self.links, self.voice, self._wired = {}, None, None
