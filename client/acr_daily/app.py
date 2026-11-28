"""ACR Daily desktop app: main window + the timer window that sits over the game's own timer."""
import ctypes
import json
import os
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import font as tkfont, messagebox, ttk

from . import __version__, i18n, settings
from .i18n import N_, _, local, n_, said
from .api import TOO_OLD, Api, ApiError, refused
from .judge import Judge, fmt_ms
from . import (autodrive, gamelog, gamewatch, ghostui, ingamedrive, ingamehud, leagues, liverally, notify, modinstall,
               nextcard, photos,
               rallyweekend, saveslot, single, tiles, tmtext, updater, waiting, whatsnew, widgets)
from .ghosts import GhostSet
from .copilot import CP_SLOT
from .homeui import HomeUI
from .communityui import CommunityUI
from .inboxui import INBOX_EVERY_MIN, InboxUI
from .profileui import ProfileUI
from .settingsui import SettingsUI
from .signinui import SignInUI
from .browserui import BrowserUI
from .cupbrowser import CupBrowserUI
from .leagueui import LEAGUES_EVERY_MIN, LeaguesUI
from .liverallyui import LiveRallyUI
from .replayui import ReplayUI
from .tabsui import DRIVER_EVERY_MIN, EXTRAS_EVERY_MIN, TabsUI
from .ttui import TT_EVERY_MIN, TimeTrialUI
from .commentui import CommentUI
from .names import norm, same_car, same_track
from .recorder import RouteRecorder
from .standings import standing
from .telemetry import PacketRate, ReplaySource, SharedMemory, steam_account

# Assetto Corsa Rally look: black and white, ACR red as the accent (and for LIVE), green = faster / ready,
# orange = slower. Laid out like RaceRoom's event screen: tabs as blocks (the one on screen solid white), the driver's
# card with their figures, each stage a card of its own (tiles.py: the one on screen filled red), chips with a hairline,
# solid buttons (white on dark, black on red).
BG, PANEL, PANEL2, LINE, LINE2 = '#0A0A0B', '#141417', '#1C1C21', '#1F1F23', '#2B2B31'
WHITE, SOFT, FG2, MUTED = '#F4F4F5', '#D4D4D8', '#A1A1AA', '#85858E'
ACC, GOOD, BAD, LIVE = '#E30613', '#30D158', '#FF453A', '#E10600'
# ACR red as text: the brand's red is for fills, bars and borders (white on it, 4.9:1); as words on the dark panels it
# read at 3.5-4:1, under WCAG AA's 4.5 (a UI review, Nov 2026): this lighter red reads at 5:1 or more on all of them.
# MUTED likewise (3.2-3.75:1 before: '#6B6B74'), for the small grey labels.
ACC_TEXT = '#FF4655'
STRIPE, ME_ROW = '#101013', '#2A0A0E'   # the timing sheet: every other row, and my own
SLOW = '#FF9F0A'   # slower than the reference, and time lost to penalties
# Your first start of a daily (and of a league stage) is the one that counts, and a restart in a run's first minute was
# the most common DNF (Nov 2026): said on DRIVE, on the start line and in the run's first seconds, in orange (0.1.5)
COUNTS_HINT = _('Your first run counts: once the clock starts, a restart or going back to the menu is a DNF.')
COUNTS_LINE = _('THIS RUN COUNTS · a restart is a DNF')
COUNTS_LIVE_MS = 20000
RW_RETRY_S = 2.0          # the start line's look at the save (in_rally), the game having just written it: again after this
# Only a run in the daily's Rally Weekend counts (in_rally): anything else is practice (from 0.1.5)
PRACTICE_HINT = _("Not set up by ACR DAILY, so it doesn't count. DRIVE in ACR DAILY sets it up.")
# (no "PRACTICE" on the timer: the game has a mode of that name; and "your first run is your result" on a daily driven
# already, in a Single Rally Stage, was wrong, the user said, 19 Nov 2026: it says what the run is, it doesn't count)
PRACTICE_LINE = _("Doesn't count · DRIVE in ACR DAILY sets it up")
# a run on a stage the game wasn't taken to by ACR DAILY (set up or resumed by hand in its menus): nothing counts
NOT_HERE_HINT = _("SS%d: not counted, it wasn't started from ACR DAILY. Click DRIVE on it in ACR DAILY.")
NOT_COUNTED = _("Doesn't count ·")
# The race's settings as the game runs them (the game mod reads them live: settings_changed) not the event's: changed in
# the game's own menus before START RALLY. Said on the start line, before the run, and that run doesn't count (no DNF);
# without the mod the save says it once the stage is over (_official_found).
SETTINGS_LINE = _("Doesn't count · settings changed in the game")
SETTINGS_HEAD = _('SETTINGS CHANGED')
SETTINGS_POINTS = (_("This run won't count. Changed in the game: %s"),
                   _('DRIVE again in ACR Daily to set them back'))
# ... and driving aids on that the event forbids (its rules' assists 'off'): the player's own settings, DRIVE can't
AIDS_POINTS = (_("This run won't count. Not allowed here: %s"), _("Switch them off in the game's Driving Assists"))
AIDS_HEAD = _('DRIVING AIDS NOT ALLOWED')
AIDS_LINE = _("Doesn't count · driving aids not allowed")
# Rule of thumb (the user, 19 Nov 2026): during a stage, switching to anything the event doesn't allow is a DNF (a change
# it allows is fine: _watch_run); said before the start, on the start line's note
DURING_LINE = _("On the stage, switching to anything the event doesn't allow is a DNF")
STAGE_HEAD = _('THIS STAGE COUNTS')
STAGE_RULES = (DURING_LINE, _('Restart or quit is a DNF'))
# The pre-start check (the user, 25 Nov 2026: "the user before running the stage should know that it will be a dnf
# unless they change settings"): on the start line, what of the game's settings and driving aids isn't as the event
# says, one row each (what, now, must be), read again twice a second, so it changes as they do (problems_alert)
CHECK_HEAD_COUNT = _("THIS RUN WON'T COUNT")
CHECK_HEAD_DNF = _('THIS RUN WILL BE A DNF')
CHECK_TITLE = _('PRE-START CHECK · CHANGE BEFORE THE START')
CHECK_FIX_SETTINGS = _("Settings: quit to the game's main menu, then DRIVE or CONTINUE in ACR DAILY sets them for you")
CHECK_FIX_AIDS = _("Driving aids: switch them off in the game's Driving Assists")
CHECK_OK = _('Pre-start check: settings and driving aids as the event says')
CHECK_OK_RULES = _('Checked: %s')       # (the event's conditions named: leagues.conditions, App.check_ok_line)
CHECK_ROWS = 8                # rows the check shows at most (7 settings and 3 aids can't all be wrong at once)
CONFIRM_S = 1.0               # a setting read as changed this long before a run is judged by it (settings_judged)
SETTINGS_HINT = _("%s: not counted, its settings were changed in the game (%s). DRIVE in ACR Daily sets them back.")
AIDS_HINT = _("%s: not counted, driving aids not allowed here (%s). Switch them off in the game's Driving Assists.")
# A daily counts only from a run the driver commits to (the 0.1.5.x test builds on): START OFFICIAL RALLY on the commit
# card (commit_offer: after DRIVE, and over the game on the daily's start line), pressed before the stage clock starts.
# The next run of that daily after it is the official one, whatever the game's mode (it can't be told: PRACTICE_CHECK).
# Not pressed, or pressed once the clock runs: practice, ignored (no live start, nothing sent, no DNF, its time dropped
# even if the game saved one). As ACRK's weekly challenges arm each attempt.
# Off since 0.1.5.48 (the user, 19 Nov 2026: "there is no start official window ... the player doesn't need to click
# anything"): every run of a daily counts from its start again, and the start line says once what makes it count
# (_rules_alert: Rally Weekend only; a restart or quitting a DNF in any mode, the mode not known until the finish).
COMMIT_REQUIRED = False
COMMIT_NOTE = _("Press START OFFICIAL RALLY, then drive the stage in Rally Weekend mode: that run is your result. Once "
                "the clock starts, restarting or quitting is a DNF. Runs in other modes don't count, and nothing counts "
                'until you press it.')
# Only the game's official time counts (the 0.1.5.x test builds on): the game saves one only in the Rally Weekend, so a
# run of a daily or a time trial stage without it (Practice, Single Rally Stage, or a time the game lost) is no longer
# sent with the app's own clock (server/src/apptime.js, up to 0.1.5): it doesn't count, and it is no DNF (a daily's is
# sent as 'void', so the server forgets its start and the next run counts: _void_daily, server/src/voids.js). That makes
# the Rally Weekend the only way. (A restart or quitting once the clock runs is a DNF in any mode: the mode is known only
# from the game's save after the finish.)
OFFICIAL_ONLY = True
NO_RALLY_WEEKEND = N_('the game saved no time for it (it only does in Rally Weekend mode)')
UNCOMMITTED_LINE = _('PRACTICE · press START OFFICIAL RALLY first')
# a daily driven already: later runs are practice (said as the rule is: the official run, or the first one up to 0.1.5)
DRIVEN_LINE = _("Driven already · this run doesn't count")
UNCOMMITTED_HINT = _("Practice: this run wasn't started with START OFFICIAL RALLY, so it doesn't count. Press it in ACR "
                     'Daily before the run you want to count.')
# The two rules, said as loudly as the app can (the test builds: RULES_LOUD): a red banner over the daily cards
# (_rules_banner), the commit card after DRIVE (a red banner, the rules, START OFFICIAL RALLY), and the timer window's
# red (or orange) alert on a daily's start line until it is driven (_rules_alert). Once each, where the driver is at that
# moment: a warning box at DRIVE and the status line said the commit card's words again (six times on a first DRIVE,
# a UI review, Nov 2026).
RULES_LOUD = OFFICIAL_ONLY
RULES_BANNER = (_('⚠  A DAILY ONLY COUNTS IN RALLY WEEKEND MODE, AFTER YOU PRESS START OFFICIAL RALLY') if COMMIT_REQUIRED else
                _('⚠  A DAILY ONLY COUNTS IN RALLY WEEKEND MODE'))
RULES_BANNER_SUB = (_('Click DRIVE (it sets up Rally Weekend for you), press START OFFICIAL RALLY on the card that pops '
                      'up, then in the game go to Racing › Rally › Rally Weekend › START RALLY. Runs in Practice or Single '
                      "Rally Stage don't count, because the game doesn't save a time there.") if COMMIT_REQUIRED else
                    _('Click DRIVE (it sets up Rally Weekend for you), then in the game go to Racing › Rally › Rally Weekend › '
                      "START RALLY. Runs in Practice or Single Rally Stage don't count: the game saves no time in those "
                      'modes. Once the clock starts, a restart or quitting is a DNF.'))
COMMIT_BANNER = _('⚠  PRESS THE BUTTON BELOW, THEN DRIVE IN RALLY WEEKEND MODE')
COMMIT_RULES = _('1. Press START OFFICIAL RALLY below before the stage clock starts. Until you do, nothing counts.\n'
                 '2. Drive it in Rally Weekend mode: Racing › Rally › Rally Weekend › START RALLY. Runs in Practice or '
                 "Single Rally Stage don't count.\n"
                 "3. Don't change anything in the game's menu (weather, time of day, conditions, rules): if you do, the "
                 "run doesn't count.\n"
                 '4. Once the clock starts, restarting or quitting is a DNF.')
# ... on the timer window (_rules_alert): a heading and a few short points, as bullets (Overlay.set_alert). The line
# under the time is hidden meanwhile: it said the same (Overlay._sync_line)
START_HEAD_UNCOMMITTED = _("THIS RUN WON'T COUNT")
START_UNCOMMITTED = (_('Press START OFFICIAL RALLY in ACR Daily first'),)
START_HEAD_COMMITTED = _('THIS RUN COUNTS')
START_COMMITTED = (_('Rally Weekend mode only'), DURING_LINE, _('Restart or quit is a DNF'))
# ... without START OFFICIAL RALLY (COMMIT_REQUIRED off): the one warning, on the start line until the daily is driven.
# The mode can't be told at the start (PRACTICE_CHECK), so a restart or quitting is a DNF whatever the mode, and says so
START_HEAD_WEEKEND = _('THIS RUN COUNTS')
START_WEEKEND = (DURING_LINE, _('Restart or quit is a DNF'))
START_HEAD_NORALLY = _('NOT SET UP BY ACR DAILY')      # (the save says so, rw_pre: committed, but in another mode)
# the game's modes as its own menus name them (the game mod tells which: app.game_mode), on the timer by the stage
MODE_NAMES = {'weekend': 'RALLY WEEKEND', 'single': 'SINGLE RALLY STAGE', 'practice': 'FREE PRACTICE',
              'timeattack': 'TIME ATTACK', 'championship': 'CHAMPIONSHIP'}
START_NORALLY = (_("This run won't count"), _('DRIVE in ACR DAILY sets it up'))
STEAM_BG, STEAM_HOVER = '#171A21', '#2A475E'   # Steam's own colours, for the sign-in button
YEL = ACC
FONT = i18n.font('Bahnschrift')
FONT_C = i18n.font('Bahnschrift SemiBold Condensed')   # WRC-style condensed figures (ships with Windows 10/11)

# overlay status badge: text, background, text colour
STATUS = {
    'offline': (_('OFFLINE'), PANEL2, MUTED),
    'standby': (_('STANDBY'), PANEL2, SOFT),
    'ready': (_('READY'), GOOD, '#0A0A0C'),
    'ready_off': (_('READY'), PANEL2, SOFT),       # ... for a run that won't count (practice, START OFFICIAL RALLY not pressed)
    'live': (_('● LIVE'), LIVE, WHITE),
    # ... driving one: no LIVE (it said ● LIVE, in grey, on a run that doesn't count: a UI review, Nov 2026)
    'live_off': (_('NOT COUNTING'), PANEL2, SOFT),
    'rec': (_('● REC'), LIVE, WHITE),
    'finished': (_('FINISHED'), WHITE, '#0A0A0C'),
    'dnf': (_('DNF'), BAD, WHITE),
    'invalid': (_('INVALID'), '#FF8A00', '#0A0A0C'),
    'wait': (_('WAIT'), BAD, WHITE),                # a ranked rally: the wait for my turn, red (liverally.py overlay)
    'go': (_('GO'), GOOD, '#0A0A0C'),               # ... my turn: start now
    'break': (_('BREAK'), SLOW, '#0A0A0C'),         # ... between stages
    'late': (_('MISSED'), '#FF9F0A', '#0A0A0C'),    # ... my turn gone by: to the end of the queue
}
TICK_MS = 50
LR_EVERY_MIN = 5          # live rallies' sessions, now and then (their page open: every minute, liverallyui.py)
# The app's displays are drawn by the game (ingamehud.py, the game mod's hud.lua), and the game mod is always in: from
# 0.1.5.50 (the user, 19 Nov 2026: "using the internal/drawn in game will be mandatory (but you still turn off or on the
# overlays and ghost)"). No switch for it; the app's own windows only where the mod doesn't run.
IN_GAME = True
SPLIT_SHOW_S = 5      # how long the split standings stay on the timer window (user, 19 Nov 2026: "no one looks so long")
FINISH_SHOW_S = 10    # ... and the finish's, provisional or official (the user, 19 Nov 2026; gone sooner when the car is on
                      # a start line again: _drop_stale_standing)


def split_title(frac):
    """A split's standings' heading, by how far into the stage it is ("SPLIT 75%"): the app's own splits, not the
    game's split points; "SPLIT 3 / 3" read like the finish with a quarter of the stage to go (19 Nov 2026)."""
    return _('SPLIT · %d%%') % round(frac * 100)
NEXT_CARD_AFTER_MS = 5000   # the next-daily card shows this long after a run ends
COMMENT_WAIT_S = 15         # ...and waits this long more for the run's comment to be offered (the server's answer)
# A Rally Weekend daily (mode 'weekend'): after the finish the game's own result (stage time + its penalties) is waited
# for in its save, which the game writes once the stage is over. No result = DNF: the run is only sent with it.
OFFICIAL_CHECK_MS = 2000      # how often the save is read while waiting
BACK_IN_MENUS_S = 20          # the game back in its menus this long, a finished run's time not saved: lost (back_in_menus)
CHANGED_WAIT_S = 90           # a result whose save says the set-up changed: the game's next save decides, or this long
                              # without one (_official_found)
OFFICIAL_WAIT_S = 30 * 60     # how long at most (the game still running)
# A run set up by ACR DAILY in the running game: its time at the finish line (the stage clock stopped there + the game's
# penalties, read by the mod) is sent this long after the line, not when the game leaves its results (the user, 24 Nov
# 2026: "when user finishes the stage ... the time is sent THEN"). The seconds: for the game's penalties of the last
# moments to come in.
FINISH_SETTLE_S = 3.0


def finish_settled(a):
    """Has the finish of a waiting run (a: its item, its 'live' read at the line) settled: FINISH_SETTLE_S since?"""
    at = (a.get('live') or {}).get('at')
    return bool(at) and time.time() - at >= FINISH_SETTLE_S
OFFICIAL_CLOCK_MS = 5000      # the game's time and the app's stage clock agree this closely (else: not this run)
OFFICIAL_SAME_MS = 50         # ... and this closely for a result that was in the save already at the start (they have
                              # agreed to the ms on every run so far)
# On the timer window while a finished run waits for it (Overlay.set_alert): the game saves its time only when the driver
# goes on from its results screen; quitting the game or restarting the stage from there loses it (12 Nov 2026: two new
# drivers' finished first runs, a P3 among them).
# The game lost a finished run's result (closed or hung after the finish, or the stage started again from its results
# screen): the app's own stage clock is sent instead, the last line of support. The server takes it for a run without
# respawns; with any, the game's penalty can't be known: a DNF, saying why (server/src/apptime.js), the admin's to look
# at case by case.
OFFICIAL_HEAD = _('SAVE YOUR TIME')
OFFICIAL_ALERT = (_("Go on from the game's results screen"), _('Restarting or quitting on the results screen loses your time'))
# ... and once the game has written its save: the app reads it SETTLE_S after the last write (saveslot.SaveWatch), so
# the timer window shows that wait filling up, then the time saved for a moment (a tester: "how long do I wait?")
SAVING_ALERT = _('Saving your official time…')
SAVED_SHOW_S = 2.5            # "Official time saved" in green on the timer, this long
SWEEP_S = 1.6                 # the bar's piece going across while the results screen is still up
# The timer window's alert, by kind (Overlay.set_alert): background, heading, points, their bullets, a bar down its left
# side. stop: it won't count (red); warn: what to do or not to do (orange, on dark); good: done (green); info: a wait
ALERT_KINDS = {'stop': (ACC, WHITE, WHITE, WHITE, None),
               'warn': (PANEL2, SLOW, WHITE, SLOW, SLOW),
               'good': (GOOD, '#0A0A0C', '#0A0A0C', '#0A0A0C', None),
               'info': (PANEL2, WHITE, SOFT, MUTED, None)}
ALERT_LINES = 3               # points under its heading, at most
# How often we talk to the server, in seconds. The server says (the dailies' 'timing', set in its wrangler.toml, so it
# can stay within its requests a day without a new app); these are what it said when this version came out.
#   liveSendS: our position while on stage; livePollS: the others' while the game is on a daily's stage (start line,
#   results; while driving they come back with our position); liveIdleS: the others' anywhere else;
#   boardS / boardIdleS: today's boards with the game running / not running
TIMING = {'liveSendS': 5, 'livePollS': 5, 'liveIdleS': 15, 'boardS': 120, 'boardIdleS': 300}
# The others' positions are not asked for at all while the game is closed: no telemetry, not even its menus', for this
# long (s). (Its telemetry stands still for a few seconds now and then: SharedMemory lets go and opens it again.)
GAME_GONE_S = 30
# and in minutes, the rest:
CHALLENGE_EVERY_MIN = 10   # today's dailies (the new ones are fetched as soon as the day's are over)
RETRY_S = 15               # ... not fetched (no connection): tried again this often, or at once with RETRY on a card
ROUTES_EVERY_MIN = 60      # the stages that have a route (a new stage's first clean run is sent)
CREDITS_EVERY_MIN = 10     # credits: the balance, a new day's bonus
WIN_W, WIN_H = 1280, 720  # the window at first start, 16:9 (at the screen's scale, within it); then as the user left it
# The window's size (Settings › Window size, from 0.1.5.13): fixed, so a page never reflows or cuts off what it shows
# (a window dragged narrow put the header in two rows and the cards one under another, and hid what didn't fit). At
# the screen's scale (125 % makes 1280 x 720 1600 x 900 pixels); only sizes that fit the screen are offered, and a
# saved one that doesn't fit any more (another screen) is the biggest that does. 'free': resizable, as before.
WINDOW_SIZES = (('1280x720', 1280, 720), ('1440x810', 1440, 810), ('1600x900', 1600, 900), ('1920x1080', 1920, 1080),
                # vertical, for a screen stood on its end (a second one, often): offered where they fit, and picked, the
                # window goes to a screen they fit (work_areas, area_for); the layout stacks for them (STACK_W)
                ('720x1280', 720, 1280), ('810x1440', 810, 1440), ('900x1600', 900, 1600), ('1080x1920', 1080, 1920))
WINDOW_DEFAULT = '1280x720'
MIN_W, MIN_H = 560, 640   # (at 96 dpi) narrow enough for a screen stood on its end (1080 px across, at up to 175 %)
NARROW_W = 1120           # a window narrower than this (at 96 dpi): the header in two rows, the driver's panel across the top
STACK_W = 820             # narrower still: the cards, and the pages' two columns, one under the other (_layout)
LAYOUT = 2                # a window size saved from this layout on is kept (the one before: a narrow window, 440 px)
SIDE_W = 300              # the driver's panel on the left (at 96 dpi)
CARD_H = 230              # a daily's or a time trial stage's card at least this tall (at 96 dpi): its photo


def conditions(ch):
    """'Light rain · Afternoon (16:00)': the weather and time of day the daily is driven in."""
    return ' · '.join(i18n.data(x) for x in ((ch or {}).get('weatherLabel'), (ch or {}).get('timeLabel')) if x)


def set_by(ch):
    """'Set by Ann': a daily a driver bought in the shop (server src/shop.js DAILY_SET), or ''."""
    who = (ch or {}).get('setBy') or {}
    return _('Set by %s') % who['name'] if who.get('name') else ''


def intro_steps():
    """The first start's steps (_show_intro): the dailies' rule as the rest of the app says it. With START OFFICIAL
    RALLY (COMMIT_REQUIRED) a daily counts from the run after it, not the first run (they said "Your first run
    counts" under the red banner that says otherwise: a UI review, Nov 2026)."""
    if COMMIT_REQUIRED:
        return (_('Click DRIVE. The app sets up the stage and starts the game.'),
                _('Press START OFFICIAL RALLY on the card that pops up. Until you do, no run counts.'),
                _('In the game: Racing › Rally › Rally Weekend › Start Rally › J › Confirm › Start Stage.'),
                _("Drive. ACR Daily's timer shows in the game, by the game's own. Once the clock starts, a restart or "
                  'quitting is a DNF.'))
    return (_('Click DRIVE. The app sets up the stage and starts the game.'),
            _('In the game: Racing › Rally › Rally Weekend › Start Rally › J › Confirm › Start Stage.'),
            _("Drive. ACR Daily's timer shows in the game, by the game's own. Your first run counts."))


def keyable(w, cmd, lit=None, unlit=None):
    """A label that acts as a button, from the keyboard too: Tab reaches it, Enter or Space presses it, and while it has
    the focus it looks as under the mouse (lit; unlit when it goes), scrolled into sight if its page scrolls. (The
    buttons were clickable labels only: nothing could be done from the keyboard, a UI review, Nov 2026.)"""
    w.configure(takefocus=1)

    def press(_e):
        if w.cget('cursor') != 'arrow':          # (a button that does nothing now stays so)
            cmd()
        return 'break'
    for seq in ('<Return>', '<KP_Enter>', '<space>'):
        w.bind(seq, press, add='+')

    def focus_in(_e):
        if lit:
            lit()
        p = w
        while p is not None:                     # (the page that scrolls, if one holds it: brought into sight)
            area = tiles.ScrollArea._areas.get(str(p))
            if area is not None:
                area.show(w)
                break
            p = getattr(p, 'master', None)
    w.bind('<FocusIn>', focus_in, add='+')
    if unlit:
        w.bind('<FocusOut>', lambda _e: unlit(), add='+')
    return w


def has_focus(w):
    try:
        return w.focus_displayof() is w
    except (tk.TclError, KeyError):
        return False


def offline_words(e):
    """What the app says when the server can't be asked: in words, not the system's error ([Errno 111] Connection
    refused: it is in the app's notes, waiting.note)."""
    if getattr(e, 'unreachable', False):
        return _("No connection to the ACR Daily server. Check your internet connection.")
    return str(e)


def px(widget, n):
    """n pixels at 96 dpi in this screen's pixels: a wrap width (wraplength is in pixels, the fonts in points, so
    at 150 % a fixed 400 holds two thirds of the words and lines broke after two or three: a UI review, Nov 2026)."""
    return round(n * widget.winfo_fpixels('1i') / 96)


def follow_wrap(box, labels, less=0, least=160):
    """Labels in box break their lines at box's width (less `less` px), whatever the screen's scale: a wraplength in
    pixels set once is too narrow at 150 % (lines of two words) or wider than the box at 100 %. Bound once a box: a
    view drawn again hands over its new labels (the gone ones are let go)."""
    held = getattr(box, '_acr_wrap', None)
    if held is None:
        held = box._acr_wrap = []
        box.bind('<Configure>', lambda e: _rewrap(held, e.width), add='+')
    held[:] = [x for x in held if x[0].winfo_exists()]
    held.extend((lab, less, least) for lab in labels)
    if box.winfo_width() > 1:
        _rewrap(held, box.winfo_width())


def _rewrap(held, width):
    for lab, less, least in held:
        w = max(least, width - less)
        try:
            if int(lab.cget('wraplength')) != w:
                lab.configure(wraplength=w)
        except tk.TclError:
            pass


def is_weekend(ch):
    """The daily is a one-stage Rally Weekend: the game's own result counts (rallyweekend.py)."""
    return (ch or {}).get('mode') == 'weekend'


# Whether a run outside the daily's Rally Weekend is told apart at its start (in_rally) and kept as practice. Off: the
# save can't tell it then. The game writes a one-stage Rally Weekend into its save only once its stage is finished, so
# at the start START RALLY and Practice look the same, and every real run was taken for practice (15 Nov 2026, report
# #175: no live start sent, the timer saying PRACTICE, the wager daily's run refused as never seen on stage). With it
# off, every run of a daily counts from its start, as up to 0.1.5. On again once something tells the mode at the start.
PRACTICE_CHECK = False


def in_rally(ch, b):
    """Is the run starting now the daily's (or time trial stage's) Rally Weekend? Only that run can count (from 0.1.5):
    the game saves an official time only there, and the lost results of 13-15 Nov 2026 (95 reports) were nearly all
    runs driven in Practice or Single Rally Stage, which the app counted all the same. It assumed START RALLY writes the
    rally into the save as in progress, nothing driven: the game doesn't (PRACTICE_CHECK), so it says False then too.
    b: the save as the stage clock starts. -> True / False; None when it can't be told (no save read, or not as
    expected): the run counts, as before."""
    sid = str((ch or {}).get('stageId') or '').lower()
    if b is None or not sid:
        return None
    try:
        p = rallyweekend.progress(b)
    except Exception:
        return None
    return bool(p) and p['done'] == 0 and bool(p['stages']) and p['stages'][0]['stage'].lower() == sid


def penalty_s(e):
    """A board entry's penalty in seconds: its total - its stage clock."""
    if e.get('totalMs') is not None and e.get('clockMs') is not None:
        return round((e['totalMs'] - e['clockMs']) / 1000)
    return 0


def shown_name(e):
    """A board entry's name as the timing sheet shows it: their team's tag first ('[GFX] Ann'; tmtext.tagged)."""
    return tmtext.tagged(e)


def stage_name(ch, short=False):
    """The daily's stage as the game's menu names it ('Peïra Cava - La Bollène-Vésubie'), or its short name
    ('Peïra Cava', for the timer window). Servers before menu names only send the short one."""
    ch = ch or {}
    return (ch.get('stageName') if short else ch.get('menuName') or ch.get('stageName')) or ch.get('track') or ''


def ui(widget, fn, *a):
    """Run fn on the Tk thread."""
    widget.after(0, lambda: fn(*a))


def work_area(x=None, y=None):
    """(left, top, right, bottom) without the taskbar: of the screen the point (x, y) is on (the nearest one: a second
    screen, stood on its end...), else of the main screen; or None."""
    try:
        from ctypes import wintypes
        if x is not None and y is not None:
            class MonitorInfo(ctypes.Structure):
                _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT),
                            ('dwFlags', wintypes.DWORD)]
            u = ctypes.WinDLL('user32')                          # (its own copy: other modules' calls keep their types)
            u.MonitorFromPoint.restype = wintypes.HANDLE
            u.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
            u.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
            mon = u.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)     # MONITOR_DEFAULTTONEAREST
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            if mon and u.GetMonitorInfoW(mon, ctypes.byref(info)):
                r = info.rcWork
                return r.left, r.top, r.right, r.bottom
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(r), 0):   # SPI_GETWORKAREA
            return r.left, r.top, r.right, r.bottom
    except (AttributeError, OSError):
        pass
    return None


def daily_waits():
    """The dailies' and the time trial's runs left waiting for the game's official result when the app last closed
    (waiting.py)."""
    return [dict(x, known=set(x['known']) if x.get('known') is not None else None, closed=0, other=None)
            for x in waiting.load() if x['kind'] in ('daily', 'tt')]


def local_runs():
    """The dailies driven on this PC, sent or not (results.jsonl keeps every run, the queued ones too):
    ((challengeId, the game's Steam accounts), ...)."""
    out = []
    try:
        with open(settings.RESULTS, encoding='utf-8') as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                cid = r.get('challengeId') if isinstance(r, dict) else None
                if cid and not str(cid).startswith(('league:', 'tt:')):
                    out.append((cid, tuple(r.get('gameSteamIds') or ())))
    except OSError:
        pass
    return tuple(out)


def window_size(saved, first, least, area):
    """(width, height, x, y) of the main window: as saved (settings 'window') if it was saved from this layout on, else
    first (x, y: None, the caller centres it); within area (left, top, right, bottom; less the title bar), at least
    least. The narrow window of the layout before (440 px wide) is not kept, nor where it was: it doesn't fit this one."""
    saved = saved if isinstance(saved, dict) and saved.get('layout') == LAYOUT else {}
    aw, ah = area[2] - area[0], area[3] - area[1] - 40
    width = max(least[0], min(aw, int(saved.get('w') or first[0])))
    height = max(least[1], min(ah, int(saved.get('h') or first[1])))
    x, y = saved.get('x'), saved.get('y')
    if isinstance(x, int) and isinstance(y, int):             # (all of it on the screen it was on)
        x, y = max(area[0], min(x, area[2] - width)), max(area[1], min(y, area[3] - 40 - height))
    return width, height, x, y


def fixed_size(key, k, room):
    """The window's fixed size in pixels for Settings' key (WINDOW_SIZES; k: the screen's scale; room: (width, height)
    the screen has for it, less the title bar), or None ('free': resizable). Too big for the room: the biggest size
    that fits, the same way round if one does (wide or tall); none fits: the room."""
    if key == 'free':
        return None
    sizes = [(kk, round(w * k), round(h * k)) for kk, w, h in WINDOW_SIZES]
    want = next(((w, h) for kk, w, h in sizes if kk == key), sizes[0][1:])
    if want[0] <= room[0] and want[1] <= room[1]:
        return want
    fits = [(w, h) for _kk, w, h in sizes if w <= room[0] and h <= room[1]]
    same = [(w, h) for w, h in fits if (h > w) == (want[1] > want[0])]
    return (same or fits)[-1] if fits else (min(want[0], room[0]), min(want[1], room[1]))


def sizes_that_fit(k, room):
    """The keys of WINDOW_SIZES that fit the room at the screen's scale k (the first the same way round as the room
    always offered)."""
    out = [kk for kk, w, h in WINDOW_SIZES if round(w * k) <= room[0] and round(h * k) <= room[1]]
    return out or [next((kk for kk, w, h in WINDOW_SIZES if (h > w) == (room[1] > room[0])), WINDOW_SIZES[0][0])]


def room_of(area):
    """(width, height) a screen's work area (left, top, right, bottom) has for the window: less its title bar."""
    return area[2] - area[0], area[3] - area[1] - 40


def sizes_anywhere(k, rooms):
    """The keys of WINDOW_SIZES that fit any of these rooms (every screen: a vertical one's tall sizes too), in
    WINDOW_SIZES' order."""
    fit = {kk for room in rooms for kk, w, h in WINDOW_SIZES if round(w * k) <= room[0] and round(h * k) <= room[1]}
    return [kk for kk, _w, _h in WINDOW_SIZES if kk in fit] or sizes_that_fit(k, rooms[0])


def area_for(key, k, area, areas):
    """The screen (work area) the window goes on for a fixed size: the one it is on if the size fits there, else the
    first screen it fits (a tall size: the screen stood on its end), else the one it is on."""
    size = next(((round(w * k), round(h * k)) for kk, w, h in WINDOW_SIZES if kk == key), None)
    if size is None:
        return area
    fits = lambda a: size[0] <= room_of(a)[0] and size[1] <= room_of(a)[1]
    if fits(area):
        return area
    return next((a for a in areas if fits(a)), area)


def work_areas():
    """Every screen's (left, top, right, bottom) without its taskbar (Windows' EnumDisplayMonitors); [] elsewhere."""
    try:
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT),
                        ('dwFlags', wintypes.DWORD)]
        u = ctypes.WinDLL('user32')
        out = []
        proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                  wintypes.LPARAM)

        def each(mon, _hdc, _rect, _data):
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            if u.GetMonitorInfoW(mon, ctypes.byref(info)):
                r = info.rcWork
                out.append((r.left, r.top, r.right, r.bottom))
            return 1
        u.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.c_void_p)
        u.EnumDisplayMonitors(None, None, proc(each), 0)
        return out
    except (AttributeError, OSError, ValueError):
        return []


def layout_for(width, k=1.0, extra=0):
    """(narrow, stack) for a window width pixels wide, at k times 96 dpi (App._layout): narrower than NARROW_W (plus
    extra: the header's words wider in the app's language than in English), than STACK_W."""
    w = width / k
    return w < NARROW_W + extra, w < STACK_W


def ends_words(fmt):
    """The header's 'STAGES CLOSE IN %s' -> the words before the time and after it, as the language puts them:
    ('STAGES CLOSE IN', ''), ('A SZAKASZOK', 'MÚLVA ZÁRULNAK')."""
    pre, _s, post = fmt.partition('%s')
    return pre.strip(), post.strip()


def nav_extra(measure):
    """How much wider (96 dpi pixels) the header's nav is in the app's language than in English: measure(text) is the
    width of a text in the nav's font (NARROW_W is the English header's)."""
    from .tabsui import NAV, NAV_EN
    return max(0, sum(measure(t) for _k, t in NAV if t) - sum(measure(t) for t in NAV_EN))


def on_screen(x, y):
    """Is the window's top-left corner on one of the screens (they may have been unplugged since)?"""
    try:
        m = ctypes.windll.user32.GetSystemMetrics      # the virtual screen: every monitor together
        left, top, w, h = m(76), m(77), m(78), m(79)
        return left <= x < left + w - 100 and top <= y < top + h - 100
    except (AttributeError, OSError):
        return x >= 0 and y >= 0


# ---------------------------------------------------------------------- timer window

class Overlay:
    """Borderless always-on-top timer. Drag it over the game's timer once; then lock it (click-through)."""

    def __init__(self, app):
        self.app = app
        o = app.s['overlay']
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.attributes('-alpha', 0.94)
        self.win.configure(bg=BG)
        self.scale = float(o.get('scale') or 1.0)
        self.status = None
        self._blink = False
        # header strip: status badge + what is going on (always visible)
        head_row = tk.Frame(self.win, bg=PANEL)
        head_row.pack(fill='x')
        self.badge = tk.Label(head_row, text=_('STANDBY'), bg=PANEL2, fg=SOFT, padx=8)
        self.badge.pack(side='left', fill='y')
        self.title = tk.Label(head_row, text='ACR DAILY', bg=PANEL, fg=SOFT, anchor='w', padx=8)
        self.title.pack(side='left', fill='x', expand=True)
        tk.Frame(self.win, bg=ACC, height=2).pack(fill='x')       # ACR red rule
        body = tk.Frame(self.win, bg=BG)
        body.pack(fill='both', expand=True, padx=(12, 12), pady=(2, 8))
        self.bar = body   # kept for the drag bindings below
        row = self.row = tk.Frame(body, bg=BG)
        row.pack(anchor='w')
        self.time = tk.Label(row, text='0:00.00', fg=WHITE, bg=BG)
        self.time.pack(side='left')
        self.pen = tk.Label(row, text='', fg='#0A0A0C', bg=SLOW, padx=6)   # shown only after a reset
        self.line = tk.Label(body, text='', fg=MUTED, bg=BG, anchor='w')
        self.line.pack(anchor='w', fill='x')
        # where the driver is looking: on a daily's start line what makes the run count, and while a finished run waits
        # for the game's official time what saves it (new drivers closed the game or restarted from its results screen
        # and lost their time, 12 Nov 2026): a heading, a few points under it as bullets (set_alert, ALERT_KINDS)
        self.alert = tk.Frame(body, bg=PANEL2)
        self.alert_bar = tk.Frame(self.alert, bg=SLOW, width=4)
        self.alert_box = tk.Frame(self.alert, bg=PANEL2)
        self.alert_box.pack(side='left', fill='both', expand=True)
        self.alert_head = tk.Label(self.alert_box, text='', bg=PANEL2, anchor='w', justify='left')
        self.alert_head.pack(anchor='w', fill='x', padx=8, pady=(5, 5))
        self.alert_list = tk.Frame(self.alert_box, bg=PANEL2)
        self.alert_list.columnconfigure(1, weight=1)
        self.alert_rows = [(tk.Label(self.alert_list, text='•', bg=PANEL2, anchor='n'),
                            tk.Label(self.alert_list, text='', bg=PANEL2, anchor='w', justify='left'))
                           for _i in range(ALERT_LINES)]
        # the pre-start check's rows (problems_alert): what, now, must be; under the heading, over the points
        self.alert_check = tk.Frame(self.alert_box, bg=PANEL2)
        self.alert_check.columnconfigure(1, weight=1)
        self.check_title = tk.Label(self.alert_check, text=CHECK_TITLE, bg=PANEL2, anchor='w')
        self.check_title.grid(row=0, column=0, columnspan=4, sticky='w', pady=(0, 2))
        self.check_rows = [(tk.Frame(self.alert_check, width=6, height=6, bg=ACC),
                            tk.Label(self.alert_check, text='', bg=PANEL2, anchor='w'),
                            tk.Label(self.alert_check, text='', bg=PANEL2, anchor='e'),
                            tk.Label(self.alert_check, text='', bg=PANEL2, anchor='e'))
                           for _i in range(CHECK_ROWS)]
        self._alert_key = ('', (), None, ())
        self.alert.bind('<Configure>', self._alert_wrap)     # (its words as wide as it is: the window can be wider)
        # under it, while that time is on its way: a thin bar (set_progress)
        self.prog = tk.Canvas(body, height=4, bg=PANEL2, highlightthickness=0, bd=0)
        self._prog_fill = self.prog.create_rectangle(0, 0, 0, 4, fill=ACC, width=0)
        self._head = (head_row, self.badge, self.title)
        # split / finish standings (RallySimFans style): shown for a few seconds after each split
        self.panel = tk.Frame(body, bg=BG)
        tk.Frame(self.panel, bg=LINE, height=2).pack(fill='x', pady=(6, 4))
        head = tk.Frame(self.panel, bg=BG)
        head.pack(fill='x')
        self.p_title = tk.Label(head, text='', fg=MUTED, bg=BG, anchor='w')
        self.p_title.pack(side='left')
        self.p_pos = tk.Label(head, text='', fg=WHITE, bg=BG, anchor='e')
        self.p_pos.pack(side='right')
        grid = tk.Frame(self.panel, bg=BG)
        grid.pack(fill='x', pady=(2, 0))
        grid.columnconfigure(1, weight=1)
        self.p_rows = []
        for i in range(4):
            cells = (tk.Label(grid, bg=BG, fg=MUTED, anchor='e', width=3),
                     tk.Label(grid, bg=BG, fg=SOFT, anchor='w'),
                     tk.Label(grid, bg=BG, fg=SOFT, anchor='e'))
            for c, w in enumerate(cells):
                w.grid(row=i, column=c, sticky='ew', padx=(0, 8) if c < 2 else 0)
            self.p_rows.append(cells)
        self.p_pb = tk.Label(self.panel, text='', fg=MUTED, bg=BG, anchor='w')
        self.p_pb.pack(anchor='w', fill='x', pady=(2, 0))
        self._fonts()
        self.win.update_idletasks()
        self.win.geometry('+%d+%d' % widgets.fit_on_screen(o.get('x', 60), o.get('y', 60), self.win.winfo_reqwidth(),
                                                           self.win.winfo_reqheight()))
        alert = (self.alert, self.alert_bar, self.alert_box, self.alert_head, self.alert_list) + \
            tuple(w for r in self.alert_rows for w in r)
        for w in (self.win, body, row, self.time, self.line, self.pen) + self._head + alert:
            w.bind('<ButtonPress-1>', self._press)
            w.bind('<B1-Motion>', self._drag)
            w.bind('<ButtonRelease-1>', self._release)
            w.bind('<Button-3>', self._menu)
        self.win.update_idletasks()
        self.set_locked(True)
        self.win.withdraw()                          # (never on the screen since 0.1.6: show)

    def _fonts(self):
        s = self.scale
        q = s * self.win.winfo_fpixels('1i') / 96      # (pixels: the scale x the screen's; the fonts' points scale themselves)
        self.badge.configure(font=(FONT_C, int(12 * s)))
        self.title.configure(font=(FONT_C, int(12 * s)))
        self.time.configure(font=(FONT_C, int(40 * s)))
        self.pen.configure(font=(FONT_C, int(16 * s)))
        self.line.configure(font=(FONT_C, int(13 * s)), wraplength=int(300 * q), justify='left')
        self.alert_head.configure(font=(FONT_C, int(15 * s)), wraplength=int(256 * q))
        for dot, text in self.alert_rows:
            dot.configure(font=(FONT_C, int(13 * s)))
            text.configure(font=(FONT_C, int(13 * s)), wraplength=int(238 * q))
        self.check_title.configure(font=(FONT_C, int(10 * s)))
        for mark, what, now, want in self.check_rows:
            mark.configure(width=max(4, int(6 * q)), height=max(4, int(6 * q)))
            what.configure(font=(FONT_C, int(13 * s)))
            now.configure(font=(FONT_C, int(12 * s)))
            want.configure(font=(FONT_C, int(13 * s)))
        self._alert_wrap()
        self.prog.configure(width=int(276 * q), height=max(3, int(4 * q)))
        self.win.minsize(int(300 * q), 1)    # same width in every state, so it never jumps around
        self.p_title.configure(font=(FONT_C, int(12 * s)))
        self.p_pos.configure(font=(FONT_C, int(17 * s)))
        for pos, name, gap in self.p_rows:
            pos.configure(font=(FONT_C, int(13 * s)))
            name.configure(font=(FONT_C, int(13 * s)))
            gap.configure(font=(FONT_C, int(13 * s)))
        self.p_pb.configure(font=(FONT_C, int(11 * s)))

    def _press(self, e):
        self._off = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _drag(self, e):
        if widgets.WINDOWS:
            self.win.geometry('+%d+%d' % (e.x_root - self._off[0], e.y_root - self._off[1]))

    def _release(self, _e):
        o = self.app.s['overlay']
        o['x'], o['y'] = self.win.winfo_x(), self.win.winfo_y()
        settings.save(self.app.s)

    def _menu(self, e):
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label=_('Bigger'), command=lambda: self.resize(1.15))
        m.add_command(label=_('Smaller'), command=lambda: self.resize(1 / 1.15))
        m.add_command(label=_('Hide'), command=lambda: self.app.toggle_overlay(False))
        m.tk_popup(e.x_root, e.y_root)

    def resize(self, k):
        self.scale = max(0.6, min(3.0, self.scale * k))
        self.app.s['overlay']['scale'] = round(self.scale, 2)
        settings.save(self.app.s)
        self._fonts()
        self.app._overlay_buttons()           # (its size on the settings page)

    def set_locked(self, locked):
        """Locked = clicks go through to the game (WS_EX_TRANSPARENT | WS_EX_LAYERED)."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.win.winfo_id())
            GWL_EXSTYLE, LAYERED, TRANSPARENT, NOACTIVATE = -20, 0x80000, 0x20, 0x08000000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | LAYERED | NOACTIVATE
            style = style | TRANSPARENT if locked else style & ~TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass
        self.win.configure(highlightthickness=0 if locked else 2, highlightbackground=YEL)

    def show_standing(self, title, st, pb_label=_('vs your best today')):
        """st: standings.standing(...) result, or None to hide the panel. pb_label: the last line's words (the time
        trial's best is the week's)."""
        # (packed or not, not mapped: while the game draws the displays this window is withdrawn, never mapped, and a
        # panel never taken away stayed in the game for good: 19 Nov 2026, SS2's finish still up on SS1)
        if st is None:
            if self.panel.winfo_manager():
                self.panel.pack_forget()
            return
        self.p_title.configure(text=title)
        self.p_pos.configure(text='P%d / %d' % (st['pos'], st['of']), fg=ACC_TEXT if st['pos'] == 1 else WHITE)
        for i, (pos, name, gap) in enumerate(self.p_rows):
            if i < len(st['rows']):
                p, n, g, me = st['rows'][i]
                pos.configure(text=str(p), fg=ACC_TEXT if me else MUTED)
                name.configure(text=n[:22], fg=ACC_TEXT if me else SOFT, font=(FONT_C if me else FONT_C, int(13 * self.scale)))
                gap.configure(text='' if p == 1 else '+%.3f' % (g / 1000), fg=ACC_TEXT if me else SOFT)
            else:
                for w in (pos, name, gap):
                    w.configure(text='')
        pb = st.get('pbGap')
        self.p_pb.configure(text='' if pb is None else '%s  %s%.3f' % (pb_label, '+' if pb >= 0 else '−', abs(pb) / 1000),
                            fg=SLOW if pb is not None and pb > 0 else GOOD if pb is not None else MUTED)
        if not self.panel.winfo_manager():
            self.panel.pack(anchor='w', fill='x')

    def set_alert(self, head, lines=(), kind='warn', checks=()):
        """A note under the time: a heading in big letters, and up to ALERT_LINES short points under it as bullets;
        kind: one of ALERT_KINDS (head '' takes it away). checks: the pre-start check's rows, (what, now, must be) each,
        between the two (App.problems_alert). The line under the time hides meanwhile (_sync_line)."""
        lines = tuple(lines)[:ALERT_LINES]
        checks = tuple(tuple(r) for r in checks or ())[:CHECK_ROWS]
        if (head, lines, kind, checks) == self._alert_key:
            return
        self._alert_key = (head, lines, kind, checks)
        if not head:
            self.alert.pack_forget()
            self._sync_line()
            return
        bg, head_fg, fg, dot_fg, bar = ALERT_KINDS[kind]
        for w in (self.alert, self.alert_box, self.alert_list, self.alert_check, self.check_title):
            w.configure(bg=bg)
        self.alert_head.configure(text=head, bg=bg, fg=head_fg)
        self.alert_head.pack_configure(pady=(5, 1 if lines or checks else 5))
        self.check_title.configure(fg=fg)
        for i, (mark, what, now, want) in enumerate(self.check_rows):
            if i < len(checks):
                w_, n_, m_ = checks[i]
                mark.configure(bg=dot_fg)
                what.configure(text=w_, bg=bg, fg=fg)
                now.configure(text='%s  →' % n_, bg=bg, fg=fg)
                want.configure(text=m_, bg=bg, fg=head_fg)
                mark.grid(row=i + 1, column=0, sticky='w', padx=(0, 6))
                what.grid(row=i + 1, column=1, sticky='w')
                now.grid(row=i + 1, column=2, sticky='e', padx=(8, 4))
                want.grid(row=i + 1, column=3, sticky='e')
            else:
                for w in (mark, what, now, want):
                    w.grid_remove()
        if bar:
            self.alert_bar.configure(bg=bar)
            if not self.alert_bar.winfo_manager():
                self.alert_bar.pack(side='left', fill='y', before=self.alert_box)
        elif self.alert_bar.winfo_manager():
            self.alert_bar.pack_forget()
        for i, (dot, text) in enumerate(self.alert_rows):
            if i < len(lines):
                dot.configure(bg=bg, fg=dot_fg)
                text.configure(text=lines[i], bg=bg, fg=fg)
                dot.grid(row=i, column=0, sticky='n', padx=(0, 6))
                text.grid(row=i, column=1, sticky='w')
            else:
                dot.grid_remove()
                text.grid_remove()
        if lines and not self.alert_list.winfo_manager():
            self.alert_list.pack(anchor='w', fill='x', padx=(10, 8), pady=(0, 6))
        elif not lines and self.alert_list.winfo_manager():
            self.alert_list.pack_forget()
        if checks:                             # (always right under the heading)
            self.alert_check.pack(anchor='w', fill='x', padx=(10, 8), pady=(2, 4), after=self.alert_head)
        elif self.alert_check.winfo_manager():
            self.alert_check.pack_forget()
        if not self.alert.winfo_manager():
            self.alert.pack(anchor='w', fill='x', pady=(6, 0), after=self.line if self.line.winfo_manager() else self.row)
        self._alert_wrap()                     # (the bar on or off: its width the same, so no <Configure>)
        self._sync_line()

    def _alert_wrap(self, e=None):
        """The alert's heading and points wrap at its width (less its padding, the bar, the bullets)."""
        width = e.width if e is not None else self.alert.winfo_width()
        if width <= 1:
            return
        bar = self.alert_bar.winfo_reqwidth() if self.alert_bar.winfo_manager() else 0
        head = max(80, width - bar - 16)
        text = max(60, width - bar - 18 - self.alert_rows[0][0].winfo_reqwidth() - 6)
        if abs(int(self.alert_head.cget('wraplength')) - head) > 2:
            self.alert_head.configure(wraplength=head)
        for _dot, label in self.alert_rows:
            if abs(int(label.cget('wraplength')) - text) > 2:
                label.configure(wraplength=text)

    def _sync_line(self):
        """The line under the time: hidden while the alert shows (it said the same, smaller), but not on stage, where it
        is the gap to the ghost."""
        hide = bool(self.alert.winfo_manager()) and self.status not in ('live', 'live_off')
        if hide and self.line.winfo_manager():
            self.line.pack_forget()
        elif not hide and not self.line.winfo_manager():
            self.line.pack(anchor='w', fill='x', after=self.row)

    def set_progress(self, mode, frac=0.0, colour=ACC):
        """The bar under the note: None (none), 'wait' (a piece going across: nothing to measure yet) or a share filled
        (frac, 0 to 1)."""
        self._prog = None if mode is None else (mode, frac, colour)     # (the displays in the game: snapshot)
        if mode is None:
            if self.prog.winfo_manager():
                self.prog.pack_forget()
            return
        if not self.prog.winfo_manager():
            above = next(w for w in (self.alert, self.line, self.row) if w.winfo_manager())
            self.prog.pack(anchor='w', fill='x', pady=(4, 0), after=above)
        w = max(self.prog.winfo_width(), int(self.prog.cget('width')))
        h = int(self.prog.cget('height'))
        if mode == 'wait':
            seg = w * 0.28
            x = (time.monotonic() % SWEEP_S) / SWEEP_S * (w + seg) - seg
            box = (x, 0, x + seg, h)
        else:
            box = (0, 0, w * max(0.0, min(1.0, frac)), h)
        self.prog.coords(self._prog_fill, *box)
        if self.prog.itemcget(self._prog_fill, 'fill') != colour:
            self.prog.itemconfigure(self._prog_fill, fill=colour)

    def show(self, on):
        """(Never on the screen since 0.1.6, widgets.WINDOWS: the game draws what it says, snapshot.)"""
        if on and widgets.WINDOWS:
            self.win.deiconify()
            self.win.attributes('-topmost', True)
        else:
            self.win.withdraw()

    def snapshot(self):
        """What the timer says now, as drawn (shown or hidden: the displays in the game, ingamehud.py, say it either
        way): {status, badge (text, colour, background), title, time (text, colour), ms (the time's own ms), running
        (its clock running: the game moves it on), pen, line (text, colour) or None, alert {head, lines, bg, head_fg,
        fg, dot_fg, bar} or None, progress (mode, frac, colour) or None, panel {title, pos, rows [(pos, name, gap,
        mine)], pb (text, colour)} or None}."""
        on = lambda w: bool(w.winfo_manager())                   # noqa: E731
        ms, running = getattr(self, '_ms', (None, False))
        s = {'status': self.status, 'badge': (self.badge.cget('text'), self.badge.cget('fg'), self.badge.cget('bg')),
             'title': self.title.cget('text'), 'time': (self.time.cget('text'), self.time.cget('fg')),
             'ms': ms, 'running': running, 'pen': self.pen.cget('text') if on(self.pen) else '',
             'line': (self.line.cget('text'), self.line.cget('fg')) if on(self.line) else None, 'alert': None, 'panel': None,
             'progress': getattr(self, '_prog', None) if on(self.prog) else None}
        head, lines, kind, checks = self._alert_key
        if head and on(self.alert):
            bg, head_fg, fg, dot_fg, bar = ALERT_KINDS[kind]
            s['alert'] = {'head': head, 'lines': list(lines), 'bg': bg, 'head_fg': head_fg, 'fg': fg, 'dot_fg': dot_fg,
                          'bar': bar, 'checks': [list(r) for r in checks], 'check_title': CHECK_TITLE if checks else ''}
        if on(self.panel):
            s['panel'] = {'title': self.p_title.cget('text'), 'pos': self.p_pos.cget('text'),
                          'rows': [(p.cget('text'), n.cget('text'), g.cget('text'), n.cget('fg') == ACC_TEXT)
                                   for p, n, g in self.p_rows if n.cget('text')],
                          'pb': (self.p_pb.cget('text'), self.p_pb.cget('fg'))}
        return s

    def render(self, status, title, total_ms, resets, line, line_color=MUTED):
        """status: a key of STATUS (badge), title: header text, then the big time and the line under it."""
        text, bg, fg = STATUS[status]
        if status in ('live', 'rec'):                      # the red dot blinks while recording
            self._blink = (time.monotonic() % 1.0) < 0.6
            text = text if self._blink else text.replace('●', '○')
        if (self.badge.cget('text'), self.badge.cget('bg')) != (text, bg):
            self.badge.configure(text=text, bg=bg, fg=fg)
        if status != self.status:
            self.status = status
            self._sync_line()                  # (on stage the line under the time shows, alert or not)
        if self.title.cget('text') != title:
            self.title.configure(text=title)
        exact = status in ('finished', 'dnf', 'invalid')
        self._ms = (total_ms, status in ('live', 'live_off', 'rec') and bool(total_ms))   # (the displays in the game)
        t = fmt_ms(total_ms, 3 if exact else 2) if total_ms else '0:00.00'
        if self.time.cget('text') != t:
            self.time.configure(text=t)
        tc = MUTED if status in ('offline', 'standby') else WHITE
        if self.time.cget('fg') != tc:
            self.time.configure(fg=tc)
        pen = '+%d s' % (resets * self.app.penalty_s()) if resets and self.app.penalty_s() else ''
        if self.pen.cget('text') != pen:
            self.pen.configure(text=pen)
            if pen:
                self.pen.pack(side='left', padx=(10, 0))
            else:
                self.pen.pack_forget()
        if self.line.cget('text') != line or self.line.cget('fg') != line_color:
            self.line.configure(text=line, fg=line_color)
        # (no -topmost here: it moved the window in Windows' order on every tick, 20 times a second. App._keep_on_top
        # puts it back on top only when the game has come over it: widgets.keep_on_top)


# ---------------------------------------------------------------------- main window

class App(TabsUI, HomeUI, SignInUI, LeaguesUI, BrowserUI, CupBrowserUI, InboxUI, TimeTrialUI, SettingsUI, ProfileUI,
          CommentUI, CommunityUI, LiveRallyUI, ReplayUI):
    credits = None                 # (before __init__ sets it: the tests build bare apps)
    layout_narrow = False          # the window narrower than NARROW_W (_layout)
    _nav_extra = None              # (_layout) the header's words in this language: so much wider than in English
    layout_stack = False           # ... and than STACK_W
    _layout_job = None
    local_runs = ()
    _drive_wait = None
    coin_img = None
    game_watch = None              # what the game does while a finished run waits (gamewatch.py; _game_watch_on)
    notifier = None                # the sound and notification when a run's official time is in or lost (notify.py)
    start_hidden = False           # (main(): the window kept off the screen until the launcher is on it, launcher.py)

    def __init__(self):
        self.s = settings.load()
        self.api = Api(self.s)
        self._league_init()
        self._tt_init()
        self._lr_init()                            # live rallies (liverallyui.py)
        replay = os.environ.get('ACR_DAILY_REPLAY')
        self.shm = ReplaySource(replay, float(os.environ.get('ACR_DAILY_REPLAY_FROM') or 0)) if replay else SharedMemory()
        # the day's dailies, by slot: {'ch': challenge, 'judge': Judge, 'board': leaderboard, 'ghost_for', 'ghost_name'}
        self.dailies = {}
        self._offered = set()    # dailies (ids, so per day) the next-daily card has already offered
        self._next_pending = set()   # dailies whose run's card is still to come (_offer_next): it carries the comment
        # finished Rally Weekend runs waiting for the game's official result (_await_official), on disk too: one left
        # waiting when the app last closed is looked for again (_resume_waiting)
        self.awaiting = daily_waits()
        self.next_card = None
        self.active = 1          # the daily on screen: the one being driven, or the one whose stage is loaded
        self.live_at = 0.0       # last live-position update sent
        self.recorder = None
        self.auto_rec = RouteRecorder()   # always on: new stages get their route from your first clean run
        self.country = saveslot.driver_country()   # nationality from the in-game driver profile (flag on the website)
        self.known_routes = None          # normalised names of stages that already have a route (None = unknown)
        self.net_msg = ''
        self.last_frame = None
        self.credits = None               # /api/credits (a prototype: off unless the server has it on)
        self._drive_wait = None           # what DRIVE waits for on the server (a stake...): further clicks say so
        self.local_runs = local_runs()    # the dailies driven on this PC (_driven: a run not sent yet counts too)

        self.root = tk.Tk()
        if self.start_hidden:
            # (the whole window was drawn at its saved size, then the launcher put over it 200 ms later: the old
            # window seen for a moment at every start, the user 24 Nov 2026)
            self.root.withdraw()
        self.root.title(_('ACR Daily (beta)'))
        self.root.configure(bg=BG)
        self.root.geometry('%dx%d' % (WIN_W, WIN_H))
        try:
            self.root.iconbitmap(os.path.join(os.path.dirname(__file__), 'icon.ico'))
        except tk.TclError:
            pass
        self._ov_allowed = True   # the timer allowed on screen right now (_apply_visibility)
        self._ov_state = (True, False)   # (allowed, the screen hidden from) as last applied (_apply_visibility)
        self._style()
        self._build()
        self._place_window()
        self.root.bind('<Configure>', self._layout_soon, add='+')   # (narrower, wider: _layout)
        self.overlay = Overlay(self)
        self.widgets = {k: cls(self, k) for k, cls in widgets.CLASSES.items()}   # optional displays
        self._widget_buttons()
        from . import watch as watch_mod
        self.watch = watch_mod.Watch(self)               # WATCH: the camera on another driver live (watch.py)
        self.ghostcars = ghostui.GhostOverlay(self)     # ghost cars on the road (a test, ghostui.py)
        self.ghost_setup = None
        self.ghost_buttons()
        self._replay_init()                        # every run kept as a replay (replayui.py, replays.py)
        # (no "Getting started" box: 0.2 opens on the launcher, and the game's pages say what each part is)
        self.open_home()                          # (where the app opens: HOME, its tiles; homeui.py)
        self._gate_check()                         # (not signed in: Steam first, over it all; signinui.py)
        self._wtick = 0
        self.root.protocol('WM_DELETE_WINDOW', self.quit)

        self.update_msg = ''
        self.update_info = None    # {'version', 'url'} when the server has a newer app
        self.update_busy = ''      # bar text while downloading / installing
        self._pending_update = None
        threading.Thread(target=updater.cleanup_old, daemon=True).start()
        self.panel_until = 0
        self.panel_slot = None     # the daily whose standings (a split, its finish) the timer shows under the time
        self.refresh_challenge()
        self.refresh_routes()
        self.refresh_leagues()
        self.refresh_tt()
        self.refresh_live_rallies()
        self.refresh_credits()
        self.refresh_unread()
        self.refresh_driver()
        self.refresh_community()                   # (HOME's COMMUNITY tile; a time trial's track; after a game update: communityui.py)
        threading.Thread(target=self.flush_leagues, daemon=True).start()
        threading.Thread(target=self.check_update, daemon=True).start()
        self._resume_waiting()
        self.root.after(TICK_MS, self.tick)
        self.root.after(60000, self.periodic)
        self.root.after(3000, self.poll_live)

    # the active daily
    @property
    def challenge(self):
        return self.dailies.get(self.active, {}).get('ch')

    @property
    def judge(self):
        return self.dailies.get(self.active, {}).get('judge')

    @property
    def board(self):
        return self.dailies.get(self.active, {}).get('board')

    @property
    def ghost_name(self):
        return self.dailies.get(self.active, {}).get('ghost_name') or '#1'

    def _pick_active(self, f):
        """The daily being driven; otherwise the one whose stage and car are loaded; otherwise keep."""
        for slot, d in self.dailies.items():
            if d.get('judge') and d['judge'].state == 'running':
                return slot
        if f is not None and f.track:
            for slot, d in self.dailies.items():
                if same_track(f.track, d['ch']) and same_car(f.car, d['ch']):
                    return slot
            for slot, d in self.dailies.items():    # a stage known by its start line: on it, or driving up to it
                if d.get('judge') and (d['judge'].state == 'armed' or d['judge'].approaching):
                    return slot
        return self.active if self.active in self.dailies else min(self.dailies or {1: None})

    # -------------------------------------------------------------- layout

    def _style(self):
        st = ttk.Style(self.root)
        st.theme_use('clam')
        # Segoe UI: its digits are all the same width, so the times line up like a timing sheet
        st.configure('Treeview', background=BG, fieldbackground=BG, foreground=SOFT, rowheight=28,
                     font=('Segoe UI', 10), borderwidth=0, relief='flat')
        st.configure('Treeview.Heading', background=PANEL, foreground=MUTED, font=(FONT, 8, 'bold'),
                     relief='flat', borderwidth=0, padding=(6, 6))
        st.map('Treeview.Heading', background=[('active', PANEL)])
        st.map('Treeview', background=[('selected', PANEL)], foreground=[('selected', WHITE)])
        st.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])   # no frame around the sheet
        # the car picker of a league event run in a class (leagueui.py): dark, a hairline around it
        st.configure('TCombobox', fieldbackground=PANEL, background=PANEL, foreground=SOFT, arrowcolor=FG2,
                     bordercolor=LINE2, lightcolor=PANEL, darkcolor=PANEL, padding=(6, 3))
        st.map('TCombobox', fieldbackground=[('readonly', PANEL)], foreground=[('readonly', SOFT)],
               selectbackground=[('readonly', PANEL)], selectforeground=[('readonly', WHITE)],
               bordercolor=[('focus', FG2), ('hover', FG2)], arrowcolor=[('hover', WHITE)])
        self.root.option_add('*TCombobox*Listbox.background', PANEL)
        self.root.option_add('*TCombobox*Listbox.foreground', SOFT)
        self.root.option_add('*TCombobox*Listbox.selectBackground', ACC)
        self.root.option_add('*TCombobox*Listbox.selectForeground', WHITE)
        self.root.option_add('*TCombobox*Listbox.font', (FONT, 10))

    def _lbl(self, parent, text='', size=11, fg=SOFT, bold=False, **kw):
        font = kw.pop('font', (FONT, size, 'bold' if bold else 'normal'))
        return tk.Label(parent, text=text, bg=kw.pop('bg', BG), fg=fg, font=font, anchor='w', justify='left', **kw)

    def _k(self, parent, text, bg=BG):
        """A small spaced-out uppercase label (like the website's)."""
        return tk.Label(parent, text=i18n.spaced(text), bg=bg, fg=MUTED, font=(FONT, 7, 'bold'), anchor='w')

    def _rule(self, parent=None, pady=0, padx=None):
        f = tk.Frame(parent or self.root, bg=LINE, height=1)
        f.pack(fill='x', padx=(0 if parent else 20) if padx is None else padx, pady=pady)
        return f

    # -------------------------------------------------------------- pages: HOME, the inbox, the settings, the driver page
    def _page_on(self):
        """Is a page (HOME, the inbox, the settings, the driver page, the community's) in the view's place?"""
        return bool(self.home_view or self.inbox_view or self.settings_view or self.profile_view or self.community_view
                    or self.lr_view)

    def _pages_leave(self):
        """Whichever page is open makes way (the view clicked packs its own cards; a page opened, its own box)."""
        self._home_leave()
        self._inbox_leave()
        self._settings_leave()
        self._profile_leave()
        self._community_leave()
        self._lr_leave()

    def _page_show(self, box):
        """A page (its flag set) in the view's place: the view's cards and the first start's steps put away. -> what to
        put back besides (_page_hide): nothing since the timing sheet left the window (0.1.6)."""
        hid = []
        for w in (self.daily_box, self.league_box, self.tt_box, getattr(self, '_intro_box', None)):
            if w is not None and w.winfo_exists():
                w.pack_forget()
        self._render_strip()                         # (put away too: it sits over the dailies)
        box.pack(fill='both', expand=True, before=self._view_end)
        return hid

    def _page_hide(self, box, hid):
        """The page goes: the first start's steps back under the dailies' cards (not dismissed yet: _place_intro)."""
        box.pack_forget()
        for w, info in hid:
            w.pack(**info)
        self._place_intro()

    def _place_intro(self):
        """The first start's steps (until 'Got it') under the dailies' cards, DAILIES on screen only: they are the
        dailies' steps (DRIVE, a Rally Weekend), not the time trial's, the competitions' or a page's. (tabsui._mark_tabs:
        every time the view changes.)"""
        intro = getattr(self, '_intro_box', None)
        if intro is None or not intro.winfo_exists():
            return
        on = getattr(self, '_tab_on', None) == 'daily'
        if on and not intro.winfo_manager():
            intro.pack(fill='x', padx=20, pady=(14, 0), after=self._view_end)   # (the view's end is always there)
        elif not on and intro.winfo_manager():
            intro.pack_forget()

    @staticmethod
    def _padx(box):
        """Where a view's contents start and end in box: 20 px from the window's sides, closer to a column beside
        them (the leagues' two columns set padx_)."""
        return getattr(box, 'padx_', 20)

    def _link(self, parent, text, cmd, fg=FG2):
        """Text that acts as a button: quiet until hovered."""
        l = tk.Label(parent, text=text, bg=BG, fg=fg, font=(FONT, 9), cursor='hand2')
        l.bind('<Button-1>', lambda _e: cmd())
        l.bind('<Enter>', lambda _e: l.configure(fg=WHITE))
        l.bind('<Leave>', lambda _e: None if has_focus(l) else l.configure(fg=l._fg))
        l._fg, l._cmd = fg, cmd                     # (a card draws it as its own words: tiles.py)
        keyable(l, lambda: l._cmd(), lambda: l.configure(fg=WHITE), lambda: l.configure(fg=l._fg))
        return l

    def _btn(self, parent, text, cmd, primary=False, surface=BG):
        """A button, as RaceRoom's: primary solid (white on the dark, black on a red card), the others a hairline
        outline. surface: what it sits on (a card's colour: tiles.py restyles it as the card changes)."""
        b = tk.Label(parent, text=text, font=(FONT_C, 11), padx=14, pady=5, cursor='hand2')
        b.bind('<Button-1>', lambda _e: cmd())
        b.bind('<Enter>', lambda _e: self._btn_hover(b))
        b.bind('<Leave>', lambda _e: None if has_focus(b) else self._btn_style(b, b._primary))
        self._btn_style(b, primary, surface)
        keyable(b, cmd, lambda: self._btn_hover(b), lambda: self._btn_style(b, b._primary))
        return b

    @staticmethod
    def _btn_style(b, primary, surface=None):
        b._primary = primary
        b._surface = surface = surface or getattr(b, '_surface', BG)
        if surface == ACC:              # on a red card: solid black, or a light red hairline
            b.configure(bg=BG if primary else ACC, fg=WHITE, highlightthickness=0 if primary else 1,
                        highlightbackground=tiles.RED['chip'])
        else:
            b.configure(bg=WHITE if primary else surface, fg=BG if primary else SOFT,
                        highlightthickness=0 if primary else 1, highlightbackground=LINE2)

    @staticmethod
    def _btn_hover(b):
        """Under the mouse: red (a white button), white (the rest); a button that does nothing stays as it is."""
        if b.cget('cursor') == 'arrow':
            return
        if b._primary and b._surface != ACC:
            b.configure(bg=ACC, fg=WHITE)
        else:
            b.configure(bg=WHITE, fg=BG)

    def _build(self):
        """The window in 16:9 panels, as RaceRoom's: the header (logo, the nav, the icons, the day and the time), the
        driver's panel on the left (their card; put away on HOME), the view on the right (its cards side by side, the
        timing sheet under them; or a page: HOME, the inbox, the settings, the driver page), the status bar along
        the bottom."""
        r = self.root
        k = r.winfo_fpixels('1i') / 96
        self.coin_img = self._coin()               # by an amount of credits (the balance, the stake)
        # ---- header
        head = tk.Frame(r, bg=BG)
        head.pack(fill='x', padx=20, pady=(14, 14))
        self._logo_img = self._logo()
        if self._logo_img:
            tk.Label(head, image=self._logo_img, bg=BG, bd=0).pack(side='left')
        else:
            self._lbl(head, 'ACR DAILY', font=(FONT_C, 15), fg=WHITE).pack(side='left')
        tk.Label(head, text=_('BETA'), bg=BG, fg=ACC_TEXT, font=(FONT_C, 10), padx=5, pady=0, highlightthickness=1,
                 highlightbackground=ACC).pack(side='left', padx=(10, 0))   # still being built: bugs are expected
        # top right, as RaceRoom's clock: when the dailies close ("STAGES CLOSE IN 7:40"), the time in white between the
        # words in grey (around it as the language puts them: "A SZAKASZOK 7:40 MÚLVA ZÁRULNAK"); _tick keeps it
        ends = self.ends_f = tk.Frame(head, bg=BG)
        ends.pack(side='right')
        self.ends_l = [self._lbl(ends, '', fg=FG2, font=(FONT_C, 11)), self._lbl(ends, '', fg=WHITE, font=(FONT_C, 13)),
                       self._lbl(ends, '', fg=FG2, font=(FONT_C, 11))]
        self._ends_words = ends_words(_('STAGES CLOSE IN %s'))
        for i, l in enumerate(self.ends_l):
            l.pack(side='left', padx=(6 if i else 0, 0))
        self._build_tabs(head)                     # the nav; the icons on the right (tabsui.py)
        self._head = head                          # (a narrow window: the nav on a row of its own, _header_layout)
        self._head_wide = [(w, w.pack_info()) for w in head.pack_slaves()]

        # ---- footer (first, so the panels never squeeze it out), as RaceRoom's bar along the bottom: what goes on on
        # the left (the state in a chip, the timer window's badge; what goes on, what to do), on the right the update
        # (when there is one), the website and the version
        foot = tk.Frame(r, bg=BG)
        foot.pack(side='bottom', fill='x', padx=20, pady=(0, 10))
        tk.Frame(foot, bg=LINE, height=1).pack(fill='x', pady=(0, 8))
        bar = self._status_bar = tk.Frame(foot, bg=BG)
        bar.pack(fill='x')
        self.foot_l = self._lbl(bar, '', fg=MUTED, font=(FONT, 8))
        self.foot_l.pack(side='right')
        self._link(bar, _('Website'), self.open_site).pack(side='right', padx=(0, 16))
        # a new version: one red button, one click (shown only when there is one)
        self.upd = tk.Label(bar, text='', bg=ACC, fg=WHITE, font=(FONT_C, 11), padx=10, pady=2, cursor='hand2')
        self.upd.bind('<Button-1>', lambda _e: self.do_update())
        keyable(self.upd, self.do_update)
        text, bg, fg = STATUS['standby']
        self.state_l = tk.Label(bar, text=text, bg=bg, fg=fg, font=(FONT_C, 10), padx=8, pady=1)
        self.state_l.pack(side='left', anchor='n')
        self.status_l = self._lbl(bar, '', fg=WHITE, font=(FONT, 10))
        self.status_l.pack(side='left', anchor='n', padx=(10, 0))
        self.sub_l = self._lbl(bar, '', fg=FG2, font=(FONT, 9))
        self.sub_l.pack(side='left', anchor='n', fill='x', expand=True, padx=(14, 12), pady=(1, 0))
        bar.bind('<Configure>', lambda e: self.sub_l.configure(wraplength=max(200, round(e.width * 0.42))))

        # the driver's panel and the view, in a frame that scrolls once they are taller than the window (a small
        # window: DRIVE out of reach on DAILIES, TIME TRIAL and HOME, a UI review, Nov 2026); at least as tall as the
        # window, so a view that fills it still does (tiles.ScrollArea fill)
        self._view_scroll = tiles.ScrollArea(r, BG, fill=True)
        self._view_scroll.outer.pack(fill='both', expand=True, pady=(0, 12))
        # RANKED's registration bar (as iRacing's), between the view and the footer in every view (liverallyui.py)
        self._build_lr_bar(r, before=self._view_scroll.outer)
        body = self._body = self._view_scroll.inner
        for seq, n in (('<Prior>', -1), ('<Next>', 1)):      # (Page Up / Page Down: the view, as the wheel does)
            r.bind(seq, lambda e, n=n: self._view_scroll.page(n) if e.widget.winfo_class() not in ('Entry', 'Text', 'TCombobox') else None)
        # ---- the driver's panel, on the left (its width fixed: what is in it fills it)
        side = self._side = tk.Frame(body, bg=BG, width=round(SIDE_W * k))
        side.pack(side='left', fill='y', padx=(20, 0))
        side.pack_propagate(False)
        self._build_driver_strip(side)             # the driver's card: picture, name, rating, world rank, credits (tabsui.py)
        self._head_rule = tk.Frame(side, bg=BG, height=1)   # (the sign-in goes under it, the card over it)
        self._head_rule.pack(fill='x')
        # signed out only (signed in, the driver's card has the name, the balance and Sign out): the Steam button
        acct = self._acct_row = tk.Frame(side, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        self.acct_l = self._lbl(acct, '', fg=FG2, font=(FONT, 9), bg=PANEL, wraplength=round(260 * k))
        self.acct_l.pack(anchor='w', padx=14, pady=(12, 8))
        # a Steam-coloured button with the Steam logo (Steam is a trademark of Valve Corporation)
        self._steam_img = self._steam_logo()
        self.steam_b = tk.Label(acct, text=(' ' + _('SIGN IN WITH STEAM')), image=self._steam_img or '', compound='left',
                                bg=STEAM_BG, fg=WHITE, font=(FONT_C, 10), padx=10, pady=5, cursor='hand2')
        self.steam_b.bind('<Button-1>', lambda _e: self.login_click())
        keyable(self.steam_b, self.login_click, lambda: self.steam_b.configure(bg=STEAM_HOVER),
                lambda: self.steam_b.configure(bg=STEAM_BG))
        self.steam_b.bind('<Enter>', lambda _e: self.steam_b.configure(bg=STEAM_HOVER))
        self.steam_b.bind('<Leave>', lambda _e: self.steam_b.configure(bg=STEAM_BG))

        # ---- the view, on the right: its cards (no timing sheet under them from 0.1.6: each card links to its standings
        # on the website, Timing sheet ›; the board is still fetched for the ghosts, the live gap and the next-daily card)
        main = self._main = tk.Frame(body, bg=BG)
        main.pack(side='left', fill='both', expand=True)
        main.bind('<Configure>', lambda _e: self._cards_resized())    # (a bigger window: taller cards)
        self._view_scroll.cv.bind('<Configure>', lambda _e: self._cards_resized(), add='+')
        # today's two special stages, a card each side by side (tiles.py); the active one (driven / loaded) filled red
        self.daily_box = tk.Frame(main, bg=BG)
        self.daily_box.pack(fill='x')
        if RULES_LOUD:                             # (the test builds: over the cards, in red, what makes a daily count)
            self._rules_banner(self.daily_box, k)
        grid = tk.Frame(self.daily_box, bg=BG)     # (the cards' grid: tiles.TileRow)
        grid.pack(fill='x')
        self._daily_row = tiles.TileRow(grid, 2, base=self._card_base())
        self.cards = {}
        for slot in (1, 2):
            tile = self._daily_row.add(tiles.Tile(grid, restyle=self._btn_style))
            tile.button = self._btn(tile.cv, _('DRIVE  ›'), lambda s=slot: self.drive_click(s), primary=True)
            # the wager daily (credits): a strip under its card, shown by _wager_marks; its standings on the website
            self.cards[slot] = {'tile': tile, 'drive': tile.button, 'wager': tile.strip(),
                                'timing': self._link(tile.cv, _('Timing sheet ›'), lambda s=slot: self.open_page('/#ss%d' % s))}
            tile.render(self._card_spec(slot))
        self._build_league_box()                   # the events of my leagues, in the cards' place when shown
        self._build_tt_box()                       # the time trial's two stages, in the cards' place when shown (ttui.py)
        self._build_inbox_box()                    # the inbox, in the cards' place when shown
        self._build_settings_box()                 # the settings, there too (settingsui.py)
        self._build_profile_box()                  # the driver page: profile, achievements, shop, customize (profileui.py)
        self._build_home_box()                     # HOME: a photo tile for each part of the app (homeui.py)
        self._build_community_box()                # COMMUNITY: tracks, cars and liveries to install (communityui.py)
        self._build_lr_box()                       # LIVE: live rallies, their sessions and queues (liverallyui.py)
        self._view_end = tk.Frame(main, bg=BG, height=round(4 * k))    # (each view's cards are packed just over it)
        self._view_end.pack(fill='x')
        self._account_ui()
        self._overlay_buttons()

    # -------------------------------------------------------------- actions

    def penalty_s(self):
        return int((self.challenge or {}).get('penaltyMs', 0) / 1000)

    def login_click(self):
        """The Steam button, or Sign out (signinui.py: signed out, the sign-in screen comes back)."""
        if self.s.get('token'):
            self.sign_out()
        else:
            self.sign_in()

    def _account_ui(self):
        """The sign-in panel in the driver's panel: signed out, it says so with the Steam button; signed in it gives way to
        the driver's card (the name, the balance by the coin and Sign out: tabsui.py)."""
        row = getattr(self, '_acct_row', None)
        if getattr(self, 'set_acct_b', None) is not None:      # (SETTINGS > Account: who, and the button to change it)
            signed = bool(self.s.get('token'))
            self.set_acct_l.configure(text=(self.s.get('name') or _('Signed in')) if signed else _('Not signed in'))
            self.set_acct_b.configure(text=_('SIGN OUT') if signed else _('SIGN IN WITH STEAM'))
            self._btn_style(self.set_acct_b, not signed)
        if self.s.get('token'):
            self.steam_b.pack_forget()
            if row is not None:
                row.pack_forget()
        else:
            self.acct_l.configure(text=_('Not signed in · runs wait until you are'), fg=MUTED, image='', cursor='')
            self.steam_b.configure(text=(' ' + _('SIGN IN WITH STEAM')))
            self.steam_b.pack(anchor='w', padx=14, pady=(0, 14))
            if row is not None and not row.winfo_manager():     # (where the driver's card is when signed in)
                row.pack(fill='x', after=self._head_rule)

    def _logo(self):
        """The ACR Daily logo at the screen's scale (acr_daily/logo-<px>.png, made by make_icon.py)."""
        scale = self.root.winfo_fpixels('1i') / 96
        px = 48 if scale < 1.25 else 72 if scale < 1.75 else 96
        try:
            return tk.PhotoImage(file=os.path.join(os.path.dirname(__file__), 'logo-%d.png' % px))
        except tk.TclError:
            return None

    def _coin(self):
        """A credit's coin at the screen's scale (acr_daily/coin-<px>.png, made by make_icon.py), or None."""
        scale = self.root.winfo_fpixels('1i') / 96
        px = 12 if scale < 1.25 else 18 if scale < 1.75 else 24
        try:
            return tk.PhotoImage(file=os.path.join(os.path.dirname(__file__), 'coin-%d.png' % px))
        except tk.TclError:
            return None

    def _steam_logo(self):
        """The Steam mark at the screen's scale (acr_daily/steam-<px>.png, made by make_steam_logo.py)."""
        scale = self.root.winfo_fpixels('1i') / 96
        px = 18 if scale < 1.25 else 27 if scale < 1.75 else 36
        try:
            return tk.PhotoImage(file=os.path.join(os.path.dirname(__file__), 'steam-%d.png' % px))
        except tk.TclError:
            return None

    def open_guide(self):
        if self.api.configured:
            webbrowser.open(self.api.site + '/guide')

    def open_discord(self):
        """The ACR Daily Discord: the server sends /discord on to the current invite."""
        if self.api.configured:
            webbrowser.open(self.api.site + '/discord')

    def _show_intro(self):
        """First start: the steps under the dailies' cards, until 'Got it' (DAILIES on screen: _place_intro)."""
        box = self._intro_box = tk.Frame(self._main, bg=PANEL, highlightthickness=1, highlightbackground=LINE2)
        bar = tk.Frame(box, bg=PANEL)    # title + buttons on top, so they show even on a short screen
        bar.pack(fill='x', padx=14, pady=(10, 6))
        tk.Label(bar, text=i18n.spaced(_('Getting started')), bg=PANEL, fg=ACC_TEXT, font=(FONT, 7, 'bold'),
                 anchor='w').pack(side='left')
        steps = intro_steps()
        texts = []
        for i, t in enumerate(steps, 1):
            row = tk.Frame(box, bg=PANEL)
            row.pack(fill='x', padx=14, pady=(0, 10 if i == len(steps) else 1))
            tk.Label(row, text='%02d' % i, bg=PANEL, fg=ACC_TEXT, font=(FONT_C, 10), width=3, anchor='nw').pack(side='left', anchor='n')
            lab = tk.Label(row, text=t, bg=PANEL, fg=SOFT, font=(FONT, 9), anchor='w', justify='left', wraplength=700)
            lab.pack(side='left', fill='x', expand=True)
            texts.append(lab)
        follow_wrap(box, texts, 80)         # (the box's own width: a fixed 700 px broke lines badly at 150 %)

        def done():
            self.s['introSeen'] = True
            settings.save(self.s)
            box.destroy()
        ok = tk.Label(bar, text=_('GOT IT'), bg=ACC, fg=WHITE, font=(FONT_C, 10), padx=10, pady=2, cursor='hand2')
        ok.bind('<Button-1>', lambda _e: done())
        keyable(ok, done)
        ok.pack(side='right')
        g = tk.Label(bar, text=_('Full guide ›'), bg=PANEL, fg=FG2, font=(FONT, 9), cursor='hand2')
        g.bind('<Button-1>', lambda _e: self.open_guide())
        g.bind('<Enter>', lambda _e: g.configure(fg=WHITE))
        g.bind('<Leave>', lambda _e: None if has_focus(g) else g.configure(fg=FG2))
        keyable(g, self.open_guide, lambda: g.configure(fg=WHITE), lambda: g.configure(fg=FG2))
        g.pack(side='right', padx=12)
        self._place_intro()

    def save_settings(self):
        settings.save(self.s)

    def toggle_widget(self, key):
        w = self.widgets[key]
        w.cfg['visible'] = not w.cfg.get('visible')
        settings.save(self.s)
        w.show(w.cfg['visible'] and getattr(self, '_ov_ok', {}).get(key, self._ov_allowed))
        self._widget_buttons()

    def toggle_auto_drive(self):
        on = not self.s.get('autoDrive', False)
        if on:
            try:
                keys = autodrive.describe_keys(autodrive.player_keys())   # this player's own menu keys
            except ValueError as e:
                messagebox.showwarning('ACR Daily', _('Auto-drive can\'t be used: %s. DRIVE still sets everything up; '
                                                    'go through the game\'s menus by hand.') % e)
                return
            if not messagebox.askyesno('ACR Daily', _('AUTO clicks through the game\'s menus after every DRIVE (dailies, '
                                       'leagues, 1V1s, cups) and stops at the Service Park. You press START STAGE.\n\n'
                                       'Keys: %s.\n\nTouch the keyboard or mouse to take over. Turn it on?') % keys):
                return
        self.s['autoDrive'] = on
        settings.save(self.s)
        self._slide_auto_switch(on)
        if not on and getattr(self, 'auto', None):
            self.auto.cancel()

    def toggle_notify(self):
        """The sound and Windows notification when a run's official time is in, or lost (notify.py): on or off."""
        self.s['notify'] = not self.s.get('notify', True)
        settings.save(self.s)

    def toggle_only_daily(self):
        o = self.s['overlay']
        o['onlyOnDaily'] = not o.get('onlyOnDaily', True)
        settings.save(self.s)
        self._overlay_buttons()

    # ---- the displays in the game (ingamehud.py; drawn by the game mod, mod/ACRDailyGhosts/Scripts/hud.lua)
    def ingame_on(self):
        """The displays drawn by the game (IN_GAME): always, with the game mod always in. "Show the timer" and the
        displays' own switches still say what is shown; where the mod doesn't run (not in yet, UE4SS broken by a game
        update) the app's windows show instead (ingame_drawn)."""
        return IN_GAME

    def ingame_place(self):
        place = (self.s.get('overlay') or {}).get('inGamePlace', 'dock')
        return 'dock' if place == 'left' else place if place in ingamehud.PLACES else 'dock'   # ('left': before 0.1.5.48)

    def _pulse(self):
        """The game mod's pulse (ingamehud.ModPulse): is it running, and the game's mode it says."""
        pulse = getattr(self, '_mod_pulse', None)
        if pulse is None:
            pulse = self._mod_pulse = ingamehud.ModPulse(os.path.join(settings.DIR, ingamehud.CAMERA_FILE),
                                                         lambda p: ghostui.open_kept(p, binary=True))
        return pulse

    def ingame_drawn(self):
        """Is the game drawing the displays now (on, and the mod seen running: ModPulse)? Then the app's windows over
        the game stand down. (Read only.)"""
        if not self.ingame_on():
            return False
        return self._pulse().alive()

    def game_mode(self):
        """The game's mode on the loaded stage, as the game mod tells it (its race event: 'weekend' for a Rally
        Weekend, 'single', 'practice', 'championship', 'other'), or None: it can't be told (no mod running: ghost cars'
        real cars and the displays in the game both off; the menus; a game the mod doesn't know). The game's save can't
        tell it before the finish (PRACTICE_CHECK), so without the mod a run counts from its start whatever the mode."""
        m = self._pulse().mode()
        return m if m in ingamehud.MODES else None

    def mode_rw(self):
        """Is the stage loaded in the game a Rally Weekend's that ACR DAILY took the game to? True / False, or None
        (can't be told: game_mode). One the player set up by hand in the game's menus, even with a daily's settings,
        is False: it doesn't count (set_up_here)."""
        m = self.game_mode()
        if m is None:
            return None
        return m == 'weekend' and self.set_up_here() is not False

    def set_up_here(self):
        """Did ACR DAILY take the game to the Rally Weekend stage loaded now (its DRIVE / CONTINUE, or the game started
        by the app with its set-up: the mod keeps it until the game's main menu is back, appui.lua)? True / False, or
        None: can't be told (the pages in the game off, an older mod, no Rally Weekend stage). Read twice a second."""
        if getattr(self, 'ingame_app', None) is None:
            return None
        now = time.monotonic()
        seen = getattr(self, '_here_seen', None)
        if seen is None or now - seen[0] > 0.5:
            live = ingamedrive.live_setup()
            seen = self._here_seen = (now, None if live is None else live.get('ours'))
        return seen[1]

    def game_settings(self):
        """The race's settings on the loaded stage as the game runs them (the game mod reads them: ingamehud.SETTINGS),
        or None (no mod running, no stage, an older mod)."""
        return self._pulse().settings()

    def settings_changed(self, rules):
        """What of an event's rules (rallyweekend.RULES with the event's over them: a daily's or a time trial stage's
        'weekend', a league event's 'rules') the race the game runs now doesn't hold: its settings changed in the game's
        menu, or driving aids on that the event forbids -> [what] (leagues.RULE_NAMES / AID_NAMES, in English), [] when
        all is as it must be, None when it can't be told (game_settings)."""
        s = self.game_settings()
        if s is None or not leagues.plausible(s):   # (not a Rally Weekend's settings: a misread, not a change)
            return None
        try:
            out = leagues.live_changed(s, rules)
        except saveslot.SaveError:                  # (rules the app can't read: the save check after the stage says it)
            return None
        out = out + leagues.aids_broken(self._pulse().aids(), self._pulse().dash(), rules)
        self._seen_since(rules, out)
        return out

    def _seen_since(self, rules, got):
        """Since when the game has said `got` for these rules, read after read (settings_judged) -> monotonic s."""
        seen = self.__dict__.setdefault('_judged', {})
        key, now = repr(rules), time.monotonic()
        if not got:
            seen.pop(key, None)
            return now
        was = seen.get(key)
        if was is None or was[0] != list(got):
            seen[key] = was = (list(got), now)
        return was[1]

    def settings_judged(self, rules):
        """settings_changed for a decision (a DNF, a run not counted): only what the game has said CONFIRM_S on end,
        the same at each read (the start line's check reads it twice a second): a reading of a moment, as a stage loads
        or restarts, is no change (Rally Madeira Legend SS7, 25 Nov 2026: a DNF the stewards cancelled). -> [what], []
        (nothing, or not for long enough yet: the next reads tell), None (can't be told)."""
        got = self.settings_changed(rules)
        if not got:
            return got
        return got if time.monotonic() - self._seen_since(rules, got) >= CONFIRM_S else []

    def check_rows(self, rules):
        """The pre-start check: each setting or driving aid not as the event says -> [(what, now, must be)] in the
        app's language (leagues.live_check), [] when all is as it must be or it can't be told."""
        s = self.game_settings()
        if s is None or not leagues.plausible(s):
            return []
        try:
            rows = leagues.live_check(s, self._pulse().aids(), self._pulse().dash(), rules)
        except saveslot.SaveError:
            return []
        return [(local(a), local(b), local(c)) for a, b, c in rows]

    @staticmethod
    def check_ok_line(rules):
        """The start line's line once its check has passed: the conditions the stage runs with, named ("Checked:
        Hardcore Mode On · damage Realistic · driving aids Off"), so after a DRIVE or a CONTINUE the driver knows what
        changing would make a DNF (the user, 25 Nov 2026). CHECK_OK when the rules can't be read."""
        try:
            parts = leagues.conditions(rules)
        except saveslot.SaveError:
            return CHECK_OK
        return CHECK_OK_RULES % ' · '.join('%s %s' % (local(a), local(b)) for a, b in parts)

    def start_line_rules(self):
        """The rules of the run waiting on its start line (armed, or driving up to it; not once its clock runs): a
        league stage's event's, a time trial stage's or a daily's -> the rules ({} for the defaults), or None."""
        def waits(j):
            return j is not None and (j.state == 'armed' or getattr(j, 'approaching', False))
        target = getattr(self, 'drive_target', 'daily')
        if target == 'league':
            run = getattr(self, 'league_run', None)
            if run and not run.get('wait') and not run.get('over') and waits(run.get('judge')):
                return run['ev'].get('rules') or {}
            return None
        for _slot, t in sorted((getattr(self, 'tt', None) or {}).items()):
            if waits(t.get('judge')):
                return (t.get('ch') or {}).get('weekend') or {}
        for _slot, d in sorted((getattr(self, 'dailies', None) or {}).items()):
            if waits(d.get('judge')):
                return (d.get('ch') or {}).get('weekend') or {}
        return None

    def aids_to_force(self):
        """Should the game mod switch the driving aids off now (main.lua force_aids_off)? Yes while a run of an event
        without them waits on its start line: DRIVE sets up everything the event says, the aids too (the user, 25 Nov
        2026). Never once the clock runs: switching one on during the stage stays a DNF (_watch_run)."""
        rules = self.start_line_rules()
        return rules is not None and dict(rallyweekend.RULES, **rules).get('assists') == 'off'

    @staticmethod
    def problems_alert(problems, rows=(), dnf=False):
        """The pre-start check on the start line, for what's wrong (settings_changed: settings changed in the game's
        menu, driving aids the event forbids): whether the run won't count or will be a DNF (dnf: a league stage after
        its first, a ranked session's), what to change, one row each (rows: check_rows: what, now, must be), and how ->
        (head, points, 'stop', rows). Without rows (none read) the points name what instead."""
        aids = set(leagues.AID_NAMES.values())
        changed = [x for x in problems if x not in aids]
        on = [x for x in problems if x in aids]
        rows = tuple(rows or ())[:CHECK_ROWS]
        points = []
        if not rows and changed:
            points.append(_('Changed in the game: %s') % ', '.join(local(x) for x in changed))
        if not rows and on:
            points.append(_('Not allowed here: %s') % ', '.join(local(x) for x in on))
        if changed:
            points.append(CHECK_FIX_SETTINGS)
        if on:
            points.append(CHECK_FIX_AIDS)
        return (CHECK_HEAD_DNF if dnf else CHECK_HEAD_COUNT), tuple(points[:ALERT_LINES]), 'stop', rows

    @staticmethod
    def problems_hint(label, problems):
        """The main window's line after a run that didn't count for what settings_changed found (label: SS1, TT2...)."""
        aids = set(leagues.AID_NAMES.values())
        changed = [x for x in problems or () if x not in aids]
        if changed:
            return SETTINGS_HINT % (label, ', '.join(local(x) for x in changed))
        return AIDS_HINT % (label, ', '.join(local(x) for x in problems or ()))

    @staticmethod
    def problems_line(problems):
        """The line by the strip for a run that won't count for what settings_changed found -> (text, colour)."""
        aids = set(leagues.AID_NAMES.values())
        return (SETTINGS_LINE if any(x not in aids for x in problems or ()) else AIDS_LINE), BAD

    def _watch_run(self, holder, j, evs, rules):
        """Rule of thumb (the user, 19 Nov 2026): during a stage, switching to what the event doesn't allow (its
        settings changed, driving aids it forbids) is a DNF; a change it allows is fine (aids switched off on an event
        that leaves them to each driver: "that's common sense"). While the run goes (from its start: holder, a daily's,
        a time trial stage's or a league run's dict), the game is checked against the event's rules (settings_changed,
        the game mod) and anything not allowed ends it as a DNF (the judge's 'dnf', handled as any other). -> the
        events to handle after evs."""
        if 'start' in evs:
            holder['watch'] = True
            return []
        if not holder.get('watch') or j.state != 'running':
            return []
        what = self.settings_judged(rules)
        if not what:
            return []
        holder['watch'] = False
        waiting.note('%s: not allowed by the event, during the stage: %s (DNF)' % (j.ch.get('id') or 'run', ', '.join(what)))
        return j.disqualify(said("%s changed during the stage: not as the event allows", ', '.join(what)))

    def mode_label(self):
        """The game's mode in its own menu's words, and its colour (green: the Rally Weekend, the only one that counts;
        orange: another), or None (can't be told)."""
        m = self.game_mode()
        if m is None or m == 'weekend':            # (0.2: DRIVE always sets up the Rally Weekend: no chip for it,
            return None                            # the user, 20 Nov 2026; only another mode, a warning, is named)
        return (MODE_NAMES.get(m) or _('ANOTHER MODE')), SLOW

    def toggle_ingame_clock(self):
        """Our clock in the game (under the displays): for a driver who hides the game's own HUD."""
        o = self.s['overlay']
        o['inGameClock'] = not o.get('inGameClock')
        settings.save(self.s)
        self._overlay_buttons()

    def set_ingame_place(self, place):
        if place in ingamehud.PLACES:
            self.s['overlay']['inGamePlace'] = place
            settings.save(self.s)
            self._overlay_buttons()

    def ingame_keys(self):
        """The keys for the in-game cards' buttons (SETTINGS › Timer › Keys in the game): {action: key}, F8 DRIVE, F9
        COMMENT, F10 CLOSE unless others were picked (two the same, as a hand-edited file could say: the defaults)."""
        got = (self.s.get('overlay') or {}).get('inGameKeys') or {}
        keys = {a: got.get(a) if got.get(a) in nextcard.GAME_KEYS else k for a, k in nextcard.DEFAULT_KEYS.items()}
        return keys if len(set(keys.values())) == len(keys) else dict(nextcard.DEFAULT_KEYS)

    def set_ingame_key(self, action, key):
        """A key picked for one of the cards' buttons; one another button had: they swap."""
        keys = self.ingame_keys()
        if action not in keys or key not in nextcard.GAME_KEYS or keys[action] == key:
            return
        for a, k in keys.items():
            if k == key:
                keys[a] = keys[action]
        keys[action] = key
        self.s['overlay']['inGameKeys'] = keys
        settings.save(self.s)
        nextcard.set_keys(keys)
        self._overlay_buttons()

    def ingame_tick(self):
        """For good, FEED_S apart (main(): never in the tests' apps): what the displays say, to the game mod, while
        the displays in the game are on."""
        try:
            self._ingame_feed()
        except Exception:                          # (never the app's end: the next look tries again)
            self._hud_feed = None
        self.root.after(int(ingamehud.FEED_S * 1000), self.ingame_tick)

    CARD_NAMES = ('comment_card', 'next_card', 'tt_next_card')   # the cards that take keys in the game, first first

    def _cards_up(self):
        """The cards up now that the game can draw and work with keys (comment, the next daily's / time trial's)."""
        out = []
        for name in self.CARD_NAMES:
            card = getattr(self, name, None)
            if card is not None and getattr(card, 'alive', False) and hasattr(card, 'snapshot'):
                out.append(card)
        return out

    def _ingame_cards(self):
        return [s for s in (c.snapshot() for c in self._cards_up()) if s]

    def _ingame_actions(self, drawn):
        """The cards while the game draws them: their windows put away (back when it stops), and the keys pressed for
        them in the game (F8 DRIVE, F9 a comment typed there, F10 CLOSE: ingamehud.Actions) done."""
        cards = self._cards_up()
        for card in cards:
            card.in_game(drawn)
        acts = getattr(self, '_hud_actions', None)
        if acts is None:
            acts = self._hud_actions = ingamehud.Actions(os.path.join(settings.DIR, ingamehud.ACTIONS_FILE),
                                                         lambda p: ghostui.open_kept(p, binary=True))
        for cid, action, text in acts.poll():
            card = next((c for c in cards if '%x' % id(c) == cid), None)
            if action == 'typing':
                self._card_typing = True           # (the box open in the game: the buttons send / close it)
            elif action in ('comment', 'close', 'drive'):
                self._card_typing = False
            if drawn and card is not None:
                card.act(action, text)
        # a wheel's / pad's buttons set for the cards (cardbuttons.py): COMMENT opens the box (the comment's key, for
        # the mod) and sends it (Enter); CLOSE closes the box, or the card
        cb = getattr(self, '_card_buttons', None)
        if cb is None:
            from . import cardbuttons
            cb = self._card_buttons = cardbuttons.CardButtons(self)
        pressed = cb.tick() if (drawn and cards) or cb.capturing else []
        if not cards:
            self._card_typing = False
        for action in pressed:
            from . import ingamenav
            typing = getattr(self, '_card_typing', False)
            if action == 'close':
                if typing:
                    ingamenav.press_key(0x1B)          # (Esc: the box closed, nothing sent)
                    self._card_typing = False
                else:
                    cards[0].act('close', '')
            elif action == 'comment':
                if typing:
                    ingamenav.press_key(0x0D)          # (Enter: sent)
                else:
                    k = self.ingame_keys().get('comment', 'F9')
                    ingamenav.press_key(0x6F + int(k[1:]))   # (F1 = 0x70: the box opened by the mod, hud.lua)

    def _ingame_feed(self, now=None):
        o = self.s['overlay']
        feed = getattr(self, '_hud_feed', None)
        if not self.ingame_on():
            if feed is not None:                   # (switched off: gone from the game at once, then left alone)
                feed.write([], now)
                feed.close()
                self._hud_feed = None
                for card in self._cards_up():      # (a card the game drew: its window back)
                    card.in_game(False)
            return
        drawn = self.ingame_drawn()
        if drawn != getattr(self, '_ingame_was', None):
            self._ingame_was = drawn
            self._ov_state = None                  # (the windows over the game: standing down, or back)
        self._ingame_actions(drawn)
        if feed is None:
            feed = self._hud_feed = ingamehud.Feed(os.path.join(settings.DIR, ingamehud.FILE),
                                                   lambda p: ghostui.open_kept(p, write=True, binary=True))
        ov = self.overlay.snapshot() if getattr(self, 'overlay', None) else None
        if ov and ov.get('panel'):                 # (the place at the last split: kept on the strip for the run)
            self._hud_pos = ov['panel'].get('pos')
        elif not ov or ov.get('status') not in ('live', 'live_off', 'rec', 'finished'):
            self._hud_pos = None
        if not (ov or {}).get('alert') and not (ov or {}).get('panel') and not self._overlays_allowed(getattr(self, 'last_frame', None)):
            ov = None                              # (as the timer window: only on the dailies' / events' stages)
        if getattr(getattr(self, 'watch', None), 'on', False):
            ov = None                              # (WATCH: its broadcast instead, ig_watch.py; no timer of yours)
        if not o.get('visible', True):             # ("Show the timer" off: none of the timer's displays in the game)
            ov = None
        # in the game's menus: nothing of a stage (the strip: 19 Nov 2026, "symbols for the on-stage are still in the
        # main menu"); a note, the standings and the cards stay. The menus: the mod says no stage is loaded, or the
        # telemetry has none (the mod says the Rally Weekend's mode from the tyre allocation on, before any stage)
        menus = drawn and (self._pulse().in_menus() or not self._on_stage())
        # RANKED's start board (WAIT / GO) only on the stage (the user, 19 Nov 2026: not as soon as the game opens)
        gate = getattr(self, '_lr_gate', None)
        g = gate.snapshot() if gate is not None and self._on_stage() else None
        if g and getattr(getattr(self, 'watch', None), 'on', False):
            g = dict(g, side=True)                 # (watching meanwhile: small, at the side, the broadcast kept clear)
        logo =ingamehud.logo_file(settings.DIR, photos.SERIES_DIR, g.get('series')) if g else None
        view = getattr(self, '_hud_view', None) if self._widget_on('strip') and not menus else None
        brand = ingamehud.brand_file(settings.DIR) if ov else None
        if ov is not None:
            line = ov.get('line')
            ov = dict(ov, mode=getattr(self, '_mode_shown', None), strip=not menus,   # (the game's mode: its own chip)
                      line=line if line and str(line[0]).strip() else self._strip_line(ov))
        nextcard.set_keys(self.ingame_keys())
        feed.write(ingamehud.panels(ov, g, logo, view, self.ingame_place(), o.get('scale', 1.0), getattr(self, '_hud_pos', None),
                                    bool(o.get('inGameClock')), brand, cards=self._ingame_cards()), now)

    def _on_stage(self):
        """A stage is loaded in the game now: the telemetry has one (the game blanks it in its menus, the tyre
        allocation's too)."""
        f = getattr(self, 'last_frame', None)
        return bool(f is not None and getattr(f, 'track', None))

    @staticmethod
    def _strip_line(ov):
        """The strip's second row when the timer has no line under it (an alert says it): the strip next to the red D is
        always two rows (the user, 19 Nov 2026: one row looked bad). Good luck on the start line, good job at the
        finish, else the stage."""
        words = {'ready': _('Good luck!'), 'finished': _('Good job!'), 'dnf': _('Hard luck'), 'invalid': _('Hard luck')}
        said = words.get(ov.get('status'))
        if said:
            return said, SOFT
        return (ov.get('title') or 'ACR DAILY'), FG2

    def _clock_running(self, paused=False):
        """Is a run's stage clock running, not paused (a daily's, a time trial stage's, a league stage's)? paused=True:
        a run going, paused or not."""
        def going(j):
            return bool(j) and j.state == 'running' and (paused or not j.paused)
        run = getattr(self, 'league_run', None)
        return any(going(d.get('judge')) for d in self.dailies.values()) or \
            any(going(t.get('judge')) for t in (getattr(self, 'tt', None) or {}).values()) or \
            bool(run and not run.get('over') and going(run.get('judge')))

    def _game_screen(self):
        """The screen the game fills: (left, top, right, bottom); False: none (a window, minimised); None: can't be told
        (widgets.GameScreen, looked at once a second at most)."""
        gs = getattr(self, 'game_screen', None)
        if gs is None:
            gs = self.game_screen = widgets.GameScreen()
        return gs.rect()

    def _overlays_allowed(self, f):
        """With 'only on a stage' on: the displays (drawn by the game) only while a daily's stage + car are loaded (and
        always while recording, or during / just after a run)."""
        o = self.s['overlay']
        if self.recorder and self.recorder.state == 'recording':
            return True
        if not o.get('onlyOnDaily', True):
            return True
        if self._league_allowed(f):                # a league event's stage (leagueui.py)
            return True
        if self._tt_allowed(f):                    # a time trial stage (ttui.py)
            return True
        for d in self.dailies.values():
            j = d.get('judge')
            if j and (j.state == 'running' or j.approaching):    # (approaching: shows "drive up to the start line")
                return True
            if j and f is not None and f.track and j._right(f):
                return True
        return False

    def _apply_visibility(self, f):
        """The displays allowed now (_overlays_allowed): what the game draws (_ingame_feed) and what the app fetches
        for them (_others_shown). Their windows are never on the screen (0.1.6: widgets.WINDOWS). The next-daily card
        goes once a run's clock runs (DRIVE on it would end the run)."""
        allowed = self._overlays_allowed(f)
        running = self._clock_running()
        if (allowed, running) != self._ov_state:
            self._ov_state = (allowed, running)
            self._ov_allowed = allowed
            self._ov_ok = {k: allowed for k in self.widgets}
            self.overlay.show(False)
            for w in self.widgets.values():
                w.show(False)
        card = getattr(self, 'next_card', None)
        if running and card is not None and card.alive:
            card.close()                           # (a run started with it still up: DRIVE on it would end the run)

    def _widget_buttons(self):
        """The displays' switches on the settings page (settingsui.py), as they are."""
        self._draw_switches()

    def toggle_ghosts(self):
        cfg = ghostui.config(self.s)
        cfg['on'] = not cfg.get('on')
        settings.save(self.s)
        self.ghost_buttons()
        self.poke_game_mod()
        if cfg['on'] and not self.ghost_setup:
            self.open_ghost_setup()

    def want_game_mod(self):
        """The game mod wanted: always (IN_GAME: the displays are drawn by the game, and the mod tells the game's mode;
        ghost cars on or off only says whether it draws them). (Read only: called on the mod's thread.)"""
        return IN_GAME

    def poke_game_mod(self):
        if getattr(self, 'gamemod', None):
            self.gamemod.poke()

    def ghost_cars_on(self):
        return bool(ghostui.config(self.s).get('on'))

    def ghost_buttons(self):
        """Ghost cars on or off, as they are: its switch on the settings page (settingsui.py), the set-up's tick."""
        self._draw_switches()
        if getattr(self, 'ghost_setup', None):
            self.ghost_setup.vars['on'].set(self.ghost_cars_on())

    def open_ghost_setup(self):
        if self.ghost_setup is None:
            self.ghost_setup = ghostui.GhostSetup(self, self.ghostcars)
        self.ghost_setup.show()

    def toggle_overlay(self, on):
        self.s['overlay']['visible'] = on
        settings.save(self.s)
        self._overlay_buttons()

    def _overlay_buttons(self):
        """The timer's settings on the settings page (settingsui.py) as they are: its size, place, keys, the switches."""
        o = self.s['overlay']
        if getattr(self, 'size_l', None) is not None:
            self.size_l.configure(text='%d %%' % round(100 * float(o.get('scale') or 1.0)))
        for key, b in (getattr(self, 'place_bs', None) or {}).items():      # (the displays in the game: their place)
            if b.winfo_exists():
                self._btn_style(b, key == self.ingame_place())
        keys = self.ingame_keys()
        for action, var in (getattr(self, 'key_vars', None) or {}).items():  # (the cards' keys in the game: a swap shows)
            if var.get() != keys[action]:
                var.set(keys[action])
        self._draw_switches()
        self._draw_auto_switch()

    # -------------------------------------------------------------- AUTO: one switch for every DRIVE
    AUTO_SW = (34, 18)                             # a switch's size at 96 dpi (width, height)

    def _build_auto_switch(self, parent, bg=BG):
        """AUTO on the settings page, for everything: after any DRIVE (a daily, a league event, a 1V1, a cup match) the
        app goes on through the game's menus to the Service Park (autodrive.py). A switch: red with the knob right when
        on. -> its frame (not packed)."""
        f = tk.Frame(parent, bg=bg, cursor='hand2')
        self.auto_lbl = tk.Label(f, text=_('AUTO'), bg=bg, fg=FG2, font=(FONT_C, 11), cursor='hand2')
        self.auto_lbl.pack(side='left', padx=(0, 6))
        k = self.root.winfo_fpixels('1i') / 96
        self.auto_sw = tk.Canvas(f, width=round(self.AUTO_SW[0] * k), height=round(self.AUTO_SW[1] * k), bg=bg,
                                 highlightthickness=0, cursor='hand2')
        self.auto_sw.pack(side='left')
        for w in (f, self.auto_lbl, self.auto_sw):
            w.bind('<Button-1>', lambda _e: self.toggle_auto_drive())
            w.bind('<Enter>', lambda _e: self._draw_auto_switch(hover=True))
            w.bind('<Leave>', lambda _e: self._draw_auto_switch())
        self._draw_auto_switch()
        return f

    def _draw_auto_switch(self, pos=None, hover=False):
        """AUTO's switch as the setting is (or its knob at pos, 0 = off .. 1 = on, while it slides)."""
        cv = getattr(self, 'auto_sw', None)
        if cv is None:
            return
        on = bool(self.s.get('autoDrive', False))
        self._draw_switch(cv, on, pos, hover)
        self.auto_lbl.configure(fg=WHITE if on else FG2)

    @staticmethod
    def _draw_switch(cv, on, pos=None, hover=False):
        """A switch: a rounded track, red with the knob on the right when on (or the knob at pos, 0 .. 1, as it
        slides); white edge under the mouse."""
        p = (1.0 if on else 0.0) if pos is None else pos
        w, h = int(cv.cget('width')), int(cv.cget('height'))
        r, pad = h / 2, max(2, round(h / 6))
        track = ACC if p >= 0.5 else BG
        edge = WHITE if hover else (ACC if p >= 0.5 else LINE2)
        cv.delete('all')
        cv.create_oval(1, 1, h - 1, h - 1, fill=track, outline=edge)              # a rounded track: two ends and the middle
        cv.create_oval(w - h + 1, 1, w - 1, h - 1, fill=track, outline=edge)
        cv.create_rectangle(r, 1, w - r, h - 1, fill=track, outline='')
        cv.create_line(r, 1, w - r, 1, fill=edge)
        cv.create_line(r, h - 1, w - r, h - 1, fill=edge)
        d = h - 2 * pad                                                             # the knob
        x = pad + p * (w - 2 * pad - d)
        cv.create_oval(x, pad, x + d, pad + d, fill=WHITE if (p >= 0.5 or hover) else FG2, outline='')

    def _slide_auto_switch(self, on, steps=6, every_ms=16):
        """AUTO's knob slides across to the new setting."""
        def step(i):
            t = i / steps
            self._draw_auto_switch(pos=t if on else 1 - t)
            if i < steps:
                self.root.after(every_ms, step, i + 1)
        step(1)

    def _slide_switch(self, cv, on, steps=6, every_ms=16):
        """A settings switch's knob slides across to the new setting."""
        def step(i):
            if cv.winfo_exists():
                self._draw_switch(cv, on, pos=i / steps if on else 1 - i / steps)
                if i < steps:
                    self.root.after(every_ms, step, i + 1)
        step(1)

    def open_site(self):
        if self.api.configured:
            webbrowser.open(self.api.site + '/')

    def open_shop(self):
        """The balance clicked: the shop on the website's credits page (with credits on and the driver signed in)."""
        c = self.credits or {}
        if self.api.configured and c.get('enabled') and c.get('signedIn'):
            webbrowser.open(self.api.site + '/credits#shop')

    def drive_click(self, slot, confirm=True, agreed=False):
        """Set the daily up in the game's save, then start the game: it opens on the daily's stage, car and conditions.
        confirm=False: no 'restart the game?' question (the next-daily card's button already says it restarts);
        agreed: nor the stake's (its button said that too: _card_drive)."""
        d = self.dailies.get(slot)
        if not d:
            self.retry_now()                       # (the card's button reads RETRY while there is no daily: _show_active)
            return
        ch = d['ch']
        if getattr(self, '_restarting', False):
            if self._restarting == slot:       # this daily's button reads CANCEL while the game closes
                self._cancel_restart()
            return
        if self._drive_wait:                       # a stake (or the credits) on its way: DRIVE goes on then
            self.sub_l.configure(text=self._drive_wait)
            return
        if any(x.get('judge') and x['judge'].state == 'running' for x in self.dailies.values()) or self._tt_running():
            messagebox.showinfo('ACR Daily', _('Finish or leave the stage you are on first.'))
            return
        if self._waiting_text():                  # (the set-up closes the game before it saves that run's time)
            messagebox.showinfo('ACR Daily', self._waiting_text())
            return
        if self.community_missing(ch, 'SS%d' % slot):   # a community track not installed yet (communityui.py)
            return
        told = self._league_before_daily(is_weekend(ch))   # a league stage or rally in progress (leagueui.py)
        if told is None:
            return
        # the game only reads the set-up when it starts (and writes its save when it exits), so: close it the
        # normal way, set the daily up, start it again. One click, no need to quit by hand.
        if saveslot.game_running() and confirm and not told and not messagebox.askyesno(
                'ACR Daily', _('The game is running. ACR Daily will restart it with SS%d (%s · %s · %s).\n\nGo?') % (slot, stage_name(ch), ch['car'], conditions(ch))):
            return
        # every question answered: the stake last (the wager daily, credits), then nothing more is asked
        if self._wager_first(slot, lambda: self._drive_go(slot), agreed):
            self._drive_go(slot)

    def _drive_go(self, slot):
        """DRIVE once its questions are answered: set it up in the running game (0.2: ingamedrive.py), or restart the
        game into the daily, or set it up and start the game."""
        if saveslot.game_running():
            if self._drive_in_game(slot):
                return
            self._restart_into(slot)
        else:
            self._setup_and_launch(slot)

    def _drive_in_game(self, slot):
        """The daily set up in the running game by the mod, and the game on to the Service Park: no restart
        (ingamedrive.py). -> False when it can't be tried (the old way then)."""
        d = self.dailies.get(slot)
        if not d or not is_weekend(d['ch']) or not ingamedrive.ready(self):
            return False
        ch = d['ch']
        try:
            setup = ingamedrive.setup_of(ingamedrive.daily_stages(ch), ch['carId'], ch.get('weekend'))
            from . import gear
            setup.update(gear.for_daily(self.s, ch['carId']))     # (the livery picked: gear.py; the tyres the game's)
        except saveslot.SaveError:
            return False

        def ok():
            d['ingame_setup'] = setup                  # (the finish checks the stage driven against it: _await_official)
            self.drive_target = 'daily'                # the game's frames are judged for the dailies again
            self.active = slot
            self._show_active()
            path = _('At the Service Park: START STAGE.')
            if not self._driven(slot) and not COMMIT_REQUIRED:
                path = COUNTS_HINT + ' ' + path
            self.sub_l.configure(text=(_('SS%d set up in the game.') % slot) + ' ' + path)
            self.commit_offer(slot)
        self.sub_l.configure(text=_('Setting up SS%d in the game...') % slot)
        self.ingame_drive(setup, ok, 'SS%d' % slot, lambda: self._restart_into(slot))
        return True

    def ingame_drive(self, setup, ok, what, old_way, offer_restart=True):
        """Send a DRIVE to the running game (ingamedrive.py). If it can't be done there, why is said and the old way
        offered (close the game, set it up in the save, start it again): in the game when DRIVE was pressed there,
        else in the window."""
        ig = self.ingame_app
        from_game = ig.shown

        def fail(why):
            words = _('Not set up in the game: %s.') % ingamedrive.why_words(why)
            waiting.note('in-game DRIVE %s failed: %s' % (what, why))
            self.sub_l.configure(text=words)
            if not offer_restart:                  # (CONTINUE: its old way is the game's own RESUME, no restart)
                old_way()
            elif from_game:
                ig.ask(what, [words, _('ACR Daily can close the game, set it up and start it again instead.')],
                       _('RESTART THE GAME'), old_way, safe=True, expires_s=120)
                ig.ask_open = True                     # (the pages back over the game's menu, the question on them)
            elif messagebox.askyesno('ACR Daily', words + '\n\n' + _('Close the game, set it up and start it again?')):
                old_way()
        ig.drive(setup, ok, fail)

    def _restart_into(self, slot):
        """Close the game (WM_CLOSE, like its X button), wait for it to exit and save, then set up + start.
        While it waits, that daily's DRIVE button reads CANCEL and takes the app back (_cancel_restart)."""
        self._restarting = slot
        self.cards[slot]['drive'].configure(text=_('CANCEL  ✕'))
        from .communityui import quit_game
        quit_game(self)                       # (the mod asked to quit too: the close message alone opened the
        t0 = time.monotonic()                 # game's own "quit?" question, 24 Nov 2026)

        def wait():
            if not saveslot.game_running():
                self.sub_l.configure(text=_('Game closed. Setting up the daily...'))
                self._restart_job = self.root.after(4000, lambda: (self._restart_done(), self._setup_and_launch(slot)))
                return
            waited = time.monotonic() - t0
            if waited > 120:
                self._restart_done()
                self.sub_l.configure(text=_('The game did not close. Quit it from its menu, then click DRIVE again.') +
                                     self._stake_stands(slot))
                return
            if 8 < waited < 9 or 30 < waited < 31:
                quit_game(self, hard=waited > 30)   # ask again (it may have been on a loading screen); in its menus: ended
            self.sub_l.configure(text=_('Closing the game... (%d s) Confirm if it asks. CANCEL to stop.') % waited)
            self._restart_job = self.root.after(1000, wait)
        self._restart_job = self.root.after(1000, wait)

    def _restart_done(self):
        slot, self._restarting = self._restarting, False
        if slot in self.cards:
            self.cards[slot]['drive'].configure(text=_('DRIVE  ›'))

    def _cancel_restart(self):
        """Stop waiting for the game to close (it may still ask its player whether to quit)."""
        job = getattr(self, '_restart_job', None)
        if job:
            self.root.after_cancel(job)
        self._restart_job = None
        slot = self._restarting
        self._restart_done()
        self.sub_l.configure(text=_('Cancelled. Nothing changed.') +
                             self._stake_stands(slot))

    def _setup_and_launch(self, slot):
        d = self.dailies.get(slot)
        if not d:
            return
        ch = d['ch']
        weekend = is_weekend(ch)
        if weekend and not self._league_park_for_daily():    # a league rally in the game: set aside first (asked)
            if self._stake_stands(slot):
                self.sub_l.configure(text=_('Not set up.') + self._stake_stands(slot))
            return
        d['ingame_setup'] = None                   # (set up in the save: the save's check, _official_found)
        try:
            (rallyweekend if weekend else saveslot).write_daily(ch)
        except saveslot.SaveError as e:
            messagebox.showwarning('ACR Daily', _('%s\n\nSet it up by hand: %s · %s · %s%s') % (e, ch['track'], ch['car'], conditions(ch),
                                                                                      self._stake_stands(slot, '\n\n')))
            return
        self.drive_target = 'daily'                # the game's frames are judged for the dailies again
        self.active = slot
        self._show_active()
        if weekend:
            path = _('In the game: Racing › Rally › Rally Weekend › START RALLY › J › CONFIRM › Start Stage.')
        else:
            path = _('In the game: Racing › Rally › Single Rally Stage › START RACE › Start Stage.')
        if not self._driven(slot) and not COMMIT_REQUIRED:   # (the first start counts: the most DNFs are restarts in its
            path = COUNTS_HINT + ' ' + path                    # first minute; with the commit card, it says the rules)
        self.sub_l.configure(text=(_('Starting the game...') + ' ') + path)
        self.commit_offer(slot)                    # (commit now, before the game is even up: or on the start line)
        try:
            saveslot.launch_game(set_up=True)
        except OSError:
            self.sub_l.configure(text=(_('Daily set up. Start the game from Steam.') + ' ') + path)
        if self.s.get('autoDrive'):
            if getattr(self, 'auto', None):
                self.auto.cancel()
            self.auto = autodrive.AutoDrive(lambda t: ui(self.root, self.sub_l.configure, {'text': t}),
                                            'weekend' if weekend else 'single').start()

    def restore_click(self):
        if not messagebox.askyesno('ACR Daily', _('Put back the game save from before the last daily set-up?')):
            return
        try:
            messagebox.showinfo('ACR Daily', saveslot.restore_latest())
        except (saveslot.SaveError, OSError) as e:
            messagebox.showwarning('ACR Daily', str(e))

    def record_click(self):
        self.recorder = RouteRecorder()

    def upload_click(self):
        rec = self.recorder.saved if self.recorder else None
        if not rec:
            messagebox.showinfo('ACR Daily', _('Record a route first.'))
            return

        def go():
            try:
                self.api.upload_route(rec['track'], rec['points'])
                ui(self.root, self.adm_l.configure, {'text': _('Uploaded %s') % rec['track']})
            except ApiError as e:
                ui(self.root, self.adm_l.configure, {'text': _('Upload failed: %s') % e})
        threading.Thread(target=go, daemon=True).start()

    def _place_window(self):
        """The window at its size from Settings (fixed: WINDOW_SIZES at the screen's scale, not resizable), where the
        user left it; 'free' (resizable): as big as the user left it, at first 16:9 (WIN_W x WIN_H at the screen's scale),
        never smaller than MIN_W x MIN_H (or the screen). In the middle of the screen at first; never bigger than the
        screen it is on."""
        self.root.update_idletasks()
        saved = self.s.get('window') if isinstance(self.s.get('window'), dict) else {}
        at = ((saved['x'] + int(saved.get('w') or 0) // 2, saved['y'] + int(saved.get('h') or 0) // 2)
              if isinstance(saved.get('x'), int) and isinstance(saved.get('y'), int) else (None, None))
        area = work_area(*at) or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48)
        k = self.root.winfo_fpixels('1i') / 96
        key = self.s.get('windowSize') or WINDOW_DEFAULT
        if key != 'free':                            # (a size that doesn't fit this screen: on one it fits)
            moved = area_for(key, k, area, work_areas())
            if moved != area:
                area, saved = moved, {kk: v for kk, v in saved.items() if kk not in ('x', 'y')}
        aw, ah = area[2] - area[0], area[3] - area[1] - 40          # 40: the title bar
        fixed = fixed_size(key, k, (aw, ah))
        if fixed:                                    # (Settings › Window size: this size, not resizable)
            try:
                if self.root.state() == 'zoomed':
                    self.root.state('normal')
            except tk.TclError:
                pass
            width, height = fixed
            self.root.resizable(False, False)
            self.root.minsize(width, height)
            self.root.maxsize(width, height)
            _w, _h, x, y = window_size(dict(saved, w=width, h=height), fixed, fixed, area)
        else:                                        # (resizable: as the user left it)
            self.root.resizable(True, True)
            self.root.maxsize(max(aw, self.root.winfo_screenwidth()) * 4, max(ah, self.root.winfo_screenheight()) * 4)
            min_w, min_h = min(aw, round(MIN_W * k)), min(ah, round(MIN_H * k))
            self.root.minsize(min_w, min_h)
            width, height, x, y = window_size(self.s.get('window'), (round(WIN_W * k), round(WIN_H * k)), (min_w, min_h), area)
        if not (isinstance(x, int) and isinstance(y, int) and on_screen(x, y)):
            x, y = area[0] + (aw - width) // 2, area[1] + max(0, (ah - height) // 2)
        self.root.geometry('%dx%d+%d+%d' % (width, height, x, y))
        self._layout(width)                          # (laid out for its width before it is first seen)

    # -------------------------------------------------------------- narrow windows
    def _layout_soon(self, e):
        """(the window resized) _layout once Tk is idle (a drag sends many sizes)."""
        if e.widget is self.root and self._layout_job is None:
            self._layout_job = self.root.after_idle(self._layout)

    def _layout(self, width=None):
        """The layout for the window's width: wide (as RaceRoom's: the driver's panel on the left, cards side by side);
        narrower than NARROW_W, the header in two rows and the driver's panel across the top; narrower than STACK_W (a
        screen stood on its end), the cards and the pages' panels one under the other."""
        self._layout_job = None
        width = width or self.root.winfo_width()
        if width <= 1:                               # (not on screen yet)
            return
        k = self.root.winfo_fpixels('1i') / 96
        if self._nav_extra is None:                  # (the language's words: measured once, in the nav's font)
            try:
                f = tkfont.Font(root=self.root, font=(FONT_C, 12))
                self._nav_extra = nav_extra(lambda t: f.measure(t) / k)
            except tk.TclError:
                self._nav_extra = 0
        narrow, stack = layout_for(width, k, self._nav_extra)
        if (narrow, stack) == (self.layout_narrow, self.layout_stack):
            return
        restack = stack != self.layout_stack
        self.layout_narrow, self.layout_stack = narrow, stack
        self._header_layout()                        # (tabsui.py)
        self._pack_side()
        self._driver_layout()                        # (tabsui.py)
        if restack:
            for row in (getattr(self, '_daily_row', None), getattr(self, '_tt_row', None)):
                if row is not None and row.frame.winfo_exists():
                    row.set_cols(1 if stack else row.wide)
            self._settings_layout()                  # (settingsui.py)
            if self.league_view:
                self._render_leagues()
            if self.profile_view:
                self._render_profile()
        self._cards_resized()

    def _pack_side(self):
        """The driver's panel: on the left of the view (a wide window) or across its top (a narrow one); none on HOME
        nor COMMUNITY (the whole width)."""
        side = getattr(self, '_side', None)
        if side is None:
            return
        side.pack_forget()
        if self.home_view or getattr(self, 'community_view', False):
            return
        if self.layout_narrow:
            side.pack_propagate(True)                # (as tall as the card in it)
            side.pack(side='top', fill='x', padx=20, pady=(0, 12), before=self._main)
        else:                                        # (its own width again: the strip's was kept otherwise)
            side.configure(width=round(SIDE_W * self.root.winfo_fpixels('1i') / 96))
            side.pack_propagate(False)
            side.pack(side='left', fill='y', padx=(20, 0), before=self._main)

    def window_room(self):
        """(screen scale k, (width, height) the screen the window is on has for it, less the title bar)."""
        self.root.update_idletasks()
        cx, cy = self.root.winfo_x() + self.root.winfo_width() // 2, self.root.winfo_y() + self.root.winfo_height() // 2
        area = work_area(cx, cy) or (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48)
        return self.root.winfo_fpixels('1i') / 96, (area[2] - area[0], area[3] - area[1] - 40)

    def set_window_size(self, key):
        """Settings › Window size: a fixed size (WINDOW_SIZES) or 'free' (resizable), kept and put on at once."""
        self._save_window()                          # (where it is now: it stays there)
        self.s['windowSize'] = key
        settings.save(self.s)
        self._place_window()

    def _save_window(self):
        if self.root.state() != 'normal':      # minimised or maximised: keep the last normal size
            return
        if getattr(getattr(self, 'launcher', None), 'on', False):
            return
        self.s['window'] = {'w': self.root.winfo_width(), 'h': self.root.winfo_height(),
                            'x': self.root.winfo_x(), 'y': self.root.winfo_y(), 'layout': LAYOUT}
        settings.save(self.s)

    def quit(self, ask=True):
        if ask and self._waiting_text() and not messagebox.askyesno(
                'ACR Daily', (_("Your last run is still waiting for the game's official time. It will be picked up next time.") + ' ')
                             + waiting.HINT + ('\n\n' + _('Close ACR Daily?'))):
            return
        try:
            self._replay_close()                   # (a run under way kept as it is)
        except Exception:
            pass
        try:
            self._save_window()
        except (tk.TclError, OSError):
            pass
        self.shm.close()
        if getattr(self, 'ghostcars', None):
            self.ghostcars.close()
        if self.notifier is not None:
            self.notifier.close()                     # (its icon in the notification area)
        self.root.destroy()

    # -------------------------------------------------------------- network

    def refresh_challenge(self):
        if not self.api.configured:
            self.net_msg = _('No server set (see SETUP.md)')
            return

        def go():
            try:
                chs = self.api.today()
                ui(self.root, self._set_challenges, chs)
            except ApiError as e:
                ui(self.root, self._challenges_failed, e)
        self._fetching = True
        if not self.dailies and getattr(self, 'cards', None):
            self._show_active()                    # (RETRY pressed: the cards say they are trying)
        threading.Thread(target=go, daemon=True).start()

    def _challenges_failed(self, e):
        """Today's dailies could not be fetched: the cards say why in words, with RETRY (they said LOADING... for ever,
        the only sign a raw system error in small grey in the footer: a UI review, Nov 2026), and it is tried again in
        RETRY_S on its own."""
        self._fetching = False
        self.net_msg = offline_words(e)
        if getattr(e, 'why', ''):
            waiting.note('today\'s dailies: %s' % e.why)
        job = getattr(self, '_retry_job', None)
        if job:
            self.root.after_cancel(job)
        self._retry_job = self.root.after(RETRY_S * 1000, self._retry_auto)
        self._show_active()

    def _retry_auto(self):
        self._retry_job = None
        self.refresh_challenge()

    def retry_now(self):
        """RETRY on a card (no dailies yet): fetch them now."""
        job = getattr(self, '_retry_job', None)
        if job:
            self.root.after_cancel(job)
            self._retry_job = None
        if not getattr(self, '_fetching', False):
            self.refresh_challenge()

    def _set_challenges(self, chs):
        self.net_msg = ''
        self._fetching = False
        days = {d['ch'].get('date') for d in self.dailies.values()}
        if days and any(ch.get('date') not in days for ch in chs):
            self.refresh_credits()                 # a new day: its bonus, and its wager (yesterday's stake is not on it)
        for ch in chs:
            slot = ch.get('slot', 1)
            d = self.dailies.get(slot)
            if d and d['ch'].get('id') == ch.get('id'):
                # the same daily: take the server's latest details (a corrected car or stage id) - the
                # route object stays, the judge holds it
                d['ch'].update({k: v for k, v in ch.items() if k != 'route'})
                continue
            if d and d.get('judge') and d['judge'].state == 'running':
                self.root.after(5000, lambda: self._set_challenges(chs))   # never swap a daily mid-run
                return
            judge = Judge(ch) if ch.get('route') else None
            self.dailies[slot] = {'ch': ch, 'judge': judge, 'board': None, 'ghost_for': None, 'ghost_name': None,
                                  'ghosts': GhostSet(judge.route, judge.penalty_ms) if judge else None,
                                  'ghost_loading': set(), 'live': []}
        for slot in list(self.dailies):
            if slot not in {c.get('slot', 1) for c in chs}:
                del self.dailies[slot]
        self._wager_marks()
        self._show_active()
        self.refresh_board()

    def _card_base(self):
        """How tall cards side by side are at least: CARD_H, or most of the view on a big window (the timing sheet that
        shared it is gone, 0.1.6); a third each, the cards one under the other (a narrow window)."""
        return max(round(CARD_H * self.root.winfo_fpixels('1i') / 96),
                   int(self._view_room_h() * (0.33 if self.layout_stack else 0.58)))

    def _view_room_h(self):
        """How tall the view is on screen: the window's room for it (the scrolling frame's, less the driver's panel when
        it is across the top), not how tall what it holds makes it: cards sized from that would make it taller still."""
        vs, main = getattr(self, '_view_scroll', None), getattr(self, '_main', None)
        if vs is None:
            return main.winfo_height() if main else 0
        h = vs.cv.winfo_height()
        side = getattr(self, '_side', None)
        if side is not None and self.layout_narrow and side.winfo_manager():
            h -= side.winfo_reqheight() + round(12 * self.root.winfo_fpixels('1i') / 96)
        return max(0, h)

    def _cards_resized(self):
        for row in (getattr(self, '_daily_row', None), getattr(self, '_tt_row', None)):
            if row is not None and row.frame.winfo_exists() and row.base != self._card_base():
                row.base = self._card_base()
                row.later()

    def _card_spec(self, slot):
        """A daily's card (tiles.py): SS1 and its rally, its length and surface, the stage's name and road, the car and
        the conditions; filled red while it is the one on screen."""
        d = self.dailies.get(slot)
        if not d:
            if self.net_msg and not getattr(self, '_fetching', False):     # (it failed: say so, and RETRY)
                return {'lock': ('SS%d' % slot, ''), 'title': _("CAN'T REACH ACR DAILY"),
                        'lines': [(self.net_msg, 'info'), (_('Trying again every %d s.') % RETRY_S, 'muted')]}
            return {'lock': ('SS%d' % slot, ''), 'title': _('LOADING…'), 'button': False}
        ch, j = d['ch'], d.get('judge')
        km = '%.1f KM' % (ch['lengthM'] / 1000) if ch.get('lengthM') else ''
        return {'active': slot == self.active, 'lock': ('SS%d' % slot, i18n.data(ch.get('rally') or '').upper()),
                'photo': photos.for_rally(ch.get('rally')), 'bottom': True,
                'chips': [x for x in (km, i18n.data(ch.get('surface') or '').upper()) if x], 'title': stage_name(ch).upper(),
                'lines': [(ch.get('car', '') + ('  ·  %s' % ch['carClass'] if ch.get('carClass') else ''), 'sub'),
                          (' · '.join(x for x in (conditions(ch), set_by(ch)) if x), 'info')],
                'road': j.route.points if j else ch.get('route'),
                'below': [[x for x in ((getattr(self, 'cards', None) or {}).get(slot, {}).get('timing'),) if x]]}

    def _show_active(self):
        for slot, c in self.cards.items():
            want = _('DRIVE  ›') if slot in self.dailies else _('RETRY  ↻')
            if slot not in self.dailies and c['drive'].cget('text') != want:
                c['drive'].configure(text=want)
            elif slot in self.dailies and c['drive'].cget('text') == _('RETRY  ↻'):
                c['drive'].configure(text=want)
            c['tile'].render(self._card_spec(slot))
        if getattr(self, '_daily_row', None) is not None:     # (side by side: as tall as each other)
            self._daily_row.even()

    def refresh_board(self):
        if not self.api.configured:
            return
        for slot, d in list(self.dailies.items()):
            def go(slot=slot, date=d['ch'].get('date')):
                try:
                    b = self.api.leaderboard(date, slot)
                    ui(self.root, self._set_board, slot, b)
                except ApiError as e:
                    self.net_msg = offline_words(e)
            threading.Thread(target=go, daemon=True).start()

    def _set_board(self, slot, b):
        d = self.dailies.get(slot)
        if not d:
            return
        d['board'] = b
        # live gap: against this daily's #1
        entries = [e for e in (b or {}).get('entries', []) if e.get('totalMs') is not None]
        # ghosts for the displays: the top runs and your own first run
        me = self.s.get('steamId')
        gs = d.get('ghosts')
        if gs is not None:
            for e in entries[:6] + [e for e in entries if e.get('steamId') == me]:
                rid = e['runId']
                if rid in gs.runs or rid in d['ghost_loading']:
                    continue
                d['ghost_loading'].add(rid)

                def load(rid=rid, name=e['name']):
                    try:
                        tr = self.api.run_trace(rid)
                        ui(self.root, gs.add, rid, name, tr.get('trace'))
                    except ApiError:
                        pass
                    finally:
                        d['ghost_loading'].discard(rid)
                threading.Thread(target=load, daemon=True).start()
        target = entries[0] if entries else None
        if target and d.get('judge') and target['runId'] != d['ghost_for']:
            d['ghost_for'] = target['runId']

            def go():
                try:
                    tr = self.api.run_trace(target['runId'])
                    ui(self.root, self._set_ghost, slot, tr, target)
                except ApiError:
                    d['ghost_for'] = None
            threading.Thread(target=go, daemon=True).start()

    def _pack_view(self, box):
        """A view's cards back in their place; the events' as tall as the window (the RALLIES list scrolls in it,
        browserui.py)."""
        if box is getattr(self, 'league_box', None):
            box.pack(fill='both', expand=True, before=self._view_end)
        else:
            box.pack(fill='x', before=self._view_end)

    def _set_ghost(self, slot, tr, target):
        d = self.dailies.get(slot)
        if d and d.get('judge') and tr and tr.get('trace'):
            d['judge'].set_ghost(tr['trace'])
            d['ghost_name'] = shown_name(target)

    def check_update(self):
        """(thread) Ask the server for the latest version; tick() shows the UPDATE bar. A test build (four parts:
        0.1.5.4, for the testers) also looks on GitHub for a newer test build (updater.latest_test_build): each change of
        the app on main makes one (.github/workflows/dev.yml), so testers have the work for the next release as it lands."""
        def ver(x):
            return tuple(int(p) for p in str(x).split('.') if p.isdigit())
        offer = None
        forced = False
        try:
            v = self.api.version()
            if ver(v.get('latest', '0')) > ver(__version__) and v.get('url'):
                url = v['url'] if v['url'].startswith('http') else self.api.base + v['url']
                offer = {'version': v['latest'], 'url': url}
                # below the oldest version the server takes (from its day on, UTC): updated at once, no click (the
                # user, 26 Nov 2026); a test build counts by its first three parts (0.2.2.5 is 0.2.2)
                low = v.get('min')
                since = v.get('minFrom')
                today = time.strftime('%Y-%m-%d', time.gmtime())
                forced = bool(low) and ver(__version__)[:3] < ver(low) and (not since or str(since) <= today)
        except ApiError:
            pass
        if updater.is_test_build(__version__):
            try:
                t = updater.latest_test_build()
            except (OSError, ValueError):
                t = None
            if t and ver(t[0]) > ver(__version__) and (offer is None or ver(t[0]) > ver(offer['version'])):
                offer = {'version': t[0], 'url': t[1]}
        if offer:
            if forced:
                offer['forced'] = True
            self.update_info = offer

    def _driving(self):
        run = self.league_run
        return any(d.get('judge') and d['judge'].state == 'running' for d in self.dailies.values()) or self._tt_running() or \
            bool(self.recorder and self.recorder.state == 'recording') or \
            bool(run and not run.get('over') and run['judge'].state == 'running') or bool(self._waiting_text())

    def _game_watch_on(self):
        """The game watched while a finished run waits for its official result (gamewatch.py: for the report if the
        game loses it), else None (and the last watch let go)."""
        if self._official_pending() or getattr(self, '_league_restored', None):
            if self.game_watch is None:
                self.game_watch = gamewatch.GameWatch()
            return self.game_watch
        if self.game_watch is not None:
            self.game_watch.close()
            self.game_watch = None
        return None

    def _official_pending(self):
        """Is a finished run (a daily, a time trial stage, a league stage) waiting for the game to save its official
        time? (The timer window says what saves it: OFFICIAL_ALERT.)"""
        run = self.league_run
        return any(not a.get('practice') for a in self.awaiting) or bool(run and not run.get('over') and run.get('wait'))

    def _saving(self):
        """While a finished run waits for the game's official time (a daily's, a time trial stage's, a league stage's):
        'wait' while the game hasn't written its save since the finish (the driver still on its results screen), else
        how far the save has settled, 0 to 1 (the app reads it SETTLE_S after the game last wrote it: saveslot.SaveWatch;
        then the time is in). None: nothing waits."""
        waits = [(a['until'] - OFFICIAL_WAIT_S, getattr(self, '_official_watch', None))
                 for a in self.awaiting if not a.get('practice') and a.get('until')]
        run = getattr(self, 'league_run', None)
        items = [a for a in self.awaiting if not a.get('practice')]
        if run and not run.get('over') and run.get('wait'):          # (leagueui.py: the same 30 minutes at most)
            w = run['wait']
            waits.append((w.get('until', 0) - OFFICIAL_WAIT_S, w.get('watch')))
            items.append(w)
        if not waits:
            return None
        # a run sent at the finish line (set up by ACR DAILY in the running game, its penalties read there): "sending"
        # filling up from the line, FINISH_SETTLE_S, then sent (the user, 24 Nov 2026: the window at the finish, not
        # once the car has stopped and the results are left)
        fin = [a['live']['at'] for a in items if (a.get('live') or {}).get('at') and a.get('ingameChanged') == []
               and not a.get('other')]
        if fin:
            self._sending_now = True
            return min(1.0, max(0.0, (time.time() - max(fin)) / FINISH_SETTLE_S))
        self._sending_now = False
        best = None
        for since, watch in waits:
            seen = getattr(watch, 'seen', None)
            if not seen or seen == getattr(watch, 'done', None):
                continue                                  # nothing new written (or read already, not that result)
            written = seen[0] / 1e9
            if written <= since:
                continue                                  # written before the finish: the results screen is still up
            frac = (time.time() - written) / saveslot.SETTLE_S
            best = frac if best is None else max(best, frac)
        return 'wait' if best is None else min(1.0, max(0.0, best))

    def _next_line(self):
        """The timer's line under a finished run waiting for its official time: what saves it, or that it is saving."""
        if isinstance(self._saving(), float):
            return _('Official time next: the game is saving it')
        return _('Official time next: go on from the results screen')

    def _render_saving(self):
        """The timer window while a finished run's official time is on its way: what saves it with a piece going across
        (the results screen still up), then "Saving your official time…" filling up, then saved, in green."""
        at = getattr(self, '_saved_at', None)
        if at is not None and time.monotonic() - at < SAVED_SHOW_S:
            self.overlay.set_alert(_('Official time saved'), kind='good')
            self.overlay.set_progress('done', 1.0, GOOD)
            return
        s = self._saving()
        if s is None:
            loud = self._rules_alert()            # (on a daily's start line: what makes the run count, RULES_LOUD)
            if loud:
                self.overlay.set_alert(*loud)
            else:
                self.overlay.set_alert('')
            self.overlay.set_progress(None)
        elif s == 'wait':
            self.overlay.set_alert(OFFICIAL_HEAD, OFFICIAL_ALERT, 'warn')
            self.overlay.set_progress('wait', colour=SLOW)
        else:
            self.overlay.set_alert(_('Sending your time…') if getattr(self, '_sending_now', False) else SAVING_ALERT,
                                   kind='info')
            self.overlay.set_progress('saving', s, ACC)

    def _waiting_text(self):
        """While a finished run waits for the game's official time: why DRIVE waits too (it would close the game
        before the game has saved that time), else None."""
        if self._official_pending() or self._league_restored:
            return ((_("Your last run is waiting for the game's official time.") + ' ') + waiting.HINT + _('\n\nDRIVE works again '
                    'once it is in.'))
        return None

    def _game_open_cached(self):
        """saveslot.game_running(), asked at most every 5 s (the tick runs many times a second)."""
        now = time.monotonic()
        if now - getattr(self, '_game_open_at', -1e9) >= 5.0:
            self._game_open_at = now
            try:
                self._game_open = saveslot.game_running()
            except Exception:
                self._game_open = False
        return self._game_open

    def _render_update(self):
        info = self.update_info
        if not info:
            return
        # too old for the server: updated at once, no click, its screen over the app until the new one starts
        # (updatescreen.py). Never while a run is on, nor with the game open (the app's window would come up over the
        # full-screen game: that crashed the game with frame generation on, 24 Nov 2026): then once the game is closed.
        if info.get('forced') and updater.can_self_update():
            if not self.update_busy and not self._driving() and not getattr(self, '_forced_tried', False) and \
                    not self._game_open_cached():
                self._forced_tried = True                  # (once: a failed one leaves the UPDATE bar, as before)
                from . import updatescreen
                self._update_screen = updatescreen.show(self, info['version'])
                self.do_update()
            scr = getattr(self, '_update_screen', None)
            if scr is not None:
                scr.set(self.update_busy)
                if not self.update_busy:                   # (failed: its message box says why)
                    scr.close()
                    self._update_screen = None
        if not self.upd.winfo_ismapped():
            self.upd.pack(side='right', padx=(0, 16), before=self.state_l)
        if self.update_busy:
            text = self.update_busy
        elif self._driving():
            text = _('NEW VERSION %s  ·  UPDATE AFTER THIS RUN') % info['version']
        else:
            text = _('UPDATE TO %s  ›') % info['version']
        if self.upd.cget('text') != text:
            self.upd.configure(text=text, cursor='watch' if self.update_busy or self._driving() else 'hand2')

    def do_update(self):
        info = self.update_info
        if not info and getattr(self, '_whats_new', False):   # just updated: the bar opens what's new (whatsnew.py)
            whatsnew.reopen(self)
            return
        if not info or self.update_busy or self._driving():
            return
        if not updater.can_self_update():      # running from source: get it from the website
            webbrowser.open(info['url'])
            return
        if self._pending_update and os.path.exists(self._pending_update):   # downloaded during a run
            self._install_update(self._pending_update)
            return
        self.update_busy = _('DOWNLOADING %s ...') % info['version']

        def go():
            try:
                fetch = updater.download_setup if updater.installed() else updater.download   # (installed: its setup)
                new = fetch(info['url'], progress=lambda p: setattr(
                    self, 'update_busy', _('DOWNLOADING %s  ·  %d %%') % (info['version'], p * 100)))
                self.update_busy = _('INSTALLING %s ...') % info['version']
                self.root.after(0, lambda: self._install_update(new))
            except updater.UpdateError as e:
                said = _('Update failed: %s') % e     # (Python drops e as the except block ends: the popup comes later)
                self.update_busy = ''
                self.root.after(0, lambda: messagebox.showerror('ACR Daily', said))
        threading.Thread(target=go, daemon=True).start()

    def _install_update(self, new):
        if self._driving():                    # a run started while downloading: install after it
            self.update_busy = ''
            self._pending_update = new
            return
        try:
            (updater.run_setup if updater.installed() else updater.install_and_restart)(new)
        except updater.UpdateError as e:
            self.update_busy = ''
            messagebox.showerror('ACR Daily', _('Update failed: %s') % e)
            return
        self.quit(ask=False)

    def to_front(self):
        """Started again (an update, a new language): come to the front (Windows keeps it behind otherwise)."""
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        self.root.after(1500, lambda: self.root.attributes('-topmost', False))
        self.root.focus_force()

    def just_updated(self):
        """Started by the updater: come to the front and say so; a click on the bar opens what's new in this version
        again (whatsnew.py: its screen comes up by itself too)."""
        self.to_front()
        if not self.update_info:
            self._whats_new = True
            self.upd.configure(text=_("UPDATED TO %s  ·  WHAT'S NEW  ›") % __version__, bg=WHITE, fg=BG, cursor='hand2')
            self.upd.pack(side='right', padx=(0, 16), before=self.state_l)

            def done():
                self._whats_new = False
                if not self.update_info:           # (a newer version found meanwhile keeps its UPDATE bar)
                    self.upd.pack_forget()
                self.upd.configure(bg=ACC, fg=WHITE)
            self.root.after(20000, done)

    def periodic(self):
        """Once a minute: the runs waiting to be sent; today's boards as often as the server says (more often with
        the game running), the rest less often (*_EVERY_MIN)."""
        n = self._periodic_n = getattr(self, '_periodic_n', 0) + 1
        if n % 30 == 0 and not self.update_info:   # every 30 min: a new version?
            threading.Thread(target=self.check_update, daemon=True).start()
        if n % CHALLENGE_EVERY_MIN == 0 or not self.dailies or self._day_over():
            self.refresh_challenge()
        if n % ROUTES_EVERY_MIN == 0:
            self.refresh_routes()
        if n % LEAGUES_EVERY_MIN == 0:
            self.refresh_leagues()
        if n % TT_EVERY_MIN == 0 or self._tt_week_over() or (self.tt_info is None and n % 5 == 0):
            self.refresh_tt()                      # the week's stages and pots (a new week: its stages)
        if n % CREDITS_EVERY_MIN == 0:             # (a new day's bonus, the wager's pot)
            self.refresh_credits()
        if n % INBOX_EVERY_MIN == 0 or self.inbox_view:   # (every minute while the inbox is open: it is being read)
            self.refresh_unread()
        if n % DRIVER_EVERY_MIN == 0:              # (the rating moves once a day, and with a cup match)
            self.refresh_driver()
        if n % EXTRAS_EVERY_MIN == 0:              # the challenges or the cups, while their tab is open
            self.refresh_tab_extras()
        if n % LR_EVERY_MIN == 0 and not self.lr_view:   # live rallies' sessions (HOME's tile; the page: every minute)
            self.refresh_live_rallies()
        now = time.monotonic()
        every = self.timing('boardS' if getattr(self, 'last_frame', None) is not None else 'boardIdleS')
        if now - getattr(self, '_board_at', -1e9) >= every - 5:      # (this runs every 60 s, give or take)
            self._board_at = now
            self.refresh_board()
            if self.tt_view or self.drive_target == 'tt':   # (the time trial's boards: while in use)
                self.refresh_tt_board()
        threading.Thread(target=self.api.flush, args=(self._runs_sent,), daemon=True).start()
        threading.Thread(target=self.flush_leagues, daemon=True).start()
        self.root.after(60000, self.periodic)

    def _runs_sent(self):
        """(thread) Runs that waited reached the server: the credits again (a first finished run starts them); a DNF
        among them its replay may take back: asked about at once (replayui.py)."""
        ui(self.root, self.refresh_credits)
        ui(self.root, self._replay_poll)

    def timing(self, key):
        """How often (s) the server wants something done (TIMING), as today's dailies say once they are in."""
        for d in self.dailies.values():
            v = ((d.get('ch') or {}).get('timing') or {}).get(key)
            if isinstance(v, (int, float)) and v >= 1:
                return v
        return TIMING[key]

    def _day_over(self):
        """Today's dailies have closed (00:00 UTC): time for the new ones."""
        now = time.time() * 1000
        return any(d['ch'].get('endsAt') and d['ch']['endsAt'] <= now for d in self.dailies.values())

    def on_result(self, result):
        settings.append_result(result)
        self.local_runs = (*self.local_runs, (result.get('challengeId'), tuple(result.get('gameSteamIds') or ())))
        if not self.api.configured:
            return
        if not self.s.get('token'):
            self.api._queue(dict(result, appVersion=__version__))
            self.sub_l.configure(text=_('Sign in with Steam to put this run on the leaderboard.'))
            return

        def go():
            try:
                r = self.api.submit(result)
                app = (r or {}).get('appTime') or {}
                if r and r.get('status') == 'dnf':  # (the server's DNF: a lost result with respawns)
                    msg = _('DNF: %s') % local(r.get('reason') or '')
                elif r and r.get('counted') is False:
                    msg = (_('Practice run: only your official run counts.') if COMMIT_REQUIRED else
                           _('Practice run: only your first run counts.'))
                elif app.get('counted'):
                    msg = (_("The game lost its official time: the app's time counts instead.") +
                           ((' ' + _('Rank %s today.')) % r['rank'] if r.get('rank') else ''))
                else:
                    msg = _('Submitted.') + ((' ' + _('Rank %s today.')) % r['rank'] if r and r.get('rank') else '')
                if r and r.get('credits'):          # the free daily finished (credits)
                    msg += (' ' + _('+%d credits for finishing it.')) % r['credits']
                if result.get('noRallyWeekend'):     # (lost: a Single Rally Stage, most likely)
                    msg += ' ' + waiting.SINGLE_STAGE_HINT
                if r and r.get('counted') is not False:   # the counted run, a time or a DNF: a comment on it (commentui.py)
                    ui(self.root, self._offer_daily_comment, result, r)
                ui(self.root, self.refresh_credits)    # a first finished run starts the credits: the bonus now
            except ApiError as e:
                if e.code == TOO_OLD:
                    msg = _('Not on the board: %s') % e
                    self.check_update()          # shows the UPDATE bar
                elif refused(e):
                    msg = _('Not counted: %s') % e
                else:
                    msg = _('Not sent yet (%s) - will retry.') % e
            ui(self.root, self.sub_l.configure, {'text': msg})
            ui(self.root, self.refresh_board)
        threading.Thread(target=go, daemon=True).start()

    def _offer_daily_comment(self, result, r):
        """A daily's counted run is on the server: a comment on it offered, for its timing sheet (commentui.py). Its card
        pops up now, unless the next-daily card is to come (it carries the comment: _offer_next) or a run is on."""
        cid = str(result.get('challengeId') or '')
        try:
            slot = int(cid.rsplit('/', 1)[1])
        except (IndexError, ValueError):
            return
        ch = (self.dailies.get(slot) or {}).get('ch') or {}
        done = r.get('status') == 'finished' and r.get('totalMs')
        t = fmt_ms(r['totalMs']) if done else _('DNF')
        driving = any(x.get('judge') and x['judge'].state == 'running' for x in self.dailies.values())
        self.offer_comment(cid, ' · '.join(x for x in ('SS%d' % slot, stage_name(ch, short=True), t) if x), 'daily', 'SS%d' % slot,
                           title=self._run_title(slot, 'finished' if done else 'dnf'),
                           show=slot not in getattr(self, '_next_pending', ()) and not driving)

    def _run_title(self, slot, ev):
        """A daily's run as its card says it: 'SS1 FINISHED · P3 today', 'SS1 DNF'."""
        if ev == 'finished':
            me = self.s.get('steamId')
            mine = next((e for e in ((self.dailies.get(slot) or {}).get('board') or {}).get('entries', [])
                         if me and e.get('steamId') == me), None)
            return _('SS%d FINISHED') % slot + ((' ' + _('· P%s today')) % mine['rank'] if mine and mine.get('rank') else '')
        return 'SS%d %s' % (slot, _('DNF') if ev == 'dnf' else _('INVALID'))

    # -------------------------------------------------------------- Rally Weekend dailies: the game's own result

    @staticmethod
    def _game_save():
        """The game's save right now (bytes), or None if it can't be read."""
        try:
            return saveslot.read_save()
        except OSError:
            return None

    @classmethod
    def _game_results(cls, b=False):
        """The results in the game's save right now, or in b (rallyweekend.known()); None if it can't be read."""
        b = cls._game_save() if b is False else b
        return None if b is None else rallyweekend.known(b)

    def _started_again(self, kind, slot, b):
        """A run of the daily (kind 'daily') or time trial stage ('tt') `slot` just started, while an earlier finished
        run of it waits for the game's official result. To start it again the game has left that run's results screen,
        so its result is in the save b (read at this start) now or never: started again from the results screen, the
        game keeps no result (12 Nov 2026: a P3 waited 10 minutes for it, and went as "the game closed" when it did).
        Decided here: sent with the result, or as a DNF saying why, while the driver can still be told."""
        if b is None:
            return                                         # (not read: the wait goes on as before)
        for a in [x for x in self.awaiting if x.get('kind', 'daily') == kind and x['slot'] == slot]:
            o = self._official_match(a, b)
            waiting.note('%s: the stage started again; %s' % (a['id'], self._official_seen(a, b)))
            if o:
                waiting.note('%s: the game\'s result found: %.3f +%g' % (a['id'], o['time'], o['penalty']))
                self._official_found(a, o, b)
                continue
            if a.get('practice'):
                self._drop_practice(a)
                continue
            why = said('restarted from the game\'s results screen: the game did not save its time')
            self._lost_save(a, b, hint=False)        # (restarted: that is why, whatever the mode)
            waiting.note('%s: no official time: %s' % (a['id'], why))
            self._official_in(a, None, why, app_time=True)
            self._send_game_log([(a, why)])
            if OFFICIAL_ONLY:
                self.sub_l.configure(text=_("The game didn't save your time because you restarted from the results "
                                            "screen, so that run doesn't count. Next time, continue from the results "
                                            'screen first.'))
            else:
                self.sub_l.configure(text=_("The game did not save your finished run's time, as the stage was started again "
                                            "from its results screen. The app's time goes in instead. Next time go on from "
                                            "the results screen first."))

    def _await_official(self, slot, result, known, kind='daily', practice=False):
        """A Rally Weekend daily (or a time trial stage: kind 'tt', ttui.py) finished: it is sent with the game's own
        result (stage time + the game's penalties), read from the game's save once the game has written it there (when
        the driver goes on from its results screen); without one it is a DNF. The run waits on disk too (waiting.py),
        so closing the app loses nothing."""
        ch = (self._held_by(kind).get(slot) or {}).get('ch') or {}
        item = {'id': '%s:%s:%s' % (kind, ch.get('id') or slot, result.get('startedAt')), 'kind': kind, 'slot': slot,
                'stageId': ch.get('stageId') or '', 'carId': ch.get('carId') or '', 'result': result,
                # (as DRIVE wrote them: the save with the result is checked against them, _official_found)
                'weather': ch.get('weatherGame'), 'start': ch.get('startSeconds'), 'rules': ch.get('weekend'),
                'known': sorted(known) if known is not None else None, 'until': time.time() + OFFICIAL_WAIT_S,
                'practice': bool(practice)}
        setup = (self._held_by(kind).get(slot) or {}).get('ingame_setup')
        if setup:                  # set up in the running game: the stage as the game runs it, checked now (ingamedrive.py)
            live = ingamedrive.live_setup()
            if live is not None:
                item['ingameChanged'] = ingamedrive.setup_changed(setup['stages'][0], live)
                waiting.note('%s: set up in the game; the stage as the game runs it: %r; changed: %s' % (
                    item['id'], live, ', '.join(item['ingameChanged']) or 'nothing'))
        live = self._live_penalty()
        if live is not None:       # the game's penalties at the finish line (0.2's mod: main.lua read_penalty)
            item['live'] = {'penaltyMs': live[0], 'dq': live[1], 'at': time.time()}
            waiting.note('%s: the game\'s penalties at the finish: %d ms%s' % (
                item['id'], live[0], ', disqualified' if live[1] else ''))
        try:
            waiting.add(item)
        except (OSError, TypeError, ValueError):
            pass                                          # (it still waits here)
        self.awaiting.append(dict(item, known=known, closed=0, other=None))
        waiting.note('%s: finished (%s, %s), clock %s ms; %s results in the save at the start' % (
            item['id'], item['stageId'], item['carId'], result.get('clockMs'),
            'no save read' if known is None else len(known)))
        if not practice:
            self.sub_l.configure(text=(_('Finished.') + ' ') + waiting.HINT)
        if len(self.awaiting) == 1:
            self._official_watch = saveslot.SaveWatch()
            self.root.after(OFFICIAL_CHECK_MS, self._check_official)

    def _live_penalty(self):
        """The game's penalties on the loaded stage so far, as the mod reads them ((ms, disqualified)), or None."""
        try:
            p = self._pulse()
            return p.penalty() if p.mode() == 'weekend' else None
        except Exception:
            return None

    def _live_result(self, a):
        """The time the game gave a run at its finish line, from what the mod read there (the stage clock, stopped
        there, plus the game's penalties: _await_official), for a run whose result the game never saved: the game
        hangs on the loading after the results screen, often on Turini, and many drivers got a DNF (the user, 22 Nov
        2026). Only a run set up in the running game by ACR DAILY, its stage checked then as the game ran it
        (ingameChanged: nothing changed). -> the result as the save would give it ({time, penalty, splits}), 'dq'
        (the game disqualified it), or None."""
        live = a.get('live')
        if not live or a.get('ingameChanged') != [] or a.get('practice'):
            return None
        if live.get('dq'):
            return 'dq'
        clock = (a.get('result') or {}).get('clockMs')
        if not clock or clock <= 0:
            return None
        return {'time': clock / 1000.0, 'penalty': (live.get('penaltyMs') or 0) / 1000.0, 'splits': []}

    def _left_stage(self, a, track=None):
        """Has the game gone on from a finished run's stage (its results screen left: the menus, a loading screen, the
        game frozen on it or closed, the next stage of a rally)? Not a restart of that stage (the same stage, its clock
        from 0 again). track: the stage's (else the daily's / time trial's of a)."""
        try:
            p = self._pulse()
            if not p.alive():
                return True                    # (the mod silent: the game frozen on the loading, or closed)
            if p.mode() != 'weekend':
                return True                    # (its menus, or loading the next)
        except Exception:
            return False
        try:
            f = self.shm.read() if getattr(self, 'shm', None) is not None else None
        except Exception:
            f = None
        if f is None or not f.track:
            return False
        stage = {'track': track} if track else (self._held_by(a.get('kind')).get(a.get('slot')) or {}).get('ch') or {}
        if f.clock_ms == (a.get('result') or {}).get('clockMs'):
            return False                       # (its results screen: the clock still stopped at its finish)
        return bool(stage.get('track')) and not same_track(f.track, stage)

    def _still_there(self, a):
        """Is the game still on the stage of the finished run a (its stage clock still stopped at the run's finish)?"""
        try:
            f = self.shm.read() if getattr(self, 'shm', None) is not None else None
        except Exception:
            f = None
        return f is not None and f.clock_ms == (a.get('result') or {}).get('clockMs')

    @staticmethod
    def _finished_at(a):
        r = a.get('result') or {}
        return (r.get('startedAt') or 0) + (r.get('clockMs') or 0) / 1000

    def _lost_save(self, a, b, hint=True):
        """A lost result: the save as the app last read it (b) goes with its report (gamelog.py); and if the game wrote
        its save after the finish yet it holds no Rally Weekend result at all, the run was likely a Single Rally Stage
        (waiting.SINGLE_STAGE_HINT): marked on the run, for the driver and the report (not after a restart from the
        results screen, the reason then)."""
        a['lastSave'] = b
        if not hint:
            return
        try:
            after = a.get('savedAfter') or os.stat(saveslot.SAVE).st_mtime > self._finished_at(a)
        except OSError:
            after = False
        if b is not None and after and not rallyweekend.results(b):
            a['result']['noRallyWeekend'] = True
            waiting.note('%s: the save holds no Rally Weekend result at all: a Single Rally Stage?' % a['id'])

    def diagnostics_click(self):
        """Settings › Send diagnostics: the driver's line on what happened, the app's notes and the game's save, as their
        report (gamelog.send_manual); its number is the code to quote."""
        if not self.s.get('token'):
            messagebox.showinfo('ACR Daily', _('Sign in with Steam first: the diagnostics go as your report.'))
            return
        from tkinter import simpledialog
        text = simpledialog.askstring('ACR Daily', _('What happened? (a line or two: which run, what you saw)'),
                                      parent=self.root)
        if text is None:
            return                                         # (cancelled)
        try:
            save = saveslot.read_save_idle()               # (not while the game writes it)
        except OSError:
            save = None

        def done(rid, error):
            ui(self.root, self._diagnostics_sent, rid, error)
        if gamelog.send_manual(self.api, text, self._game_log_context(), save, done) is not None:
            self.sub_l.configure(text=_('Sending the diagnostics...'))

    def _diagnostics_sent(self, rid, error):
        if rid:
            messagebox.showinfo('ACR Daily', _('Sent: report #%d. Quote #%d to ACR Daily (Discord, or “Report a problem” '
                                               'on the website).') % (rid, rid))
            self.sub_l.configure(text=_('Diagnostics sent: report #%d.') % rid)
        else:
            messagebox.showwarning('ACR Daily', _('The diagnostics could not be sent: %s') % error)

    def in_game_app(self):
        """Is ACR DAILY inside the game (0.2: ingameapp.py)? Then no window of the app's over the game, no Windows sound."""
        return getattr(self, 'ingame_app', None) is not None

    def _notify(self, ok, title, text):
        """A sound and a Windows notification: how a run's wait for its official time ended (notify.py). Not with ACR DAILY
        in the game while the game runs: its strip in the game says it (a Windows sound over the game, the user, 20 Nov
        2026)."""
        if self.in_game_app() and saveslot.game_running():
            return
        if self.notifier is None:
            def hwnd():          # (an int, never anything else: ctypes handed an object it can't convert can crash)
                return ctypes.windll.user32.GetParent(int(self.root.winfo_id()))
            self.notifier = notify.Notifier(hwnd, lambda: (getattr(self, 's', None) or {}).get('notify', True))
        self.notifier.notify(ok, title, text)

    def _copilot_dnf(self, a, why):
        """A COPILOT crew's run (kind 'tt', CP_SLOT) without a time that counts: the crew's DNF on its board
        (copilot.py; a time trial's run would just not be sent). -> True when it was one."""
        cp = self.crew_for((a.get('result') or {}).get('challengeId') or ((self.tt.get(CP_SLOT) or {}).get('ch') or {}).get('id'))
        if a.get('slot') != CP_SLOT or cp is None:
            return False
        cp.on_result(dict(a.get('result') or {}, status='dnf', reason=str(why), totalMs=None))
        self.sub_l.configure(text=_('CODRIVER: DNF (%s).') % local(why))
        return True

    def _held_by(self, kind):
        """Where a waiting run's daily or time trial stage is: self.dailies or self.tt, by slot."""
        return self.tt if kind == 'tt' else self.dailies

    def _resume_waiting(self):
        """Runs left waiting for the game's official result when the app last closed: looked for again (the game keeps
        its result in its save; a run whose result the game never saved ends as a DNF, saying so)."""
        if self.awaiting:
            self.sub_l.configure(text=_('Your last run is still waiting for the game\'s official time: looking for it in '
                                      'the game\'s save. ') + waiting.HINT)
            self._official_watch = saveslot.SaveWatch()
            self.root.after(OFFICIAL_CHECK_MS, self._check_official)
        self._league_resume_waiting()

    def _check_official(self):
        """Every OFFICIAL_CHECK_MS while runs wait: their result in the game's save yet? The save is read only when the
        game has written it since (saveslot.SaveWatch: a read as the game writes it can make the game's save fail)."""
        if getattr(self, '_official_watch', None) is None:
            self._official_watch = saveslot.SaveWatch()
        watch = self._official_watch
        b = watch.look()
        running = None                       # asked only when a result is still missing (saveslot.game_running)
        lost = []                            # given up on without the game's result: its log may say why (gamelog.py)
        for a in list(self.awaiting):
            if watch.last != 'unchanged':
                waiting.note('%s: save %s; %s' % (a['id'], watch.last, self._official_seen(a, b)))
            if b is not None and watch.done and watch.done[0] / 1e9 > self._finished_at(a):
                a['savedAfter'] = True        # (the game wrote its save after the finish: it left the results screen)
            o = self._official_match(a, b)
            if o:
                waiting.note('%s: the game\'s result found: %.3f +%g' % (a['id'], o['time'], o['penalty']))
                self._official_found(a, o, b)
                continue
            if a.get('live') is not None and self._still_there(a):
                # (a penalty given after the finish line, before the results: 5 s of a respawn came 20 s or more after
                # the clock stopped, 22 Nov 2026: read again while the game is still on that finished stage)
                more = self._live_penalty()
                if more is not None and (more[0] > a['live']['penaltyMs'] or more[1] and not a['live']['dq']):
                    a['live'].update(penaltyMs=max(more[0], a['live']['penaltyMs']), dq=bool(a['live']['dq'] or more[1]))
                    waiting.note('%s: the game\'s penalties after the finish: %d ms%s' % (
                        a['id'], a['live']['penaltyMs'], ', disqualified' if a['live']['dq'] else ''))
            # the time at the finish line, sent as soon as the game goes on from the stage's results (penalties given
            # until then read above): no wait for the save, which comes later or, frozen on the loading, never (the
            # user, 22 Nov 2026: "do the uploading screen immediately instead of waiting to take it from the save")
            # (and now: FINISH_SETTLE_S after the finish line, still on the stage, the penalties read till then: the user,
            # 24 Nov 2026 "when user finishes the stage ... the time is sent THEN"; a game left on its results screen
            # 21 minutes, then closed, lost a championship's SS2, report #559)
            if a.get('live') is not None and not a.get('other') and (finish_settled(a) or self._left_stage(a)):
                live = self._live_result(a)
                if live == 'dq':
                    why = said('disqualified by the game')
                    waiting.note('%s: DNF: %s (at the finish line)' % (a['id'], why))
                    self._official_in(a, None, why)
                    continue
                if live:
                    waiting.note('%s: the stage left; the time at the finish line counts: %.3f +%g' % (
                        a['id'], live['time'], live['penalty']))
                    a['result']['officialSource'] = 'finish'
                    self._official_in(a, live)
                    continue
            if running is None:
                running = saveslot.game_running()
                gw = self._game_watch_on()
                if gw is not None:
                    gw.process(saveslot.game_pids)   # (its window responding; how its process ended)
            a['closed'] = 0 if running else a['closed'] + 1
            menus = self.back_in_menus(a)                     # (0.2: the game back in its menus, nothing saved)
            if a['closed'] >= 3 or menus or time.time() > a['until']:   # the game writes its save as it exits: a few more reads
                last = saveslot.read_save_now()                # a last look at the save as it is now, whatever the
                o = self._official_match(a, last)              # watch has read before
                waiting.note('%s: last look (game %s): %s' % (a['id'], 'running' if running else 'closed',
                                                              self._official_seen(a, last)))
                if o:
                    waiting.note('%s: the game\'s result found: %.3f +%g' % (a['id'], o['time'], o['penalty']))
                    self._official_found(a, o, last)
                    continue
                if a.get('practice'):        # (practice, as the start said: no time from the game, as expected)
                    self._drop_practice(a)
                    continue
                why = (said('the game saved %s, not this run\'s time', fmt_ms(round(a['other']['time'] * 1000)))
                       if a['other'] else said('the game closed before saving its official result') if a['closed'] >= 3
                       else said('left from the results screen: the game didn\'t save it') if menus
                       else said('no official result from the game'))
                live = None if a['other'] else self._live_result(a)
                if a['other']:               # (the game saved another time for it: a DNF, as ever)
                    waiting.note('%s: DNF: %s' % (a['id'], why))
                    self._official_in(a, None, why)
                elif live == 'dq':           # (the game disqualified it at the finish)
                    why = said('disqualified by the game')
                    waiting.note('%s: DNF: %s (%s)' % (a['id'], why, 'the save had none'))
                    self._official_in(a, None, why)
                elif live:                   # the time the game gave it at the finish line, penalties and all
                    waiting.note('%s: %s; the time at the finish line counts: %.3f +%g' % (
                        a['id'], why, live['time'], live['penalty']))
                    a['result']['officialSource'] = 'finish'
                    self._official_in(a, live)
                else:                        # the game saved nothing of it: a DNF (OFFICIAL_ONLY; the app's time up to
                    #                          0.1.5), and the report
                    self._lost_save(a, last)
                    waiting.note('%s: no official time: %s' % (a['id'], why))
                    self._official_in(a, None, why, app_time=True)
                    lost.append((a, why))
        if lost:
            self._send_game_log(lost)
        if self.awaiting:
            self.root.after(OFFICIAL_CHECK_MS, self._check_official)

    def back_in_menus(self, a):
        """Is the game back in its menus BACK_IN_MENUS_S since a run finished, its time still not in the save (0.2: the
        game mod says so)? The game saves a stage's time only as its results screen is left on to the next stage, the
        rally's end or its own menu; back in the menus with nothing saved, it never will (21 Nov 2026: quit from the
        results screen). Then the run ends now, not OFFICIAL_WAIT_S later, saying why."""
        try:
            menus = bool(self._pulse().in_menus())
        except Exception:
            return False
        if not menus:
            a.pop('menusSince', None)
            return False
        since = a.setdefault('menusSince', time.monotonic())
        return time.monotonic() - since >= BACK_IN_MENUS_S

    def _official_found(self, a, o, b):
        """The game's result o of the waiting run a, in the save b: it counts if the save still holds the daily (or time
        trial stage) as DRIVE wrote it, as ACRK's challenges check them: its weather, start time, track conditions, time
        speed and rules. Changed in the game's menu before START RALLY, the run is ignored, saying what: a daily's
        doesn't count and is no DNF (as one driven in the wrong mode: _void_daily; START OFFICIAL RALLY and the next run
        count again), a time trial run is not counted (only finished runs are sent there)."""
        w = None
        if a.get('ingameChanged') is not None:     # (set up in the running game: judged on the stage as the game ran
            changed = list(a['ingameChanged'])     # it, not on the save: it holds the set-up only once its results
            if not changed:                        # screen is left, _await_official)
                self._official_in(a, o)
                return
            a['changedOnce'] = a.get('changedOnce') or {'what': ', '.join(changed), 'at': time.time()}
        else:
            try:
                w = rallyweekend.read_weekend(b) if b else None
                changed = leagues.daily_changed(w, a) if w is not None else []
            except saveslot.SaveError:
                changed = []
        if not changed:
            if a.get('changedOnce'):
                waiting.note('%s: the next save holds the set-up as DRIVE made it: counted' % a['id'])
            self._official_in(a, o)
            return
        what = ', '.join(changed)
        if not a.get('changedOnce'):
            # The game writes its save twice after a stage: as the results screen comes up and as it is left. The first
            # one of a run set up in the running game (0.2, ingamedrive.py) was read as "stages changed" once (20 Nov
            # 2026, TT2) while the second held the set-up exactly: so a change is judged on the game's next save (or
            # after CHANGED_WAIT_S without one). What the first said, and that save, kept to see why.
            a['changedOnce'] = {'what': what, 'at': time.time()}
            a['until'] = min(a.get('until') or 0, time.time() + CHANGED_WAIT_S) or time.time() + CHANGED_WAIT_S
            waiting.note('%s: the result found, but the save says the set-up changed (%s): its next save decides. Save: '
                         'preset %s, stages %r, rules %r' % (a['id'], what, (w or {}).get('preset'),
                                                             [(s.get('stage'), s.get('day'), s.get('weather'), s.get('start'),
                                                               s.get('zone')) for s in (w or {}).get('stages') or []],
                                                             {k: (w or {}).get(k) for k in ('respawn', 'damage', 'intensity',
                                                                                             'wear', 'failures', 'penalty',
                                                                                             'hardcore')}))
            try:
                keep = os.path.join(settings.DIR, 'logs', 'changed-%s-%d.sav' % (
                    re.sub(r'[^A-Za-z0-9]+', '_', str(a['id']))[:40], int(time.time())))
                os.makedirs(os.path.dirname(keep), exist_ok=True)
                with open(keep, 'wb') as fh:
                    fh.write(b)
            except OSError:
                pass
            return
        waiting.note('%s: the result found, but the set-up changed in the game: %s' % (a['id'], what))
        if a.get('kind') == 'tt' and a.get('slot') == CP_SLOT:
            self.awaiting.remove(a)
            try:
                waiting.remove(a.get('id'))
            except OSError:
                pass
            self._copilot_dnf(a, said('the stage\'s %s changed in the game', what))
            return
        if a.get('kind') == 'tt':
            self.awaiting.remove(a)
            try:
                waiting.remove(a.get('id'))
            except OSError:
                pass
            self.sub_l.configure(text=_("TT%d: not counted: the stage's %s changed in the game's menu. DRIVE sets it up "
                                        'as it must be.') % (a['slot'], local(what)))
            return
        self.awaiting.remove(a)
        try:
            waiting.remove(a.get('id'))
        except OSError:
            pass
        self._void_daily(a, said('the daily\'s %s changed in the game', what), changed=True)

    def _drop_practice(self, a):
        """A practice run (not in the daily's Rally Weekend, in_rally) whose official result the game never saved, as
        expected: nothing sent, no DNF, no report."""
        self.awaiting.remove(a)
        try:
            waiting.remove(a.get('id'))
        except OSError:
            pass
        waiting.note('%s: practice (not in the Rally Weekend): no result from the game, as expected; nothing sent' % a['id'])
        j = (self._held_by(a.get('kind')).get(a['slot']) or {}).get('judge')
        if j and j.result is not None and j.result.get('startedAt') == (a.get('result') or {}).get('startedAt') \
                and j.state == 'finished':
            j.message = _('PRACTICE %s (not in the Rally Weekend: not counted)') % fmt_ms((a.get('result') or {}).get('clockMs') or 0)

    def _send_game_log(self, lost):
        """Finished runs the game didn't save the result of (stuck on a loading screen, closed...): the log the game kept
        of that session goes to the admin with what the app saw, as the driver's bug report (gamelog.py), so the cause
        can be found. lost: [(the waiting run, why)], one report for the dailies and one for the time trial."""
        api = getattr(self, 'api', None)
        if api is None:
            return
        try:
            for kind, area in (('daily', 'daily'), ('tt', 'time trial')):
                runs, save = [], None
                for a, why in lost:
                    if a.get('kind', 'daily') != kind:
                        continue
                    cid = a['id'].split(':', 1)[-1].rsplit(':', 1)[0]      # (its id: kind:challenge:startedAt)
                    day = re.match(r'\d{4}-\d\d-\d\d', cid)
                    what = ('TT%d (%s)' % (a['slot'], cid) if kind == 'tt' else
                            'SS%d %s' % (a['slot'], day.group(0)) if day else 'SS%d (%s)' % (a['slot'], cid))
                    stage, car = self._official_ids(a)
                    runs.append({'id': a['id'], 'what': what, 'stage': stage, 'car': car, 'why': str(why),
                                 'startedAt': a['result'].get('startedAt'), 'clockMs': a['result'].get('clockMs'),
                                 'resets': a['result'].get('resets') or 0,
                                 'noRallyWeekend': bool(a['result'].get('noRallyWeekend'))})
                    if a.get('lastSave') is not None:
                        save = a['lastSave']             # (the newest of them: one save a report)
                if runs:
                    gamelog.send(api, runs, area, api.site + '/tt' if kind == 'tt' else None, self._game_log_context(),
                                 on_sent=self._game_log_sent, watch=self._game_watch_seen(), save=save)
        except Exception:                    # (a report never holds up the waits)
            import traceback
            traceback.print_exc()

    def _game_watch_seen(self):
        """What the game watch saw (gamewatch.GameWatch.snapshot()), for a report; None without one."""
        gw = self.game_watch
        return gw.snapshot() if gw is not None else None

    def _game_log_context(self):
        """For such a report: what of the app was on (the game mod, auto-drive, the timer window)."""
        s = getattr(self, 's', None) or {}
        g, o = s.get('ghostCars') or {}, s.get('overlay') or {}
        return 'App %s: ghost cars %s, auto-drive %s, timer in the game %s.' % (
            __version__, ('on, in the game (UE4SS)' if g.get('ingame', True) else 'on, drawn over it') if g.get('on')
            else 'off', 'on' if s.get('autoDrive') else 'off', 'shown' if o.get('visible', True) else 'hidden')

    def _game_log_sent(self, report_id):
        """(the report's thread) Its log went: the driver is told, and where to follow it."""
        ui(self.root, self.sub_l.configure, {'text': _("The game didn't save this run. Its log went to ACR Daily to find "
                                                        "out why (report #%d, under “Report a problem” on the "
                                                        "website).") % report_id})

    def _official_ids(self, a):
        ch = (self._held_by(a.get('kind')).get(a['slot']) or {}).get('ch') or {}
        return a.get('stageId') or ch.get('stageId') or '', a.get('carId') or ch.get('carId') or ''

    def _official_match(self, a, b):
        """The game's result of the waiting run a in the save b, or None (a['other']: a new result of its stage and car
        with another time). A new result (not in the save at the start) whose time is the app's within
        OFFICIAL_CLOCK_MS; else one that was there at the start but whose time is the app's to the OFFICIAL_SAME_MS:
        the run's own, however the save looked at the start (11 Nov 2026: two dailies the game had saved went as DNFs)."""
        if not b:
            return None
        r = a['result']
        stage, car = self._official_ids(a)
        o = rallyweekend.official(b, stage, car, a['known'] or set(), since=r.get('startedAt'))
        if o and abs(o['time'] * 1000 - r['clockMs']) <= OFFICIAL_CLOCK_MS:
            return o
        same = rallyweekend.official(b, stage, car, since=r.get('startedAt'), clock_ms=r['clockMs'],
                                     tol_ms=OFFICIAL_SAME_MS)
        if same:
            return same
        a['other'] = o or a['other']
        return None

    def _official_seen(self, a, b):
        try:
            stage, car = self._official_ids(a)
            return 'clock %d ms; %s' % (a['result'].get('clockMs') or 0, rallyweekend.describe(b, stage, car, a['known'] or ()))
        except Exception as e:                                 # (only ever for the log)
            return 'not described: %r' % e

    def _official_in(self, a, o, why='', app_time=False):
        """The wait for a run's official result is over: send it with the result (o), with the app's own time (app_time:
        the game lost its result, why), or as a DNF (why). With OFFICIAL_ONLY there is no app's time: such a daily run
        is a DNF, a time trial run not counted (nothing sent)."""
        self.awaiting.remove(a)
        try:
            waiting.remove(a.get('id'))
        except OSError:
            pass
        r = a['result']
        if app_time and OFFICIAL_ONLY:            # no official time: no app's clock in its place
            if r.get('noRallyWeekend'):           # (the save after the finish holds no Rally Weekend: _lost_save)
                why = said(NO_RALLY_WEEKEND)
            if a.get('kind') == 'tt' and self._copilot_dnf(a, why):   # (COPILOT: one go: the crew's DNF, copilot.py)
                return
            if a.get('kind') == 'tt':             # (the time trial takes finished runs only: nothing to send)
                label = 'TT%d' % a['slot']
                waiting.note('%s: not counted (no official time): %s' % (a['id'], why))
                self._notify(False, _('No official time'), '%s: %s' % (label, local(why)))
                self.sub_l.configure(text=_("%s didn't count: %s. Only times the game saves count, so drive it in Rally "
                                            'Weekend mode.') % (label, local(why)))
                return
            self._void_daily(a, why)              # (a daily's: not counted either, no DNF; the server is told)
            return
        if o:
            off = {'timeMs': int(round(o['time'] * 1000)), 'penaltyMs': int(round(o['penalty'] * 1000)),
                   'splitsMs': [int(round(t * 1000)) for t in o['splits']]}
            r.update(official=off, totalMs=off['timeMs'] + off['penaltyMs'])
        elif app_time:                # (the server takes it, marked: server/src/apptime.js)
            r.update(appTime=True, lost=str(why), totalMs=r['clockMs'])
        else:
            r.update(status='dnf', reason=why, totalMs=None)
        tt = a.get('kind') == 'tt'
        label = ('TT%d' if tt else 'SS%d') % a['slot']
        if o:                                 # (where the driver is looking: notify.py)
            self._saved_at = time.monotonic()     # (the timer window: saved, in green, for a moment)
            self._notify(True, _('Official time saved'), (_('%s: %s (%s + %d s penalty)') % (
                label, fmt_ms(r['totalMs']), fmt_ms(off['timeMs']), round(off['penaltyMs'] / 1000))
                if off['penaltyMs'] else '%s: %s' % (label, fmt_ms(r['totalMs']))))
        elif app_time:
            self._notify(False, _('No official time'), _("%s: the game did not save this run's time.") % label)
        else:
            self._notify(False, _('No official time'), '%s: %s' % (label, local(why)))
        j = (self._held_by(a.get('kind')).get(a['slot']) or {}).get('judge')
        shown = bool(j and j.result is not None and j.result.get('startedAt') == r.get('startedAt'))
        if shown:                                         # still on screen (not a run from before a restart): update it
            j.result.update({k: r[k] for k in ('status', 'reason', 'totalMs') if k in r}, official=r.get('official'))
            if j.state == 'finished' and o:
                j.message = _('FINISHED %s (official: %s + %d s penalty)') % (
                    fmt_ms(r['totalMs']), fmt_ms(off['timeMs']), round(off['penaltyMs'] / 1000))
            elif j.state == 'finished' and app_time:
                j.message = _("FINISHED %s (the app's time: the game lost its own)") % fmt_ms(r['totalMs'])
            elif j.state == 'finished':
                j.state, j.message = 'dnf', _('DNF: %s') % local(why)
        if o and shown and tt and a['slot'] == self.tt_active:
            self._tt_standing(a['slot'], _('FINISH (official)'), r['totalMs'], None, hold=FINISH_SHOW_S)
        elif o and shown and not tt and a['slot'] == self.active:
            self._standing(_('FINISH (official)'), r['totalMs'], None, hold=FINISH_SHOW_S)
        (self.on_tt_result if tt else self.on_result)(r)

    def _daily_ended(self, slot, d, ev, result):
        """A daily's counted run ended. A finish of a Rally Weekend daily waits for the game's official time (none, as in
        Practice or a Single Rally Stage: ignored, not a DNF, _void_daily). A restart or quitting is a DNF whatever the
        mode: the driver committed to that run with START OFFICIAL RALLY."""
        if ev == 'finished' and is_weekend(d['ch']):
            self._await_official(slot, result, d.get('known'))
        else:
            self.on_result(result)

    def _void_daily(self, a, why, changed=False):
        """A committed daily run without the game's official time (OFFICIAL_ONLY): driven in Practice or a Single Rally
        Stage, which keep no time, or a time the game lost (it can't be told which). It doesn't count, and it is no DNF:
        the daily is not driven yet here (START OFFICIAL RALLY and the next run count again), and the server is told
        (status 'void', in the order driven: it forgets that start, so the next run counts there too, however many:
        server/src/voids.js). The admin gets the report as for any lost time (_send_game_log). changed: the game's time
        was there, but the daily's set-up had been changed in its menu (_official_found): ignored the same way."""
        slot, r = a['slot'], a['result']
        waiting.note('%s: not counted (%s): %s' % (a['id'], 'set-up changed' if changed else 'no official time', why))
        d = self.dailies.get(slot) or {}
        if (d.get('ch') or {}).get('id') == r.get('challengeId'):
            if not d.get('norally'):          # (started again meanwhile: that run's own, uncommitted, stays)
                d['norally'], d['practice_why'] = True, 'void'
            # (the timer window's line under the run, in red: why it didn't count, _overlay_state)
            d.update(started_once=False, practice=False, voided=True, void_line=_("DIDN'T COUNT: %s") % local(why))
            j = d.get('judge')
            if j is not None and j.result is not None and j.result.get('startedAt') == r.get('startedAt') \
                    and j.state == 'finished':
                j.message = d['void_line']
        label = 'SS%d' % slot
        self._notify(False, _("Didn't count") if changed else _('No official time'), '%s: %s' % (label, local(why)))
        if changed:
            self.sub_l.configure(text=_("SS%d didn't count: %s. DRIVE it again from ACR DAILY, without changing it in the "
                                        "game's menu.") % (slot, local(why)))
        else:
            self.sub_l.configure(text=_("SS%d didn't count: %s. DRIVE it again from ACR DAILY.") % (slot, local(why)))
        body = dict(r, status='void', reason=str(why), totalMs=None)
        if not getattr(getattr(self, 'api', None), 'configured', False):
            return
        if not (getattr(self, 's', None) or {}).get('token'):
            self.api._queue(dict(body, appVersion=__version__))
            return

        def go():
            msg = None
            try:
                self.api.submit(body)
            except ApiError as e:
                if e.code == TOO_OLD:
                    msg = _('Not on the board: %s') % e
                elif not refused(e):
                    msg = _('Not sent yet (%s) - will retry.') % e
            if msg:
                ui(self.root, self.sub_l.configure, {'text': msg})
            ui(self.root, self.refresh_board)
        threading.Thread(target=go, daemon=True).start()

    # -------------------------------------------------------------- loop

    def tick(self):
        """20 times a second: read the game, judge, draw. Always schedules the next tick, whatever happens."""
        try:
            self._tick()
        except Exception:
            import traceback
            traceback.print_exc()
        self.root.after(TICK_MS, self.tick)

    def _tick(self):
        try:
            f = self.shm.read()
        except Exception:
            f = None
        self.last_frame = f
        now = time.monotonic()
        if f is not None or getattr(self.shm, 'unloaded', False):
            self._game_at = now            # the game is open: on a stage or in its menus (_game_open)
        self.auto_rec.feed(f, now)
        self._replay_feed(f, now)          # (before the judges: their start / end tag the run being recorded)
        if self.auto_rec.state == 'done':
            self._contribute(self.auto_rec.saved)
            self.auto_rec = RouteRecorder()
        if self.recorder:
            self.recorder.feed(f, now)
            if self.s.get('admin'):
                self.adm_l.configure(text=self.recorder.message)
        # following a league event (DRIVE / CONTINUE on it): its next stage is judged instead of the dailies, so the
        # one run never counts for both (leagueui.py)
        unloaded = getattr(self.shm, 'unloaded', False)
        gw = self._game_watch_on()
        if gw is not None:                 # (a finished run waiting: what the game does meanwhile)
            gw.telemetry('stage' if f is not None else 'menus' if unloaded else 'none')
        if self.drive_target == 'league':
            self._league_tick(f, unloaded)
        self._tt_tick(f, unloaded)        # the time trial's stages (ttui.py; not while following a league event)
        self._lr_watch(f)                 # a ranked rally's stages driven outside it: a DNF (liverallyui.py)
        # every daily's judge sees every frame; each only starts on its own stage + car
        for slot, d in list(self.dailies.items()) if self._dailies_judged() else ():
            j = d.get('judge')
            if not j:
                continue
            evs = j.feed(f, unloaded)
            evs = evs + self._watch_run(d, j, evs, d['ch'].get('weekend'))   # (not allowed, during the stage: DNF)
            on_line = not evs and (j.state == 'armed' or j.approaching)
            # on the start line: the race's settings as the game runs them, against the daily's (the game mod reads
            # them: settings_changed; None where it can't)
            d['changed_pre'] = self.settings_changed(d['ch'].get('weekend')) if on_line and is_weekend(d['ch']) else None
            if not on_line:
                d['rw_checked'], d['rw_pre'] = False, None   # (looked at again each time the car comes to the start line)
                if not (j.state == 'armed' or j.approaching):
                    d['commit_offered'] = False
            elif COMMIT_REQUIRED and not d.get('commit_offered'):
                d['commit_offered'] = True                # on its start line uncommitted: the card, once each time
                self.commit_offer(slot)
            elif is_weekend(d['ch']) and self.mode_rw() is not None:
                d['rw_pre'] = self.mode_rw()              # on the start line: the mode, as the game mod says it
            elif PRACTICE_CHECK and not d.get('rw_checked') and is_weekend(d['ch']) and now >= d.get('rw_next', 0):
                # on the start line (or driving up to it): which mode? (in_rally; only what the timer says before the
                # start). A look of the app's own: never just after the game wrote its save, as it does when a stage
                # has loaded (a read then can make the game's write fail, and a result lost with respawns is a DNF)
                try:
                    b = saveslot.read_save_idle()
                except OSError:
                    d['rw_next'] = now + RW_RETRY_S
                else:
                    d['rw_checked'] = True
                    d['rw_pre'] = in_rally(d['ch'], b)
            for ev in evs:
                if ev == 'start':
                    self._daily_started(slot, d)
                    # (its replay: a counted run followed by the server, a proof of its finish: replays.py)
                    ch = d['ch'] or {}
                    self._replay_tag('daily', ch.get('id'), 'SS%d · %s' % (slot, ch.get('date') or ''),
                                     not (d.get('norally') or d.get('practice') or d.get('unstaked')),
                                     stageId=ch.get('stageId'), carId=ch.get('carId'))
                if ev in ('finished', 'dnf', 'invalid'):
                    self._replay_end(ev, j.result)
                if ev in ('finished', 'dnf', 'invalid') and d.get('unstaked'):
                    self.sub_l.configure(text=_('Not counted: SS%d needs a stake. Click its DRIVE first.') % slot)
                elif ev in ('finished', 'dnf', 'invalid') and d.get('norally'):
                    if d.get('practice_why') == 'uncommitted':
                        # START OFFICIAL RALLY not pressed: ignored, even with a time the game saved
                        self.sub_l.configure(text=UNCOMMITTED_HINT)
                    elif d.get('practice_why') == 'settings':
                        # the race's settings not the daily's (read in the game at the start): ignored, no DNF
                        self.sub_l.configure(text=self.problems_hint('SS%d' % slot, d.get('changed')))
                    elif d.get('practice_why') == 'here':
                        # not taken there by ACR DAILY: ignored, even with a time the game saved; no DNF
                        self.sub_l.configure(text=NOT_HERE_HINT % slot)
                    else:
                        # practice: not in the daily's Rally Weekend. A finish still waits for the game's result, in
                        # case the save misled the check at the start: found, it counts; lost, it is dropped
                        if ev == 'finished':
                            accounts = (d.get('accounts') or set()) | {steam_account()}
                            result = dict(j.result, gameSteamIds=sorted(a for a in accounts if a), country=self.country)
                            self._await_official(slot, result, d.get('known'), practice=True)
                        self.sub_l.configure(text=PRACTICE_HINT)
                elif ev in ('finished', 'dnf', 'invalid'):
                    accounts = (d.get('accounts') or set()) | {steam_account()}
                    result = dict(j.result, gameSteamIds=sorted(a for a in accounts if a), country=self.country)
                    self._daily_ended(slot, d, ev, result)
                    self._send_live(slot, j, f, 'finished' if ev == 'finished' else 'dnf')
                    other = self._next_to_offer(slot)
                    if other:      # a few seconds later, when the result is in and the game shows its own
                        self._next_pending.add(slot)
                        self.root.after(NEXT_CARD_AFTER_MS, lambda s=slot, o=other, e=ev: self._offer_next(s, o, e))
                if ev == 'start':
                    self.active = slot
                    self._show_active()
                    self._send_live(slot, j, f, 'live')
                if ev == 'split':
                    n = len(j.splits)
                    self._standing(split_title(j.split_at[n - 1]), j.splits[-1], n - 1, hold=SPLIT_SHOW_S)
                elif ev == 'finished':
                    self._standing(_('FINISH (provisional)'), j.result['totalMs'], None, hold=FINISH_SHOW_S)
                elif ev in ('start', 'dnf', 'invalid'):
                    self._clear_standing()
            if j.state == 'running' and now - self.live_at >= self.timing('liveSendS'):
                self._send_live(slot, j, f, 'live')
        if self.panel_until and now > self.panel_until:
            self._clear_standing()
        active = self._pick_active(f)
        if active != self.active:
            self.active = active
            self._show_active()
        self._drop_stale_standing(f)
        try:
            self._apply_visibility(f)
            self._render(f)
            self._wtick += 1
            if self._wtick % 2 == 0:          # the optional displays: 10 times a second
                self._render_widgets(f)
            self._keep_on_top(now)
            self._measure(f, now)
        except Exception:   # a display bug must never stop the run being judged
            import traceback
            traceback.print_exc()

    def _daily_started(self, slot, d):
        """A daily's stage clock started: what this run is. The wager daily without a stake (unstaked: it won't count);
        which Steam account the game runs under (checked against the sign-in); a run outside the daily's Rally Weekend
        (norally: practice, only a run there counts, in_rally); and whether the daily was driven before (practice: the
        first start is the one that counts)."""
        d['unstaked'] = self._needs_stake(slot)
        d['accounts'] = {steam_account()}
        b = self._game_save() if is_weekend(d['ch']) else None
        seen = in_rally(d['ch'], b) if is_weekend(d['ch']) else None
        # which mode: the game mod says it (game_mode), else the save's look (off: every run counts from its start)
        told = self.mode_rw() if is_weekend(d['ch']) else None
        rw = told if told is not None else seen if PRACTICE_CHECK else None
        # committed: START OFFICIAL RALLY pressed for today's daily before this start, which uses it up (whatever the run)
        c, d['committed'] = d.get('committed'), None
        d['voided'] = False                            # (the run before it didn't count: _void_daily)
        uncommitted = COMMIT_REQUIRED and not (c and c.get('date') == (d['ch'] or {}).get('date'))
        # its settings as the game runs them (the game mod: settings_changed), changed in the game's menu: doesn't count
        changed = self.settings_judged(d['ch'].get('weekend')) if is_weekend(d['ch']) and rw is not False else None
        d['changed'] = changed or None
        # not taken there by ACR DAILY (a Rally Weekend set up or resumed by hand in the game's menus, even with the
        # daily's settings): never counts, not even with the game's result in its save at the finish (21 Nov 2026)
        here = self.set_up_here() if is_weekend(d['ch']) else None
        watching = getattr(getattr(self, 'watch', None), 'on', False)     # (WATCH: nothing of yours counts)
        d['norally'] = rw is False or uncommitted or bool(changed) or here is False or watching
        d['practice_why'] = ('uncommitted' if uncommitted else 'here' if here is False or watching else
                             'rally' if rw is False else 'settings' if changed else None)
        if changed:
            waiting.note('daily:%s/%d: started; the race\'s settings in the game are not the daily\'s: %s (not counted)'
                         % (d['ch'].get('date') or '', slot, ', '.join(changed)))
        self._close_commit(slot)                       # (its card, if still up: too late for this run)
        # (after norally: a run outside the Rally Weekend is no start, so it must not mark the daily driven, which made
        # the real run after it PRACTICE on the timer, "your first run is your result")
        d['practice'] = self._driven(slot)
        if is_weekend(d['ch']):
            d['known'] = self._game_results(b)       # the game's result of this run will be a new one
            self._started_again('daily', slot, b)    # an earlier finished run still waiting: now or never
            waiting.note('daily:%s/%d: started; the game mod says the mode is %s; the daily\'s Rally Weekend in '
                         'progress: %s%s; taken there by ACR DAILY: %s' % (
                             d['ch'].get('date') or '', slot, self.game_mode() or 'unknown',
                             {True: 'yes', False: 'no (practice)', None: 'unknown'}[seen],
                             '' if PRACTICE_CHECK else ' (not used)',
                             {True: 'yes', False: 'no (practice)', None: 'unknown'}[self.set_up_here()]))
        if COMMIT_REQUIRED:
            waiting.note('daily:%s/%d: started %s' % (d['ch'].get('date') or '', slot,
                                                     'uncommitted (practice: START OFFICIAL RALLY not pressed)'
                                                     if uncommitted else 'committed (START OFFICIAL RALLY): it counts'))

    def _measure(self, f, now):
        """The game's graphics packets a second while a run's clock runs (telemetry.PacketRate: its frames, if it writes
        one a frame), apart for while a window of the app was over the full-screen game and while none was; said in
        official.log once the run is over, so a driver's Send diagnostics shows what the app's windows cost the game on
        their PC (README, "The timer and the game's FPS"). What the game's screen has on it: looked at once a second."""
        rate = getattr(self, 'game_rate', None)
        if rate is None:
            rate = self.game_rate = PacketRate()
        key, running = None, self._clock_running()
        if running:
            if now - getattr(self, '_rate_at', -1e9) >= 1.0:
                self._rate_at, self._rate_key = now, self._screen_state()
            key = self._rate_key
        else:
            self._rate_at = -1e9
        line = rate.feed(f, key, end=not running and not self._clock_running(paused=True))
        if line:
            waiting.note("the game's graphics packets while the clock ran: " + line)

    def _screen_state(self):
        """What the app has on the game's screen now: 'over' (a window of the app shown on the screen the game fills),
        'clear' (none), 'window' (the game in a smaller window), 'unknown' (which screen can't be told)."""
        screen = self._game_screen()
        if screen is False or screen is None:
            return 'window' if screen is False else 'unknown'
        wins = [self.overlay.win] + [w.win for w in self.widgets.values()]
        ghosts = getattr(self, 'ghostcars', None)
        if ghosts is not None and getattr(ghosts, 'win', None) is not None:
            wins.append(ghosts.win)
        card = getattr(self, 'next_card', None)
        if card is not None and card.alive:
            wins.append(card.win)
        return 'over' if any(w.winfo_ismapped() and widgets.over(w, screen) for w in wins) else 'clear'

    def _keep_on_top(self, now):
        """The timer and the displays back over the game if it has come over them, looked at every ON_TOP_S (not set
        on every tick: widgets.keep_on_top)."""
        if now - getattr(self, '_top_at', -1e9) < widgets.ON_TOP_S:
            return
        self._top_at = now
        for w in [self.overlay] + list(self.widgets.values()):
            widgets.keep_on_top(w.win)

    def _render(self, f):
        ch = self.challenge
        status, sub, ov = self._overlay_state(f)
        if self.status_l.cget('text') != status:
            self.status_l.configure(text=status)
        if sub and self.sub_l.cget('text') != sub:     # (a Tk label is drawn again on every configure, even the same)
            self.sub_l.configure(text=sub)
        word, bg, fg = STATUS.get(ov[0], STATUS['standby'])     # (the timer window's badge, without its blink)
        if self.state_l.cget('text') != word:
            self.state_l.configure(text=word, bg=bg, fg=fg)
        # on one of our stages, the game's mode named, as the game mod tells it (the displays in the game: its own chip)
        self._mode_shown = self.mode_label() if ov[0] not in ('offline', 'standby') else None
        if self._mode_shown:
            ov = (ov[0], '%s · %s' % (ov[1], self._mode_shown[0])) + tuple(ov[2:])
        self.overlay.render(*ov)
        self._render_saving()
        self._render_update()
        self._show_ends(ch)                        # (the header: when the dailies close)
        self._home_tick()                          # (HOME's tiles: what is on now)
        self._lr_tick()                            # (live rallies: the countdowns, my session looked at again: liverallyui.py)
        self._gate_check()                         # (signed out, or the session gone: the sign-in screen)
        pending = self.api.pending_count()          # (kept by the Api: not the file read on every tick)
        ends = ''
        if self.tt_view:
            ends = self._tt_footer()               # (the time trial's week)
        elif ch and ch.get('endsAt') and self.layout_narrow:     # (a wide window: in the header, _show_ends)
            left = int(ch['endsAt'] / 1000 - time.time())
            if left > 0:
                ends = ('   ' + _('·   stages close in %d:%02d')) % (left // 3600, left % 3600 // 60)
        foot = 'v%s%s%s%s%s' % (__version__, ends, '   ·   ' + n_('%d run waiting to send', '%d runs waiting to send', pending) % pending if pending else '',
                                '   ·   ' + self.net_msg if self.net_msg and ch else '',
                                '   ·   ' + self.update_msg if self.update_msg else '')
        if self.foot_l.cget('text') != foot:
            self.foot_l.configure(text=foot, fg=ACC_TEXT if self.update_msg else MUTED)

    def _show_ends(self, ch):
        """The header's top right: when the dailies close, 'STAGES CLOSE IN 7:40' (nothing before they are in, or once
        they have closed)."""
        left = int(ch['endsAt'] / 1000 - time.time()) if ch and ch.get('endsAt') else 0
        texts = ((self._ends_words[0], '%d:%02d' % (left // 3600, left % 3600 // 60), self._ends_words[1]) if left > 0
                 else ('', '', ''))
        for l, text in zip(self.ends_l, texts):
            if l.cget('text') != text:
                l.configure(text=text)

    def _overlay_state(self, f):
        """-> (main window status, main window sub-line, overlay args (status, title, ms, resets, line, colour))."""
        j, ch, rec = self.judge, self.challenge, self.recorder
        if rec and rec.state == 'recording':
            return rec.message, '', ('rec', _('RECORDING ROUTE · %s') % rec.track.upper(), f.clock_ms if f else 0, 0,
                                     _('Drive cleanly to the finish'), SOFT)
        league = self._league_overlay_state(f)      # following a league event
        if league:
            return league
        tt = self._tt_overlay_state(f)              # a time trial stage (ttui.py)
        if tt:
            return tt
        if not ch:
            if self.net_msg and not getattr(self, '_fetching', False):
                return (_("Can't reach ACR Daily"), '', ('offline', 'ACR DAILY', 0, 0, self.net_msg, MUTED))
            return (_('Getting today\'s challenge...'), '',
                    ('offline', 'ACR DAILY', 0, 0, _('Connecting to the server'), MUTED))
        stage = 'SS%d · %s' % (ch.get('slot', 1), stage_name(ch, short=True).upper())
        today = '  |  '.join('%d: %s · %s%s' % (s, stage_name(d['ch']), d['ch']['car'],
                                                 ' (%s)' % conditions(d['ch']) if conditions(d['ch']) else '')
                             for s, d in sorted(self.dailies.items()))
        if not j:
            return _('Today\'s stage has no route yet'), _('Check back later.'), ('offline', stage, 0, 0, _('No route for today yet'), MUTED)
        signed = bool(self.s.get('token'))
        if j.state == 'running':
            gap = j.gap_ms
            if j.paused:
                line, lc = _('PAUSED · the run carries on with the clock'), SOFT
            elif gap is not None:
                line = _('vs %s  %s%.2f') % (getattr(self, 'ghost_name', '#1'), '+' if gap >= 0 else '−', abs(gap) / 1000)
                lc = SLOW if gap > 0 else GOOD
            else:
                line, lc = _('On stage · %d%%') % round(j.progress * 100), SOFT
            if not signed:
                line += ('   ' + _('· not signed in'))
            d = self.dailies.get(ch.get('slot', 1)) or {}
            if d.get('unstaked'):
                line, lc = _('NO STAKE · this run does not count'), BAD
            elif d.get('norally'):
                line, lc = self._norally_line(d)
            elif d.get('practice'):
                line = NOT_COUNTED + ' ' + line
            elif 0 <= j.total_ms < COUNTS_LIVE_MS:      # the counted run's first seconds: no restart now
                line, lc = COUNTS_LINE, SLOW
            # (a run that won't count: the badge grey, not red, so the colour says it at a glance)
            off = d.get('unstaked') or d.get('norally') or d.get('practice')
            return j.message, '', ('live_off' if off else 'live', stage, j.total_ms, j.resets, line, lc)
        if j.state in ('finished', 'dnf', 'invalid') and (self.dailies.get(ch.get('slot', 1)) or {}).get('unstaked'):
            return j.message, '', (j.state, stage, j.total_ms, j.resets, _('Not counted: no stake (DRIVE in ACR Daily)'), BAD)
        dd = self.dailies.get(ch.get('slot', 1)) or {}
        if j.state in ('finished', 'dnf', 'invalid') and dd.get('norally'):    # practice (uncommitted, or not the Rally Weekend)
            why = dd.get('practice_why')
            if why == 'void' and dd.get('void_line'):            # (committed, but it didn't count: why, _void_daily)
                line, lc = dd['void_line'], BAD
            else:
                line, lc = self._norally_line(dd)
            return j.message, '', ('standby', stage, (j.result or {}).get('clockMs', j.total_ms), j.resets, line, lc)
        if j.state == 'finished':
            if any(a.get('kind', 'daily') == 'daily' and a['slot'] == ch.get('slot', 1) and
                   a['result'].get('startedAt') == (j.result or {}).get('startedAt') for a in self.awaiting):
                return j.message, '', ('finished', stage, j.total_ms, j.resets,
                                       self._next_line(), SOFT)
            if (self.dailies.get(ch.get('slot', 1)) or {}).get('practice'):
                # (not on the board, so no place ever comes: "Sending..." stayed on, 13 Nov 2026, report #9)
                return j.message, '', ('finished', stage, j.total_ms, j.resets,
                                       DRIVEN_LINE, SOFT)
            rank = self._my_rank()
            return j.message, '', ('finished', stage, j.total_ms, j.resets,
                                   _('P%s today') % rank if rank else _('Sending...') if signed else _('Sign in to submit'), ACC_TEXT)
        if j.state in ('dnf', 'invalid'):
            return j.message, '', (j.state, stage, j.result['clockMs'], j.result['resets'], i18n.cap(local(j.result['reason'])), BAD)
        cond = conditions(ch)
        if j.state == 'armed':
            # (READY in green only for the run that counts: grey for one that won't)
            if self._needs_stake(ch.get('slot', 1)):
                return j.message, '', ('ready_off', stage, 0, 0, _('NO STAKE · stake at DRIVE in ACR Daily first'), BAD)
            if self._driven(ch.get('slot', 1)):      # (in any mode: a Rally Weekend's wouldn't count either)
                return j.message, '', ('ready_off', stage, 0, 0, DRIVEN_LINE, SOFT)
            if COMMIT_REQUIRED and not self._committed(ch.get('slot', 1)):
                return j.message, '', ('ready_off', stage, 0, 0, UNCOMMITTED_LINE, BAD)
            if dd.get('rw_pre') is False:            # (not the daily's Rally Weekend)
                return j.message, '', ('ready_off', stage, 0, 0, PRACTICE_LINE, MUTED)
            if dd.get('changed_pre'):                # (its settings changed in the game's menu: the game mod read them)
                return j.message, '', ('ready_off', stage, 0, 0) + self.problems_line(dd['changed_pre'])
            return j.message, '', ('ready', stage, 0, 0, COUNTS_LINE, SLOW)
        # waiting
        if f is None:
            return _('Waiting for Assetto Corsa Rally'), '', ('standby', 'ACR DAILY', 0, 0, _('Waiting for the game'), MUTED)
        if j.approaching:
            if dd.get('rw_pre') is False:
                return j.message, '', ('standby', stage, 0, 0, PRACTICE_LINE, MUTED)
            if dd.get('changed_pre') and not self._driven(ch.get('slot', 1)):
                return j.message, '', ('standby', stage, 0, 0) + self.problems_line(dd['changed_pre'])
            if not self._driven(ch.get('slot', 1)):
                if COMMIT_REQUIRED and not self._committed(ch.get('slot', 1)):
                    return j.message, '', ('standby', stage, 0, 0, UNCOMMITTED_LINE, BAD)
                return j.message, '', ('standby', stage, 0, 0, _('Drive up to the start line · this run counts'), SLOW)
            return j.message, '', ('standby', stage, 0, 0, _('Drive up to the start line'), SOFT)
        if f.track and not (same_track(f.track, ch) and same_car(f.car, ch)):
            return (j.message, _('The game reports: %s · %s') % (f.track, f.car or '?'),
                    ('standby', _('NOT A DAILY STAGE'), 0, 0, _('Load daily %s') % today, MUTED))
        if f.clock_ms > 0:
            return j.message, '', ('standby', stage, 0, 0, _('Restart the stage to take part') + ((' ' + _('· set:') + ' ') + cond if cond else ''), MUTED)
        return j.message, '', ('standby', stage, 0, 0, _('Load %s') % today, MUTED)

    def _norally_line(self, d):
        """The timer's line for a daily's run that doesn't count (norally): why, and its colour."""
        why = d.get('practice_why')
        if why == 'settings':
            return self.problems_line(d.get('changed'))
        return (UNCOMMITTED_LINE if why == 'uncommitted' else PRACTICE_LINE), MUTED

    def _next_to_offer(self, slot):
        """After a run of daily `slot`: the other daily to offer (always on), or None (a practice run, the other one
        already driven or already offered today)."""
        d = self.dailies.get(slot) or {}
        if d.get('practice'):
            return None
        for other, od in sorted(self.dailies.items()):
            key = (od.get('ch') or {}).get('id')
            if other == slot or not od.get('judge') or self._driven(other) or key in self._offered:
                continue
            self._offered.add(key)
            return other
        return None

    def _offer_next(self, slot, other, ev, since=None):
        """After a daily's run, once its time is on the server: one card under the timer, the comment on the run
        (commentui.py) and DRIVE on the other daily (unless it got started or driven meanwhile). Without a comment to
        offer (the server's answer not in after COMMENT_WAIT_S), the other daily's DRIVE alone."""
        if (self.dailies.get(slot) or {}).get('voided'):        # (that run didn't count: this daily first, _void_daily)
            self._next_pending.discard(slot)
            return
        # its DRIVE restarts the game: once this run's time is in
        if any(a['slot'] == slot and a.get('kind', 'daily') == 'daily' for a in self.awaiting):
            self.root.after(OFFICIAL_CHECK_MS, lambda: self._offer_next(slot, other, ev))
            return
        mine_on = ((self.dailies.get(slot) or {}).get('ch') or {}).get('id')
        o = self.comment_offer if self.comment_offer and mine_on and self.comment_offer['on'] == mine_on else None
        now = time.monotonic()
        since = now if since is None else since
        if o is None and self.s.get('token') and now - since < COMMENT_WAIT_S:   # (the server's answer: a moment more)
            self.root.after(OFFICIAL_CHECK_MS, lambda: self._offer_next(slot, other, ev, since))
            return
        self._next_pending.discard(slot)
        if any(x.get('judge') and x['judge'].state == 'running' for x in self.dailies.values()):
            return                                              # (driving again already: no card over it)
        j = (self.dailies.get(slot) or {}).get('judge')
        if ev == 'finished' and j and j.state == 'dnf':         # (no official time from the game after all)
            ev = 'dnf'
        od = self.dailies.get(other)
        # (0.2: no next daily's DRIVE on a card: back in the game's menu, ACR DAILY opens on the dailies, appui.lua)
        drive = self._card_drive(other) if od and not self._driven(other) and not self.in_game_app() else None
        title = self._run_title(slot, ev)
        fg = WHITE if ev == 'finished' else BAD
        if o and self.open_comment(o, title=title, drive=drive, title_fg=fg):
            return
        if not drive:
            return
        if getattr(self, 'next_card', None):
            self.next_card.close()
        ch = od['ch']
        self.next_card = nextcard.NextCard(
            self.root, self._card_at(), title, _('Next: SS%d · %s') % (other, stage_name(ch)),
            ' · '.join(x for x in (ch.get('car'), conditions(ch)) if x), drive[0], drive[1], title_fg=fg)

    def _card_drive(self, other):
        """The next daily's DRIVE on a card (its words, what it does), or None: none to offer. With a stake to make,
        its words say it and pressing it (F8 in the game too) is the yes: no question's window, which sat unseen behind
        the game (19 Nov 2026). A stake that can't be made now: its DRIVE says why in a window, so while the game draws
        the cards, none."""
        offer = self._stake_offer(other)
        if offer is None or (offer[0] == 'no' and not self.ingame_drawn()):
            return _('DRIVE SS%d ›  restarts the game') % other, lambda: self.drive_click(other, confirm=False)
        if offer[0] == 'no':
            return None
        return (_('DRIVE SS%d ›  stake %d credits, restarts the game') % (other, offer[1]),
                lambda: self.drive_click(other, confirm=False, agreed=True))

    def _rules_banner(self, parent, k=1.0):
        """Over the daily cards, in red (RULES_LOUD): a daily counts only in the Rally Weekend, after START OFFICIAL
        RALLY, and how. Its lines wrap at the window's width."""
        box = tk.Frame(parent, bg=ACC)
        box.pack(fill='x', padx=round(20 * k), pady=(0, round(10 * k)))
        head = tk.Label(box, text=RULES_BANNER, bg=ACC, fg=WHITE, font=(FONT_C, 15), anchor='w', justify='left')
        head.pack(anchor='w', fill='x', padx=round(12 * k), pady=(round(8 * k), 0))
        sub = tk.Label(box, text=RULES_BANNER_SUB, bg=ACC, fg=WHITE, font=(FONT, 10), anchor='w', justify='left')
        sub.pack(anchor='w', fill='x', padx=round(12 * k), pady=(round(2 * k), round(8 * k)))

        def wrap(e):
            w = max(200, e.width - round(24 * k))
            if head.cget('wraplength') != w:
                head.configure(wraplength=w)
                sub.configure(wraplength=w)
        box.bind('<Configure>', wrap)
        self._rules_box = box
        return box

    def _rules_alert(self):
        """The timer window on a Rally Weekend daily's start line (or driving up to it), not driven yet (RULES_LOUD):
        what makes the run count, in red until START OFFICIAL RALLY is pressed (or while the save says the game is in
        another mode), then in orange. A league stage's start line (_league_rules_alert) and a time trial stage's
        (_tt_rules_alert): what's wrong in the game for them. -> (heading, points, kind) for Overlay.set_alert, or None."""
        target = getattr(self, 'drive_target', 'daily')
        if target == 'league':
            return self._league_rules_alert() if hasattr(self, '_league_rules_alert') else None
        tt = self._tt_rules_alert() if getattr(self, 'tt', None) and hasattr(self, '_tt_rules_alert') else None
        if tt:
            return tt
        if not RULES_LOUD or target != 'daily':
            return None
        for slot, d in sorted((getattr(self, 'dailies', None) or {}).items()):
            j = d.get('judge')
            if j is None or not (j.state == 'armed' or getattr(j, 'approaching', False)):
                continue
            if not is_weekend(d.get('ch') or {}) or self._driven(slot):
                continue
            if COMMIT_REQUIRED and not self._committed(slot):
                return START_HEAD_UNCOMMITTED, START_UNCOMMITTED, 'stop'
            if d.get('rw_pre') is False:
                return START_HEAD_NORALLY, START_NORALLY, 'stop'
            if d.get('changed_pre'):                   # (the race's settings changed in the game's menu: the game mod)
                return self.problems_alert(d['changed_pre'], self.check_rows(d['ch'].get('weekend')))
            if not COMMIT_REQUIRED and d.get('rw_pre') is True:     # (the game mod says: its Rally Weekend)
                ok = (self.check_ok_line(d['ch'].get('weekend')),) if d.get('changed_pre') == [] else ()   # (the pre-start
                # check read, all as it must be: the conditions named)
                return START_HEAD_COMMITTED, ok + START_COMMITTED[1:], 'warn'
            if not COMMIT_REQUIRED:                    # (nothing to press, the mode not known: what makes it count)
                return START_HEAD_WEEKEND, START_WEEKEND, 'warn'
            return START_HEAD_COMMITTED, START_COMMITTED, 'warn'
        return None

    def _committed(self, slot):
        """Has START OFFICIAL RALLY been pressed for today's daily `slot`, for its next run?"""
        d = self.dailies.get(slot) or {}
        c = d.get('committed')
        return bool(c and c.get('date') == (d.get('ch') or {}).get('date'))

    def commit_offer(self, slot):
        """The commit card for daily `slot` (as the next daily's: under the timer, it takes clicks): START OFFICIAL RALLY
        makes its next run the official one. Offered after DRIVE and on its start line, while it is neither committed
        nor driven (its first counted run done: later runs are practice anyway)."""
        d = self.dailies.get(slot) or {}
        ch = d.get('ch')
        if not COMMIT_REQUIRED or not ch or self._committed(slot) or self._driven(slot):
            return None
        card = getattr(self, 'commit_card', None)
        if card is not None and card.alive:
            if getattr(card, 'slot', None) == slot:
                return card
            card.close()
        ov = getattr(getattr(self, 'overlay', None), 'win', None)
        try:
            at = (ov.winfo_x(), ov.winfo_y() + ov.winfo_height() + 8) if ov is not None and ov.winfo_ismapped() else (60, 60)
        except tk.TclError:
            at = (60, 60)
        card = self.commit_card = nextcard.NextCard(
            self.root, at, _('OFFICIAL RALLY · SS%d') % slot, stage_name(ch),
            ' · '.join(x for x in (ch.get('car'), conditions(ch)) if x), _('START OFFICIAL RALLY  ›'),
            lambda s=slot: self.commit(s), title_fg=FG2, close_s=None,      # (the banner over it is the red one)
            note=COMMIT_RULES if RULES_LOUD and is_weekend(ch) else COMMIT_NOTE, loud=RULES_LOUD and is_weekend(ch),
            banner=COMMIT_BANNER if RULES_LOUD and is_weekend(ch) else None)
        card.slot = slot
        return card

    def _close_commit(self, slot):
        card = getattr(self, 'commit_card', None)
        if card is not None and getattr(card, 'slot', None) == slot:
            card.close()

    def commit(self, slot):
        """START OFFICIAL RALLY: daily `slot`'s next run is the official one. Too late once its stage clock runs (that
        run stays practice), nothing to commit to once it is driven."""
        d = self.dailies.get(slot) or {}
        ch, j = d.get('ch') or {}, d.get('judge')
        if j is not None and j.state == 'running':
            self.sub_l.configure(text=_('Too late for this run: it started before START OFFICIAL RALLY, so it is practice. '
                                        'Press it before your next run.'))
            return False
        if self._driven(slot):
            self.sub_l.configure(text=_('SS%d is driven already: your official run is your result.') % slot)
            return False
        d['committed'] = {'date': ch.get('date'), 'at': time.time()}
        waiting.note('daily:%s/%d: START OFFICIAL RALLY pressed' % (ch.get('date') or '', slot))
        if RULES_LOUD and is_weekend(ch):
            self.sub_l.configure(text=_('SS%d will count. Start it in Rally Weekend mode (Racing › Rally › Rally Weekend › '
                                        "START RALLY); in other modes it won't count. Once the clock starts, restarting "
                                        'or quitting is a DNF.') % slot)
        else:
            self.sub_l.configure(text=_('SS%d: your next run on it is the official one. A restart or quitting is a DNF.') % slot)
        return True

    def _driven(self, slot):
        """Has this daily already been started (by this app, a run on this PC not sent yet included, or is there a
        result on the board)?"""
        d = self.dailies.get(slot) or {}
        me = self.s.get('steamId')
        if d.get('started_once'):
            return True
        on_board = any(e.get('steamId') == me for e in (d.get('board') or {}).get('entries', [])) if me else False
        cid = (d.get('ch') or {}).get('id')
        # a run of it on this PC (under this Steam account, as far as the game said), or one waiting for its official
        # time: a stake can't come after it (only the first run counts)
        # (a practice run outside the Rally Weekend waiting in case the game saved it after all: not a start)
        here = bool(cid) and (any(c == cid and (not me or not ids or me in ids) for c, ids in self.local_runs) or
                              any((a.get('result') or {}).get('challengeId') == cid for a in self.awaiting
                                  if not a.get('practice')))
        # (a run without the stake the wager daily needs never counted: not a start)
        d['started_once'] = on_board or here or \
            bool(d.get('judge') and d['judge'].state in ('running', 'finished', 'dnf', 'invalid') and not d.get('unstaked')
             and not d.get('norally'))
        return on_board or here

    # -------------------------------------------------------------- credits (a prototype: server src/credits.js)

    def refresh_credits(self):
        """(thread) The driver's credits; today's bonus claimed on the way (the app coming back counts as the visit)."""
        if not self.api.configured or not self.s.get('token'):
            self._set_credits(None)
            return

        def go():
            c, msg = self._fetch_credits()
            if c is not None:
                ui(self.root, self._set_credits, c, msg)
        threading.Thread(target=go, daemon=True).start()

    def _fetch_credits(self):
        """(thread) /api/credits, today's bonus claimed on the way. -> (credits, bonus message), (None, '') offline."""
        try:
            c = self.api.credits()
        except ApiError:
            return None, ''
        if not isinstance(c, dict):
            return None, ''
        msg = ''
        if c.get('enabled') and c.get('signedIn') and c.get('claimable'):
            try:
                r = self.api.claim_credits() or {}
            except ApiError:
                r = {}                                # (claimed next time: the balance is still worth showing)
            if r.get('claimed'):
                c = dict(c, balance=r.get('balance', c.get('balance')), streak=r.get('streak', c.get('streak')), claimable=False)
                msg = _('%s: +%d credits. You have %d.') % (_('Welcome and daily bonus') if r.get('welcome') else _('Daily bonus'),
                                                         r.get('amount') or 0, c.get('balance') or 0)
        return c, msg

    def _set_credits(self, c, msg=''):
        if not self.s.get('token'):                # (signed out since they were asked for: not this driver's)
            c, msg = None, ''
        if c and c.get('name') and c['name'] != self.s.get('name'):   # (a name of their own, set on their driver page)
            self.s['name'] = c['name']
            settings.save(self.s)
        self.credits = c
        self._account_ui()
        self._render_driver()                      # (the balance by the coin, in the driver strip: tabsui.py)
        self._wager_marks()
        if msg and not self._driving():
            self.sub_l.configure(text=msg)

    def _wager_entered(self, ch):
        """Has the driver staked on this wager daily? (The credits' wager is today's: after midnight UTC, until they
        are fetched again, it is yesterday's, not this one.)"""
        w = (self.credits or {}).get('wager') or {}
        return bool(w.get('entered') and w.get('slot') == ch.get('slot') and w.get('date') == ch.get('date'))

    def _wager_marks(self):
        """The wager daily's card says so, in a strip under it: the stake that drives it (with the coin), or that we
        have staked."""
        for slot, c in self.cards.items():
            lbl = c.get('wager')
            if lbl is None:
                continue
            ch = (self.dailies.get(slot) or {}).get('ch') or {}
            text, fg = '', ACC_TEXT
            if ch.get('wager') and (self.credits or {}).get('enabled'):
                staked = self._wager_entered(ch) or (self.dailies.get(slot) or {}).get('staked')
                text = (_('WAGER DAILY  ·  STAKED: %d') if staked else _('WAGER DAILY  ·  STAKE TO DRIVE: %d')) % ch['wager']['stake']
                fg = GOOD if staked else ACC_TEXT
            if lbl.cget('text') != text or lbl.cget('fg') != fg:
                lbl.configure(text=text, fg=fg, image=(self.coin_img or '') if text else '')
            if text and not lbl.winfo_manager():
                lbl.pack(fill='x')
            elif not text and lbl.winfo_manager():
                lbl.pack_forget()
        if getattr(self, '_daily_row', None) is not None:     # (the card beside it as tall, its strip and all)
            self._daily_row.even()

    def _needs_stake(self, slot):
        """Would a run on this daily now not count for want of a stake? (The wager daily, credits on and in, not staked;
        credits not in yet: it may count, the server decides.)"""
        d = self.dailies.get(slot) or {}
        ch, c = d.get('ch') or {}, self.credits
        return bool(ch.get('wager') and c and c.get('enabled') and c.get('signedIn') and not d.get('staked')
                    and not self._wager_entered(ch))

    def _stake_offer(self, slot):
        """Daily `slot`'s stake as DRIVE stands now: None (none to make: not the wager daily, credits off, staked
        already), ('stake', amount) (DRIVE stakes it; the credits may not be in yet), or ('no', why) (it can't be made
        now: DRIVE stops)."""
        d = self.dailies.get(slot) or {}
        ch = d.get('ch') or {}
        w, free = ch.get('wager'), 3 - slot
        if not w or not self.api.configured:
            return None
        if not self.s.get('token') or (self.credits is not None and not self.credits.get('signedIn')):
            return 'no', _('SS%d costs a %d credit stake. Sign in with Steam first.') % (slot, w['stake'])
        c = self.credits
        if c is None:                              # (not in yet: asked for at DRIVE, _credits_first)
            return 'stake', w['stake']
        if not c.get('enabled') or d.get('staked') or self._wager_entered(ch):
            return None
        if not c.get('earning', True):
            return 'no', (_('SS%d costs a %d credit stake. Finish SS%d first and you get %d credits.')
                          % (slot, w['stake'], free, c.get('nextBonus') or w['stake']))
        if (c.get('balance') or 0) < w['stake']:
            return 'no', (_('SS%d costs a %d credit stake and you have %d.\n\nYou get more each day, and for finishing SS%d.')
                          % (slot, w['stake'], c.get('balance') or 0, free))
        return 'stake', w['stake']

    def _wager_first(self, slot, then, agreed=False):
        """DRIVE on the wager daily, its questions answered: it is driven with a stake, so the stake is asked for here
        (before the first run on it). -> True to go on with DRIVE now (staked already, or not the wager daily); else
        DRIVE stops here (no stake), or then() is called once the stake is in (or the credits, if DRIVE came before
        them). agreed: not asked (the DRIVE pressed said the stake: the next daily's card, its key in the game, where a
        question's window would sit unseen behind the game, 19 Nov 2026)."""
        d = self.dailies.get(slot) or {}
        ch = d.get('ch') or {}
        offer = self._stake_offer(slot)
        if offer is None:
            return True
        if offer[0] == 'no':
            messagebox.showinfo('ACR Daily', offer[1])
            return False
        if self.credits is None:
            self._credits_first(slot, then, agreed)   # (not in yet, or not reachable last time: asked for now)
            return False
        w, c = ch['wager'], self.credits
        if not agreed and not messagebox.askyesno(
                'ACR Daily', _('Stake %d credits on SS%d? You have %d.\n\nThe faster half get %d back.')
                % (w['stake'], slot, c.get('balance') or 0, 2 * w['stake'])):
            return False
        self._drive_wait = _('Staking on SS%d... DRIVE goes on once the stake is in.') % slot
        self.sub_l.configure(text=self._drive_wait)
        date = ch.get('date')

        def go():
            try:
                r = self.api.wager(slot, date)
            except Exception as e:             # (an ApiError; anything else must not leave DRIVE waiting either)
                ui(self.root, self._stake_failed, slot, e)
                return
            ui(self.root, self._staked, slot, r, then)
        threading.Thread(target=go, daemon=True).start()
        return False

    def _staked(self, slot, r, then):
        """The stake is in: DRIVE goes on without asking again (everything was asked before the stake)."""
        self._drive_wait = None
        d = self.dailies.get(slot)
        if d:
            d['staked'] = True
        self._wager_marks()
        self.refresh_credits()
        self._drive_resume(then, _('Staked on SS%d%s.') % (slot, (' ' + _('(%s credits left)')) % r['balance']
                                                     if isinstance(r, dict) and r.get('balance') is not None else ''),
                           self._stake_stands(slot))

    def _stake_failed(self, slot, e):
        """The stake didn't go through, or no answer came. DRIVE stops; the next DRIVE asks again, unless the credits
        now show it went in."""
        self._drive_wait = None
        self.refresh_credits()
        code = getattr(e, 'code', None)
        if code is None or code >= 500:            # no answer (or a broken one): the server may have taken it
            text = (_('No answer from the server (%s). The stake may have gone through; SS%d will say STAKED if it did.'
                    '\n\nClick DRIVE again.') % (e, slot))
        else:
            text = _('Not staked: %s') % e
        messagebox.showwarning('ACR Daily', text)

    def _credits_first(self, slot, then, agreed=False):
        """DRIVE on the wager daily before the credits are in: they are fetched first, then the stake is offered."""
        self._drive_wait = _('Getting your credits... DRIVE goes on in a moment.')
        self.sub_l.configure(text=self._drive_wait)

        def go():
            try:
                c, msg = self._fetch_credits()
            except Exception:                  # (DRIVE must not stay waiting for them)
                c, msg = None, ''
            ui(self.root, self._credits_in, slot, c, msg, then, agreed)
        threading.Thread(target=go, daemon=True).start()

    def _credits_in(self, slot, c, msg, then, agreed=False):
        self._drive_wait = None
        if c is None:
            messagebox.showwarning('ACR Daily', _('Couldn\'t load your credits. Try DRIVE on SS%d again in a moment.') % slot)
            return
        self._set_credits(c, msg)
        if self.credits is not None and self._wager_first(slot, then, agreed):    # (None: signed out meanwhile)
            self._drive_resume(then)

    def _drive_resume(self, then, said='', stands=''):
        """DRIVE going on after a wait on the server (a stake, the credits), unless a run or a restart
        started meanwhile (the game is never closed under it)."""
        if self._driving() or getattr(self, '_restarting', False):
            self.sub_l.configure(text=(said + ' ' if said else '') + _('DRIVE stopped: a run started meanwhile. Try again after it.') + stands)
            return
        if said:
            self.sub_l.configure(text=said)
        then()

    def _stake_stands(self, slot, sep=' '):
        """What to add when DRIVE stopped after the stake went in: it stands ('' if there is none)."""
        d = self.dailies.get(slot) or {}
        if (d.get('staked') or self._wager_entered(d.get('ch') or {})) and not self._driven(slot):
            return sep + _('Your SS%d stake is in.') % slot
        return ''

    def refresh_routes(self):
        if not self.api.configured:
            return

        def go():
            try:
                # stages with a driven route; estimated ones (from the game's files) still take the first clean run
                self.known_routes = {norm(r['track']) for r in self.api.routes() if not r.get('estimated')}
            except (ApiError, KeyError, TypeError):
                pass
        threading.Thread(target=go, daemon=True).start()

    def _contribute(self, rec):
        """A clean run just finished: if its stage has no route yet, it becomes the stage's route."""
        if not rec or self.known_routes is None or norm(rec['track']) in self.known_routes:
            return
        if not self.s.get('token') or not self.api.configured:
            return
        self.known_routes.add(norm(rec['track']))      # once per stage per session
        stage_id = None
        try:   # the game's own stage id, from its save (only if the save's car is the car just driven)
            setup = saveslot.read_setup(saveslot.read_save_idle())   # (just after a finish: the game may write it)
            if same_car(rec['car'], {'carId': setup['car'][1].decode()}):
                stage_id = setup['stage'][1].decode()
        except (OSError, saveslot.SaveError):
            pass

        def go():
            try:
                r = self.api.contribute_route(rec, stage_id)
                msg = (_('New stage recorded: %s (%.1f km). It joins the dailies once it is checked.') % (rec['track'], r['length'] / 1000)
                       if r.get('added') and r.get('checked') is False else       # (a new stage: the admin turns it on)
                       _('New stage recorded: %s (%.1f km). It joins the daily rotation.') % (rec['track'], r['length'] / 1000)
                       if r.get('added') else '')
            except ApiError as e:
                msg = _('Route of %s not used: %s') % (rec['track'], e)
            if msg:
                ui(self.root, self.sub_l.configure, {'text': msg})
        threading.Thread(target=go, daemon=True).start()

    def _others_shown(self):
        """Is the display that shows the other drivers (the stage strip) on screen?"""
        shown = getattr(self, '_ov_ok', {}).get('strip', getattr(self, '_ov_allowed', True))
        return bool(shown and self.widgets['strip'].cfg.get('visible'))

    def _live_every_s(self):
        """How often to fetch who else is on the active daily's stage, for the displays: the server's livePollS while
        the game is on that stage (start line, results), its liveIdleS anywhere else; None (not at all) while no
        display shows them, or while we drive signed in: then they come back with our own position (_send_live)."""
        if not self._others_shown():
            return None
        j = (self.dailies.get(self.active) or {}).get('judge')
        if j and j.state == 'running' and self.s.get('token'):
            return None
        return self.timing('livePollS') if j and j.state != 'waiting' else self.timing('liveIdleS')

    def _game_open(self):
        """Is the game open (on a stage or in its menus)? Its telemetry was there in the last GAME_GONE_S."""
        return getattr(self, 'last_frame', None) is not None or \
            time.monotonic() - getattr(self, '_game_at', -1e9) < GAME_GONE_S

    def poll_live(self):
        """Who else is on the active daily's stage, for the displays (as often as _live_every_s says); on a time trial
        stage's, ttui.py asks. Never while the game is closed: an app left open all day with its displays shown asked
        every liveIdleS (5,760 requests a day at 15 s), and the free plan allows 100,000 for everyone."""
        self.root.after(1000, self.poll_live)
        if not self._game_open():
            for x in list(self.dailies.values()) + list(self.tt.values()):
                x.pop('live', None)           # (nobody asked for, nobody shown: not the last ones, standing still)
            return
        if self._tt_poll_live():
            return
        every = self._live_every_s()
        d = self.dailies.get(self.active)
        if every is None or not d or not self.api.configured or getattr(self, '_live_busy', False) \
                or time.monotonic() - getattr(self, '_live_polled', -1e9) < every:
            return
        self._live_polled = time.monotonic()
        self._live_busy = True

        def go():
            try:
                self._take_live(d, self.api.live_now(d['ch']['date'], self.active).get('drivers', []))
            except ApiError:
                pass
            finally:
                self._live_busy = False
        threading.Thread(target=go, daemon=True).start()

    def _take_live(self, d, drivers):
        """Who is on the daily's stage now (poll_live, or the answer to our own position): for the displays."""
        chosen = {str(x.get('steamId')): x['look']['color'] for x in drivers if (x.get('look') or {}).get('color')}   # (the shop)
        d['live_colours'] = widgets.colours([x.get('steamId') for x in drivers], chosen)   # same set as the website
        d['live'] = [x for x in drivers if x.get('steamId') != self.s.get('steamId')]

    def _render_widgets(self, f):
        """What the optional displays show, for the active daily."""
        vis = {k: w for k, w in self.widgets.items() if w.cfg.get('visible')}
        if not vis:
            return
        view = self._league_widget_view(f)          # following a league event: its stage
        if view is None:
            view = self._tt_widget_view(f)          # a time trial stage (ttui.py)
        self._hud_view = view                       # (the stage strip in the game: ticks under its km bar, ingamehud.py)
        if view is not None:
            for w in vis.values():
                try:
                    w.render(view)
                except Exception:
                    import traceback
                    traceback.print_exc()
            return
        d = self.dailies.get(self.active) or {}
        j, ch, gs = d.get('judge'), d.get('ch') or {}, d.get('ghosts')
        running = bool(j and j.state == 'running')
        my_idx = j._max_idx if running else 0
        my_total = j.total_ms if running else 0
        entries = [e for e in (d.get('board') or {}).get('entries', []) if e.get('totalMs') is not None]
        me = self.s.get('steamId')
        me_run = next((e['runId'] for e in entries if e.get('steamId') == me), None)
        p1_run = entries[0]['runId'] if entries else None
        picked = gs.pick(my_idx, my_total, me_run, p1_run) if gs else []
        cols = d.get('live_colours') or {}
        live_now = [x for x in d.get('live') or [] if x.get('state') == 'live']
        view = {
            'slot': ch.get('slot'), 'running': running,
            'splits': j.split_at if j else [],
            'progress': j.progress if running else (0.0 if j else None),
            'ghosts': [(lab, kind, g.progress_at(my_total), gap if running else None) for lab, kind, g, gap in picked],
            'gap_p1': j.gap_ms if running else None, 'p1_name': d.get('ghost_name'),
            'others_prog': [(shown_name(x), cols.get(str(x.get('steamId')), widgets.FG2), x.get('progress') or 0.0, x.get('avatar'))
                            for x in live_now],
        }
        self._hud_view = view
        for w in vis.values():
            try:
                w.render(view)
            except Exception:
                import traceback
                traceback.print_exc()

    def _send_live(self, slot, j, f, state):
        """Our position for the website's live map (every liveSendS while on stage, plus start / finish / DNF). With a
        display showing the other drivers, the answer brings them too (no second request)."""
        self.live_at = time.monotonic()
        if not self.s.get('token') or not self.api.configured or f is None:
            return
        if (self.dailies.get(slot) or {}).get('unstaked'):   # (the server takes the wager daily's only with a stake)
            return
        if (self.dailies.get(slot) or {}).get('norally'):    # (practice: the server must not take it for the first start)
            return
        others = self._others_shown()
        body = {'challengeId': j.ch.get('id'), 'x': round(f.x, 1), 'z': round(f.z, 1), 'progress': round(j.progress, 4),
                'totalMs': j.total_ms, 'resets': j.resets, 'state': state,
                'startedAt': getattr(j, '_start_wall', None), 'country': self.country, 'others': others}
        d = self.dailies.get(slot)

        def go():
            r = self.api.live(body)
            if others and d is not None and r and isinstance(r.get('drivers'), list):
                self._take_live(d, r['drivers'])
        threading.Thread(target=go, daemon=True).start()

    def _standing(self, title, my_ms, split, hold):
        st = standing((self.board or {}).get('entries', []), self.s.get('steamId'), my_ms, split)
        self.overlay.show_standing(title, st)
        self.panel_until = time.monotonic() + hold if hold else 0
        self.panel_slot = self.active

    def _clear_standing(self):
        """No standings under the timer."""
        self.overlay.show_standing('', None)
        self.panel_until = 0
        self.panel_slot = None

    def _drop_stale_standing(self, f=None):
        """A daily's standings (its split, its finish) are that daily's: gone once the app follows a league event, a 1V1 or
        a cup match, another daily is the one on screen, or the game (frame f) is on another stage, which it is before
        the app has made the next daily the one (15 Nov 2026: daily 1's finish still under the timer on daily 2: DRIVE's
        restart of the game, a set-up that stopped half way). A finish's stay up while its daily's stage is the one.
        A time trial stage's (panel_slot ('tt', slot)) are gone once its frames are another's, or another stage is driven."""
        ps = getattr(self, 'panel_slot', None)
        if ps is None:
            return
        if isinstance(ps, tuple):
            j = ((getattr(self, 'tt', None) or {}).get(ps[1]) or {}).get('judge')
            stale = not self._tt_judged() or self.tt_active != ps[1]
        else:
            d = (getattr(self, 'dailies', None) or {}).get(ps) or {}
            ch, j = d.get('ch'), d.get('judge')
            # (the game's name for the stage as the judge took it, recognised by its start line, is the daily's too)
            alias = getattr(j, '_track_alias', None) if j is not None else None
            stale = (not self._dailies_judged() or self.active != ps or
                     bool(f is not None and getattr(f, 'track', None) and ch and not same_track(f.track, ch)
                          and f.track != alias))
        # (its car on a start line again, the next run on its way: that one's, not the last one's)
        if stale or (j is not None and (getattr(j, 'state', None) in ('waiting', 'armed') or getattr(j, 'approaching', False))):
            self._clear_standing()

    def _my_rank(self):
        for e in (self.board or {}).get('entries', []):
            if e.get('steamId') == self.s.get('steamId'):
                return e['rank']
        return None


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # sharp text on high-DPI screens
    except Exception:
        pass
    try:
        # Check the server's certificate the way Windows (and the browser) does. On its own Python trusts only the
        # root certificates Windows has already cached: a PC without the current Let's Encrypt root, but with its
        # old expired one, got "certificate has expired" from the server. Windows fetches a missing root itself.
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    # one copy at a time (single.py): the updater's new one waits for the old one to quit
    again = '--updated' in sys.argv or '--restarted' in sys.argv     # (--restarted: a new language, settingsui.py)
    if not single.acquire(wait_s=20.0 if again else 0.0):
        single.tell_running()
        return
    App.start_hidden = True                          # (seen first as the launcher: launcher.show puts it on the screen)
    app = App()
    # real cars in the game: the game mod goes in when ghost cars want it and out when they don't (only here, never
    # in tests: it works on the real game folder)
    app.gamemod = modinstall.Keeper(app.want_game_mod)
    app.root.after(1000, app.ingame_tick)            # (the timer in the game: written only while it is on)
    # ACR DAILY inside the game (0.2): MULTIPLAYER's tile and the app's pages, drawn by the game mod (ingameapp.py, appui.lua)
    from . import ingameapp
    app.ingame_app = ingameapp.InGameApp(app, lambda p: ghostui.open_kept(p, write=True, binary=True),
                                         lambda p: ghostui.open_kept(p, binary=True))
    app.root.after(1200, app.ingame_app.tick)
    app.root.after(1500, app.ingame_app.nav_tick)
    # ... so the window opens as the launcher: a few settings and PLAY (launcher.py; FULL WINDOW: the whole window)
    from . import launcher
    app.launcher = launcher.Launcher(app)
    app.launcher.show()
    if '--updated' in sys.argv:
        app.root.after(300, app.just_updated)
    elif '--restarted' in sys.argv:
        app.root.after(300, app.to_front)
    # what's new in this version, once (whatsnew.py): after the window is up
    app.root.after(1500, lambda: whatsnew.check(app, __version__, '--updated' in sys.argv))
    app.root.mainloop()


if __name__ == '__main__':
    main()
