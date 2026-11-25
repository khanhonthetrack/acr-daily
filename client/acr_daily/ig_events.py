"""EVENTS in the game: the dailies and the time trials under one tab, as two sub-tabs (the user, 22 Nov 2026: "EVENTS
page will have two sub tabs: dailies and TT"). Each sub-tab is its own page still (ig_daily.py, ig_tt.py: their buttons
'daily.*' / 'tt.*'); ingameapp keeps the one on screen as its tab ('daily' / 'tt') and shows EVENTS lit in its header,
this bar over the page."""
from .i18n import _
from .ingamekit import row, sp, tab_id, tabs

TAB = 'events'
SUBS = (('daily', _('DAILIES')), ('tt', _('TIME TRIAL')), ('copilot', _('CODRIVER')))   # (COPILOT: ig_copilot.py)


def last(ig):
    """The sub-tab EVENTS opens on: the one last shown (DAILIES at first)."""
    sub = ig.mem(TAB).get('sub')
    return sub if sub in dict(SUBS) else 'daily'


def bar(ig):
    ig.mem(TAB)['sub'] = ig.tab
    return row(tabs(tab_id(TAB, 'sub'), SUBS, ig.tab, va='c'), sp(fill=1), pad=[0, 0, 0, 18])


def page(ig):                       # (never on screen itself: 'events' opens its sub-tab: ingameapp.click)
    m = ig.module(last(ig))
    return m.page(ig)


def click(ig, action, arg):
    if action == 'sub' and arg in dict(SUBS):
        ig.tab = arg
        ig.mem(TAB)['sub'] = arg
        ig.opened()
