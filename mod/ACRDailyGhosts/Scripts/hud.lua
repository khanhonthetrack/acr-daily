-- ACR Daily's displays, drawn by the game itself (part of the ACR Daily mod: main.lua runs M.tick every frame).
--
-- The app writes what its displays say to %APPDATA%\ACR Daily\ingame-hud.txt (client/acr_daily/ingamehud.py: its
-- words and colours, display by display); this lays them out as the game's own widgets, in the game's font and look,
-- with pictures and motion (the building blocks: hudkit.lua). Nothing sits over the game, and in VR (UEVR) they are in
-- the headset like the game's HUD:
--
--   acr     the ACR strip, docked under the game's own timer (its HUD keeps to the middle 16:9 of the screen): ACR
--           Daily's red D, whether the run counts, the place at the last split, one line (the gap to P1)
--   note    under it: what must be done now (save your time...), with a bar while the time is on its way
--   board   under it: the split's standings, its rows one after another
--   gate    RANKED's start board, top middle under the game's km bar: the series' logo, one word, the time left
--           draining, whose turn, three of the queue
--   track   the others on the stage and the ghosts: ticks under the game's km bar
--
--   ACRHUD 2 <seq> <when>                 when: the app's clock at this update (s)
--   <seq> <panel> <key> <value>           a field (value: the rest of the line; a list's cells: tabs)
--   end <seq>
-- A key that comes more than once is a list. run / left: a clock in ms at <when>, moved on here every frame. A read in
-- the middle of a write (lines of two updates) is skipped; nothing new for STALE_S: everything goes.
local UEHelpers = require("UEHelpers")
local K = require("hudkit")

local M = {}
local TAG = "[ACRDailyHud] "
local DIR = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\"
local FILE = DIR .. "ingame-hud.txt"
local STALE_S = 3.0
local AHEAD_S = 0.8              -- a running clock carried on at most this long past the app's last word
local LISTS = {row = true, point = true, split = true, other = true, ghost = true}

-- the look: the game's HUD is flat, dark, see-through, in Rajdhani; these follow it, with ACR Daily's red
local INK, PANEL, PANEL2, RULE = "0B0C10", "0B0C10", "17181D", "2B2B31"
local WHITE, SOFT, FG2, MUTED = "F4F4F5", "D4D4D8", "A1A1AA", "85858E"
local RED, GREEN, AMBER, ORANGE = "FF4655", "30D158", "FFD60A", "FF9F0A"
local LABEL = "D9D9DC"           -- the game's own grey label (its "SS 01", "POS.")

-- where the game's HUD is (1080p units, from the left of the screen's middle 16:9; measured in the game, 19 Nov 2026):
-- its timer block (flag, place, stage, the clock, POS.) ends DOCK.y down, starting DOCK.x in; its km bar runs across
-- the top middle, BAR.w wide, BAR.y down
local DOCK = {x = 86, y = 186}
local BAR = {w = 700, y = 66}

local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end

-- ---------------------------------------------------------------------- the app's file
local f, f_opened = nil, nil
local last_seq, last_new_t = nil, nil
local frame = 0

local function read_file(t)
    if not f then
        if frame % 30 ~= 1 then return nil end            -- (looked for twice a second until the app makes it)
        f = io.open(FILE, "r")
        if not f then return nil end
        f_opened = t
    end
    if not f:seek("set", 0) then
        f:close()
        f = nil
        return nil
    end
    return f:read("a")
end

local function split(s, sep)
    local out = {}
    for x in ((s or "") .. sep):gmatch("(.-)" .. sep) do out[#out + 1] = x end
    return out
end

local function parse(text)
    -- -> seq, when, panels {name -> {key -> value; lists -> {...}}}; nil when there is no whole update
    if not text then return nil end
    local seq, when = text:match("^ACRHUD 2 (%d+) ([%d%.]+)")
    if not seq then return nil end
    local stop, tail = text:match("()\nend (%d+)")
    if not stop or tail ~= seq then return nil end
    local panels = {}
    for line in text:sub(1, stop):gmatch("\n([^\n]+)") do
        local s, name, key, value = line:match("^(%d+) (%a+) ([%w_]+) ?(.*)$")
        if s then
            if s ~= seq then return nil end                 -- (a line of another update)
            local p = panels[name]
            if not p then
                p = {}
                for k in pairs(LISTS) do p[k] = {} end
                panels[name] = p
            end
            value = value:gsub("[\r ]+$", "")
            if LISTS[key] then p[key][#p[key] + 1] = value else p[key] = value end
        end
    end
    return seq, tonumber(when), panels
end

-- the app's clock mapped onto this one (as main.lua's ghosts): the smallest (read here - written there) is the gap
local offset, offset_t = nil, nil
local function app_to_here(app_t, t)
    local d = t - app_t
    if offset == nil or d < offset + (t - offset_t) * 0.001 then
        offset, offset_t = d, t
    else
        offset, offset_t = offset + (t - offset_t) * 0.001, t
    end
    return app_t + offset
end

-- ---------------------------------------------------------------------- the screen
-- the viewport in 1080p units, and where its middle 16:9 starts (the game's HUD keeps to it on a wider screen)
local WLL = nil
local screen = {w = 1920, h = 1080, left = 0, at = -1}
local function measure(t)
    if t - screen.at < 1.0 then return end
    screen.at = t
    pcall(function()
        if not (WLL and WLL:IsValid()) then WLL = StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary") end
        local world = UEHelpers.GetWorld()
        local size, sc = WLL:GetViewportSize(world), WLL:GetViewportScale(world)
        if size and sc and sc > 0 and size.X > 0 then
            screen.w, screen.h = size.X / sc, size.Y / sc
            screen.left = math.max(0, (screen.w - screen.h * 16 / 9) / 2)
        end
    end)
end

-- ---------------------------------------------------------------------- motion
-- each display comes in and goes out: v eases 0 -> 1 (in) or 1 -> 0 (out), drawn as its opacity and a slide
local function anim(dx, dy, in_s, out_s)
    return {v = 0.0, want = 0.0, dx = dx or 0, dy = dy or 0, in_s = in_s or 0.28, out_s = out_s or 0.2, shown = false}
end

local function anim_step(a, w, dt)
    if a.v ~= a.want then
        local step = dt / (a.want > a.v and a.in_s or a.out_s)
        a.v = a.want > a.v and math.min(a.want, a.v + step) or math.max(a.want, a.v - step)
    end
    local on = a.v > 0.001
    if on ~= a.shown then
        a.shown = on
        w:SetVisibility(on and K.NOT_HIT or K.COLLAPSED)
    end
    if on and a.drawn ~= a.v then
        a.drawn = a.v
        local e = a.want > 0.5 and K.out3(a.v) or a.v * a.v
        w:SetRenderOpacity(e)
        w:SetRenderTranslation({X = (1 - e) * a.dx, Y = (1 - e) * a.dy})
    end
end

-- a pop: its scale 1 + k, back to 1 over s seconds from t0 -> whether it is still moving
local function pop(w, t0, t, k, s)
    if not t0 then return false end
    local x = (t - t0) / (s or 0.35)
    local sc = x >= 1 and 1.0 or 1.0 + k * (1 - K.out3(x))
    w:SetRenderScale({X = sc, Y = sc})
    return x < 1
end

-- ---------------------------------------------------------------------- the widgets
local ui = nil                   -- every display's widgets (build); made again after a level load empties the screen
local c = {}                     -- what is set on them now (K.set: only changes are set again)

local function text(tree, size, face, colour, o)
    o = o or {}
    o.size, o.face, o.colour = size, face, colour
    return K.text(tree, o)
end

-- a label as the game's: a solid cell, its words in the middle
local function cell(tree, size, fill, colour, o)
    o = o or {}
    local b = K.panel(tree, {fill = fill, alpha = o.alpha, radius = o.radius or 2, pad = o.pad or {9, 2, 9, 2}})
    local t = text(tree, size, o.face or "bold", colour, {spacing = o.spacing or 40, shadow = o.shadow or false})
    b:SetContent(t)
    return b, t
end

-- the ACR strip, the note and the split's standings: one column, under the game's timer
local function build_column(r)
    local tree = r.tree
    local col = K.vbox(tree)
    local slot = r.canvas:AddChildToCanvas(col)
    slot:SetAutoSize(true)
    local A = {col = col, slot = slot, anim = anim(-24, 0)}

    -- the strip: [ACR Daily's logo] [● LIVE][P3 / 18] / [the line]
    local strip = K.hbox(tree)
    K.add(col, strip, {h = 1})
    A.brand = K.panel(tree, {fill = PANEL, alpha = 0.72, radius = 2, pad = {8, 5, 8, 5}})
    A.brand:SetHorizontalAlignment(2)
    A.brand:SetVerticalAlignment(2)
    K.add(strip, A.brand, {v = 0})
    local bin = K.hbox(tree)
    A.brand:SetContent(bin)
    A.brand_pic = K.image(tree, 26, 51)                         -- (the red D: as tall as the strip's two rows)
    A.brand_state = {}
    K.add(bin, A.brand_pic.box, {v = 2})
    A.brand_pic.box:SetVisibility(K.COLLAPSED)
    A.brand_t = text(tree, 17, "bold", WHITE, {spacing = 60, shadow = false, text = "ACR DAILY"})   -- (no logo file)
    K.add(bin, A.brand_t, {v = 2})
    local rows = K.vbox(tree)
    K.add(strip, rows, {pad = {3, 0, 0, 0}, v = 2})
    local row1 = K.hbox(tree)
    K.add(rows, row1, {h = 1})
    A.chip = K.panel(tree, {fill = RED, radius = 2, pad = {9, 2, 10, 2}})
    K.add(row1, A.chip, {v = 0})
    local crow = K.hbox(tree)
    A.chip:SetContent(crow)
    A.dot = K.panel(tree, {fill = WHITE, radius = 4})
    K.add(crow, K.size(tree, A.dot, 8, 8), {v = 2, pad = {0, 0, 7, 0}})
    A.chip_t = text(tree, 19, "bold", WHITE, {spacing = 60, shadow = false})
    K.add(crow, A.chip_t, {v = 2})
    A.pos, A.pos_t = cell(tree, 19, PANEL, WHITE, {alpha = 0.72, spacing = 30})
    K.add(row1, A.pos, {v = 0, pad = {3, 0, 0, 0}})
    A.line, A.line_t = cell(tree, 19, PANEL, SOFT, {alpha = 0.72, face = "semi", spacing = 10, pad = {9, 3, 10, 3}})
    local lsb = K.size(tree, A.line, nil, nil)                  -- (one line, as wide as it needs, never wider than this)
    lsb:SetMaxDesiredWidth(460.0)
    K.add(rows, lsb, {h = 1, pad = {0, 3, 0, 0}})
    A.clock, A.clock_t = cell(tree, 34, PANEL, WHITE, {alpha = 0.72, spacing = 0, pad = {9, 0, 12, 0}})
    K.add(rows, A.clock, {h = 1, pad = {0, 3, 0, 0}})
    A.strip = strip
    A.strip_anim = anim(-24, 0)

    -- the note
    local note = K.panel(tree, {fill = PANEL2, alpha = 0.92, radius = 3})
    K.add(col, K.size(tree, note, 420, nil), {pad = {0, 8, 0, 0}, h = 1})
    local nrow = K.hbox(tree)
    note:SetContent(nrow)
    A.note_edge = K.panel(tree, {fill = ORANGE})
    K.add(nrow, K.size(tree, A.note_edge, 5, nil), {v = 0})
    local nbody = K.vbox(tree)
    K.add(nrow, nbody, {pad = {14, 9, 16, 11}, fill = true})
    A.note_head = text(tree, 22, "bold", ORANGE, {wrap = true, spacing = 30})
    K.add(nbody, A.note_head)
    A.note_lines = {}
    for i = 1, 3 do
        local lr = K.hbox(tree)
        K.add(nbody, lr, {pad = {0, 4, 0, 0}})
        local dot = K.panel(tree, {fill = ORANGE, radius = 3})
        K.add(lr, K.size(tree, dot, 6, 6), {v = 1, pad = {1, 10, 10, 0}})
        local tb = text(tree, 18, "semi", WHITE, {wrap = true})
        K.add(lr, tb, {fill = true})
        A.note_lines[i] = {row = lr, dot = dot, text = tb}
    end
    A.note_bar = K.bar(tree, 380, 5, RULE, ORANGE)
    K.add(nbody, A.note_bar.outer, {pad = {0, 9, 0, 0}, h = 1})
    A.note = note
    A.note_anim = anim(-20, 0, 0.26, 0.18)

    -- the split's standings
    local bd = K.panel(tree, {fill = PANEL, alpha = 0.84, radius = 3, pad = {14, 10, 14, 12}})
    K.add(col, K.size(tree, bd, 420, nil), {pad = {0, 8, 0, 0}, h = 1})
    local bbody = K.vbox(tree)
    bd:SetContent(bbody)
    local bhead = K.hbox(tree)
    K.add(bbody, bhead)
    A.b_title = text(tree, 16, "semi", FG2, {spacing = 140})
    K.add(bhead, A.b_title, {fill = true, v = 2})
    A.b_pos = text(tree, 30, "bold", WHITE)
    K.add(bhead, A.b_pos, {v = 2})
    A.b_rows = {}
    for i = 1, 4 do
        local rb = K.panel(tree, {fill = RED, alpha = 0.0, radius = 2, pad = {7, 2, 7, 2}})
        K.add(bbody, rb, {pad = {0, i == 1 and 6 or 2, 0, 0}})
        local rr = K.hbox(tree)
        rb:SetContent(rr)
        local p = text(tree, 19, "bold", MUTED)
        K.add(rr, K.size(tree, p, 34, nil), {v = 2})
        local n = text(tree, 19, "semi", SOFT)
        K.add(rr, n, {fill = true, v = 2})
        local g = text(tree, 19, "semi", SOFT, {justify = 2})
        K.add(rr, g, {v = 2})
        A.b_rows[i] = {box = rb, pos = p, name = n, gap = g, anim = anim(-16, 0, 0.22, 0.12)}
    end
    A.b_pb = text(tree, 17, "semi", MUTED)
    K.add(bbody, A.b_pb, {pad = {0, 8, 0, 0}})
    A.board = bd
    A.board_anim = anim(-24, 0, 0.3, 0.2)
    return A
end

-- RANKED's start board: the series' logo, the stage, one word, the time left draining, whose turn, the queue
local GATE_W = 620
local function build_gate(r)
    local tree = r.tree
    local box = K.panel(tree, {fill = PANEL, alpha = 0.86, radius = 6, outline = RED, outline_w = 2})
    local slot = r.canvas:AddChildToCanvas(box)
    slot:SetAutoSize(true)
    slot:SetAnchors({Minimum = {X = 0.5, Y = 0.0}, Maximum = {X = 0.5, Y = 0.0}})
    slot:SetAlignment({X = 0.5, Y = 0.0})
    slot:SetPosition({X = 0.0, Y = BAR.y + 30.0})
    local G = {box = box, slot = slot, anim = anim(0, -40, 0.42, 0.25)}
    local body = K.vbox(tree)
    box:SetContent(K.size(tree, body, GATE_W, nil))
    -- logo | the series, the stage
    local top = K.hbox(tree)
    K.add(body, top, {pad = {20, 16, 20, 14}})
    G.logo = K.image(tree, 200, 113)
    G.logo_state = {}
    K.add(top, G.logo.box, {v = 2, pad = {0, 0, 20, 0}})
    G.logo.box:SetVisibility(K.COLLAPSED)
    local who = K.vbox(tree)
    K.add(top, who, {fill = true, v = 2})
    G.series = text(tree, 18, "semi", FG2, {spacing = 160, wrap = true})
    K.add(who, G.series)
    G.stage, G.stage_t = cell(tree, 20, LABEL, INK, {spacing = 60})
    K.add(who, G.stage, {pad = {0, 10, 0, 0}, h = 1})
    K.add(body, K.size(tree, K.panel(tree, {fill = RULE}), nil, 1), {pad = {20, 0, 20, 0}})
    -- WAIT ......... 1:20
    local mid = K.hbox(tree)
    K.add(body, mid, {pad = {20, 2, 20, 0}})
    G.head = text(tree, 72, "bold", RED, {spacing = 30})
    K.add(mid, G.head, {fill = true, v = 2})
    G.big = text(tree, 72, "bold", WHITE)
    K.add(mid, G.big, {v = 2})
    G.bar = K.bar(tree, GATE_W - 40, 8, RULE, RED)
    K.add(body, G.bar.outer, {pad = {20, 0, 20, 12}, h = 1})
    G.line = text(tree, 20, "semi", WHITE, {wrap = true})
    K.add(body, G.line, {pad = {20, 0, 20, 4}})
    -- the queue
    local q = K.vbox(tree)
    K.add(body, q, {pad = {14, 8, 14, 0}})
    G.rows = {}
    for i = 1, 3 do
        local rb = K.panel(tree, {fill = RED, alpha = 0.0, radius = 3, pad = {7, 3, 7, 3}})
        K.add(q, rb, {pad = {0, 1, 0, 1}})
        local rr = K.hbox(tree)
        rb:SetContent(rr)
        local p = text(tree, 20, "bold", MUTED)
        K.add(rr, K.size(tree, p, 36, nil), {v = 2})
        local n = text(tree, 20, "semi", SOFT)
        K.add(rr, n, {fill = true, v = 2})
        local w = text(tree, 20, "bold", SOFT, {justify = 2})
        K.add(rr, w, {v = 2})
        G.rows[i] = {box = rb, pos = p, name = n, what = w}
    end
    G.rule = text(tree, 16, "medium", MUTED, {wrap = true})
    K.add(body, G.rule, {pad = {20, 10, 20, 0}})
    -- DRIVE (the rally is out, the app not set up for it yet)
    G.drive, G.drive_t = cell(tree, 18, WHITE, INK, {spacing = 60, pad = {12, 4, 12, 4}})
    K.add(body, G.drive, {pad = {20, 12, 20, 0}, h = 1})
    K.add(body, K.size(tree, nil, nil, 16))
    return G
end

-- the others on the stage and the ghosts: ticks under the game's km bar
local function build_track(r)
    local tree = r.tree
    local cv = K.new("CanvasPanel", tree)
    local wrap = K.size(tree, cv, BAR.w, 16)
    local slot = r.canvas:AddChildToCanvas(wrap)
    slot:SetAutoSize(true)
    slot:SetAnchors({Minimum = {X = 0.5, Y = 0.0}, Maximum = {X = 0.5, Y = 0.0}})
    slot:SetAlignment({X = 0.5, Y = 0.0})
    slot:SetPosition({X = 0.0, Y = BAR.y + 0.0})
    local S = {box = wrap, slot = slot, anim = anim(0, -8)}
    local function marker(w, h, fill, o)
        o = o or {}
        local m = K.panel(tree, {fill = fill, radius = o.radius or 0, outline = o.outline, outline_w = o.outline_w})
        local ms = cv:AddChildToCanvas(m)
        ms:SetSize({X = w + 0.0, Y = h + 0.0})
        ms:SetAlignment({X = 0.5, Y = 0.5})
        if o.turn then m:SetRenderTransformAngle(45.0) end
        m:SetVisibility(K.COLLAPSED)
        return {w = m, slot = ms, x = nil, want = nil}
    end
    S.splits = {}
    for i = 1, 6 do S.splits[i] = marker(2, 8, "FFFFFF") end
    S.ghosts = {}
    for i = 1, 4 do S.ghosts[i] = marker(9, 9, "-", {outline = FG2, outline_w = 2.0, turn = true, radius = 1}) end
    S.others = {}
    for i = 1, 12 do S.others[i] = marker(10, 10, GREEN, {turn = true, radius = 1}) end
    return S
end

local function build()
    local r = K.root(50)
    if not r then return nil end
    r.col = build_column(r)
    r.gate = build_gate(r)
    r.track = build_track(r)
    for _, x in ipairs({r.col.col, r.col.strip, r.col.note, r.col.board, r.gate.box, r.track.box}) do
        x:SetVisibility(K.COLLAPSED)
    end
    for _, x in ipairs(r.col.b_rows) do x.box:SetVisibility(K.COLLAPSED) end
    c = {}
    _G.ACRDAILY_HUD_WIDGET = r.w                    -- (for working on it: the reload below takes it off first)
    log("displays made")
    return r
end

-- ---------------------------------------------------------------------- the displays, as the app says
local KIND = {good = GREEN, off = RULE, bad = RED, soft = WHITE}

local function num(x, d) return tonumber(x) or d end

local function place_column(A, hud)
    -- dock: under the game's timer; top / bottom: the middle of the screen (VR: where UEVR's plane is easiest to read)
    local key = hud.place .. "/" .. hud.scale .. "/" .. screen.w .. "x" .. screen.h
    K.set(c, "a.place", key, function()
        local k = K.clamp(num(hud.scale, 1.0), 0.6, 3.0)
        if hud.place == "top" or hud.place == "bottom" then
            local y = hud.place == "top" and 0.12 or 0.95
            A.slot:SetAnchors({Minimum = {X = 0.5, Y = y}, Maximum = {X = 0.5, Y = y}})
            A.slot:SetAlignment({X = 0.5, Y = hud.place == "top" and 0.0 or 1.0})
            A.slot:SetPosition({X = 0.0, Y = 0.0})
            A.col:SetRenderTransformPivot({X = 0.5, Y = hud.place == "top" and 0.0 or 1.0})
            A.anim.dx, A.anim.dy = 0, hud.place == "top" and -20 or 20
        else
            A.slot:SetAnchors({Minimum = {X = 0.0, Y = 0.0}, Maximum = {X = 0.0, Y = 0.0}})
            A.slot:SetAlignment({X = 0.0, Y = 0.0})
            A.slot:SetPosition({X = screen.left + DOCK.x, Y = DOCK.y + 0.0})
            A.col:SetRenderTransformPivot({X = 0.0, Y = 0.0})
            A.anim.dx, A.anim.dy = -24, 0
        end
        A.col:SetRenderScale({X = k, Y = k})
    end)
end

local function put_column(A, p, note, bd, hud, clock, t, dt)
    A.anim.want = (p or note or bd) and 1 or 0
    anim_step(A.anim, A.col, dt)
    if not A.anim.shown then return end
    place_column(A, hud)
    -- the strip
    A.strip_anim.want = p and 1 or 0
    anim_step(A.strip_anim, A.strip, dt)
    if p then
        local logo = K.picture(A.brand_pic, A.brand_state, p.logo)       -- ACR Daily's logo (its name without the file)
        K.show(c, "a.brand_t", A.brand_t, not logo)
        local colour = p.chip_bg ~= "-" and p.chip_bg or (KIND[p.kind] or WHITE)
        if A.chip_was ~= colour then
            A.chip_from = A.chip_col or K.lin(colour)
            A.chip_was, A.chip_t0, A.chip_done = colour, t, false
        end
        if not A.chip_done then                         -- (its colour comes in; the last frame sets it exactly, even
            local k = K.out3((t - (A.chip_t0 or t)) / 0.3)    -- when a hitch jumped the whole fade)
            A.chip_col = K.mix(A.chip_from or K.lin(colour), K.lin(colour), k)
            A.chip:SetBrushColor(A.chip_col)
            pop(A.chip, A.chip_t0, t, 0.12, 0.3)
            A.chip_done = k >= 1
        end
        K.tint(c, "a.chip_c", A.chip_t, p.chip_fg)
        K.say(c, "a.chip_t", A.chip_t, p.chip)
        K.show(c, "a.dot", A.dot, p.dot == "1")
        K.fill(c, "a.dot_c", A.dot, p.chip_fg)
        local pos = p.pos ~= nil and p.pos ~= ""
        K.show(c, "a.pos", A.pos, pos)
        if pos then K.say(c, "a.pos_t", A.pos_t, p.pos) end
        local line = p.line ~= nil and p.line ~= ""
        K.show(c, "a.line", A.line, line)
        if line then
            K.say(c, "a.line_t", A.line_t, p.line)
            K.tint(c, "a.line_c", A.line_t, p.line_c)
        end
        -- the clock (only when the driver asked for ours): a running one moved on here every frame, never back
        local shown = p.time
        if p.run and clock.when then
            local ms = num(p.run, 0) + math.min(AHEAD_S, math.max(0, t - clock.here)) * 1000
            if A.run_ms and ms < A.run_ms and A.run_ms - ms < 400 then ms = A.run_ms end
            A.run_ms = ms
            shown = K.clock(ms, 1)                      -- (tenths: hundredths are a blur at a glance)
        else
            A.run_ms = nil
        end
        K.show(c, "a.clock", A.clock, shown ~= nil and shown ~= "")
        if shown then
            K.say(c, "a.clock_t", A.clock_t, shown)
            K.tint(c, "a.clock_c", A.clock_t, p.time_c)
        end
    end
    -- the note: slides in; a bar while the time is on its way
    A.note_anim.want = note and 1 or 0
    anim_step(A.note_anim, A.note, dt)
    if note then
        local edge = note.edge ~= "-" and note.edge or note.head_c
        K.fill(c, "n.edge", A.note_edge, edge)
        K.fill(c, "n.bg", A.note, note.bg, 0.94)
        K.say(c, "n.head", A.note_head, note.head)
        K.tint(c, "n.head_c", A.note_head, note.head_c)
        for i, l in ipairs(A.note_lines) do
            local s = note.point[i]
            K.show(c, "n.row" .. i, l.row, s ~= nil)
            if s then
                K.say(c, "n.t" .. i, l.text, s)
                K.tint(c, "n.c" .. i, l.text, note.fg)
                K.fill(c, "n.d" .. i, l.dot, note.dot_c)
            end
        end
        K.show(c, "n.bar", A.note_bar.outer, note.bar ~= nil)
        if note.bar == "wait" then                      -- (a piece going across: nothing to measure yet)
            local x = (t % 1.6) / 1.6
            K.bar_set(A.note_bar, 0.3, note.bar_c)
            A.note_bar.fill:SetRenderTranslation({X = (x * 1.3 - 0.3) * A.note_bar.w, Y = 0.0})
            A.bar_wait = true
        elseif note.bar then
            if A.bar_wait then
                A.note_bar.fill:SetRenderTranslation({X = 0.0, Y = 0.0})
                A.bar_wait = false
            end
            K.bar_set(A.note_bar, num(note.bar, 0), note.bar_c)
        end
    end
    -- the split's standings, its rows one after another
    A.board_anim.want = bd and 1 or 0
    if bd and not A.board_was then A.board_t = t end
    A.board_was = bd ~= nil
    anim_step(A.board_anim, A.board, dt)
    if bd then
        K.say(c, "b.title", A.b_title, bd.title)
        K.say(c, "b.pos", A.b_pos, bd.pos)
        K.tint(c, "b.pos_c", A.b_pos, bd.pos:match("^P1 ") and RED or WHITE)
        for i, rw in ipairs(A.b_rows) do
            local s = bd.row[i]
            rw.anim.want = (s and t - (A.board_t or t) > 0.07 * i) and 1 or 0
            anim_step(rw.anim, rw.box, dt)
            if s then
                local x = split(s, "\t")
                local me = x[4] == "1"
                K.say(c, "b.p" .. i, rw.pos, x[1])
                K.say(c, "b.n" .. i, rw.name, x[2])
                K.say(c, "b.g" .. i, rw.gap, x[3])
                K.fill(c, "b.bg" .. i, rw.box, RED, me and 0.3 or 0.0)
                K.tint(c, "b.pc" .. i, rw.pos, me and WHITE or MUTED)
                K.tint(c, "b.nc" .. i, rw.name, me and WHITE or SOFT)
                K.tint(c, "b.gc" .. i, rw.gap, me and WHITE or SOFT)
            end
        end
        local pb = bd.pb ~= nil and bd.pb ~= ""
        K.show(c, "b.pb", A.b_pb, pb)
        if pb then
            K.say(c, "b.pb_t", A.b_pb, bd.pb)
            K.tint(c, "b.pb_c", A.b_pb, bd.pb_c)
        end
    end
end

local MODE = {ready = RED, wait = RED, turn = GREEN, ["break"] = AMBER, late = ORANGE}

local function put_gate(G, p, clock, t, dt)
    G.anim.want = p and 1 or 0
    anim_step(G.anim, G.box, dt)
    if not p then
        G.mode = nil
        return
    end
    local accent = p.accent ~= "-" and p.accent or MODE[p.mode] or RED
    -- the mode changed: its colour comes in, its word pops
    if G.mode ~= p.mode or G.accent ~= accent then
        G.from = G.colour or K.lin(accent)
        G.mode, G.accent, G.mode_t, G.col_done = p.mode, accent, t, false
    end
    local k = K.out3((t - (G.mode_t or t)) / 0.35)
    local col = K.mix(G.from or K.lin(accent), K.lin(accent), k)
    G.colour = col
    local turn = p.mode == "turn"
    if not G.col_done or turn then                     -- (the last frame of the fade sets it exactly, even after a hitch)
        local glow = turn and (0.5 + 0.5 * math.sin(t * math.pi * 2)) or 0      -- (your turn: the edge breathes)
        K.outline(G.box, col, 2.0 + 3.0 * glow)
        G.head:SetColorAndOpacity(K.slate(col))
        G.bar.fill:SetBrushColor(col)
        G.col_done = k >= 1
    elseif G.glowing then
        K.outline(G.box, col, 2.0)
    end
    G.glowing = turn
    pop(G.head, G.mode_t, t, 0.25, 0.42)
    local logo = K.picture(G.logo, G.logo_state, p.logo)
    K.show(c, "g.series", G.series, not logo)                -- (its name only without its logo: the logo says it)
    K.say(c, "g.series_t", G.series, p.series)
    K.say(c, "g.stage", G.stage_t, p.stage)
    -- one word big; a longer one (YOUR RALLY IS READY, another language's) smaller, never into the countdown
    local n = utf8.len(p.head or "") or #(p.head or "")
    K.set(c, "g.head_size", n <= 7 and 72 or (n <= 12 and 54 or 38), function(v) K.font(G.head, v, "bold", 30) end)
    K.say(c, "g.head", G.head, p.head)
    -- the time left, counted down here; its bar drains; the last five seconds each pop
    local big = p.big
    if p.left and clock.when then
        local left = num(p.left, 0) - math.max(0, t - clock.here) * 1000
        big = K.left(left)
        K.bar_set(G.bar, left / num(p.span, 1))
        local secs = math.ceil(left / 1000)
        if secs <= 5 and secs ~= G.last_sec and (p.mode == "turn" or p.mode == "wait") then G.sec_t = t end
        G.last_sec = secs
    end
    K.show(c, "g.bar", G.bar.outer, p.left ~= nil)
    K.show(c, "g.big", G.big, big ~= nil and big ~= "")
    K.say(c, "g.big_t", G.big, big)
    K.tint(c, "g.big_c", G.big, (p.mode == "turn" or p.mode == "late") and accent or WHITE)
    pop(G.big, G.sec_t, t, 0.16, 0.32)
    K.show(c, "g.line", G.line, p.line ~= nil and p.line ~= "")
    K.say(c, "g.line_t", G.line, p.line)
    for i, rw in ipairs(G.rows) do
        local s = p.row[i]
        K.show(c, "g.r" .. i, rw.box, s ~= nil)
        if s then
            local x = split(s, "\t")
            local me, state = x[5] == "1", x[4]
            K.say(c, "g.p" .. i, rw.pos, x[1])
            K.say(c, "g.n" .. i, rw.name, x[2])
            K.say(c, "g.w" .. i, rw.what, x[3])
            K.fill(c, "g.bg" .. i, rw.box, state == "turn" and GREEN or WHITE, me and 0.14 or (state == "turn" and 0.14 or 0.0))
            K.tint(c, "g.pc" .. i, rw.pos, me and WHITE or MUTED)
            K.tint(c, "g.nc" .. i, rw.name, me and WHITE or SOFT)
            K.tint(c, "g.wc" .. i, rw.what, state == "turn" and GREEN or SOFT)
        end
    end
    K.show(c, "g.rule", G.rule, p.rule ~= nil and p.rule ~= "")
    K.say(c, "g.rule_t", G.rule, p.rule)
    local drive = p.drive ~= nil and p.drive ~= ""
    K.show(c, "g.drive", G.drive, drive)
    if drive then K.say(c, "g.drive_t", G.drive_t, p.drive) end
end

local function put_track(S, p, t, dt)
    S.anim.want = p and 1 or 0
    anim_step(S.anim, S.box, dt)
    if not p then return end
    local function at(m, frac, colour)
        local on = frac ~= nil
        if on ~= m.on then
            m.on = on
            m.w:SetVisibility(on and K.NOT_HIT or K.COLLAPSED)
            if on then m.x = nil end
        end
        if not on then return end
        local want = K.clamp(frac, 0, 1) * BAR.w
        m.x = m.x and K.approach(m.x, want, 8.0, dt) or want       -- (they glide: the app's word comes in steps)
        local x = math.floor(m.x * 2 + 0.5) / 2
        if x ~= m.drawn then
            m.drawn = x
            m.slot:SetPosition({X = x, Y = 8.0})
        end
        if colour and colour ~= m.colour then
            m.colour = colour
            m.w:SetBrushColor(K.lin(colour))
        end
    end
    for i, m in ipairs(S.splits) do at(m, tonumber(p.split[i])) end
    for i, m in ipairs(S.ghosts) do
        local x = p.ghost[i] and split(p.ghost[i], "\t")
        at(m, x and tonumber(x[3]))
        if x and x[2] ~= m.ring then
            m.ring = x[2]
            K.outline(m.w, K.lin(x[2]), 2.0)
        end
    end
    for i, m in ipairs(S.others) do
        local x = p.other[i] and split(p.other[i], "\t")
        at(m, x and tonumber(x[3]), x and x[2])
    end
end

-- ---------------------------------------------------------------------- for working on it (never for players)
-- While %APPDATA%\ACR Daily\hud-dev.on exists, hud.lua and hudkit.lua are loaded again when they change on disk (their
-- widget taken off first), without restarting the game. (Not UE4SS's own hot reload: that one crashed the game.)
local DEV_FLAG = DIR .. "hud-dev.on"
local HERE = (debug.getinfo(1, "S").source or ""):match("^@(.*[/\\])") or ""
local dev = {sizes = nil, next = nil}
local DEV_COPY = rawget(_G, "ACRDAILY_HUD_COPY")  -- (this one loaded again by the first: the first one looks for changes)
_G.ACRDAILY_HUD_COPY = nil

local function dev_reload()
    if DEV_COPY then return nil end
    local flag = io.open(DEV_FLAG, "r")
    if not flag then return nil end
    flag:close()
    local sizes = ""
    for _, n in ipairs({"hud.lua", "hudkit.lua"}) do
        local h = io.open(HERE .. n, "rb")
        if h then
            sizes = sizes .. tostring(h:seek("end")) .. "/"
            h:close()
        end
    end
    if dev.sizes == nil then dev.sizes = sizes end
    if sizes == dev.sizes then return nil end
    dev.sizes = sizes
    local shown = rawget(_G, "ACRDAILY_HUD_WIDGET")         -- (the one on screen, whichever copy made it)
    if shown and shown:IsValid() then shown:RemoveFromParent() end
    _G.ACRDAILY_HUD_WIDGET = nil
    ui = nil
    package.loaded["hudkit"] = nil
    _G.ACRDAILY_HUD_COPY = true
    local ok, fresh = pcall(dofile, HERE .. "hud.lua")
    _G.ACRDAILY_HUD_COPY = nil
    log("dev: loaded again: %s", ok and "ok" or tostring(fresh))
    return ok and fresh or nil
end

-- ---------------------------------------------------------------------- every frame
local data, clock = nil, {}
local last_t = nil
local tick

function M.tick(t)
    if frame % 60 == 0 then
        local fresh = dev_reload()
        if fresh then dev.next = fresh end
    end
    if dev.next then
        frame = frame + 1
        return dev.next.tick(t)
    end
    return tick(t)
end

function tick(t)
    frame = frame + 1
    local dt = last_t and math.min(0.1, math.max(0, t - last_t)) or 0.016
    last_t = t
    local seq, when, panels = parse(read_file(t))
    if seq and seq ~= last_seq then
        -- (the first one read is only noted: a file left by an app that has since closed must not show for STALE_S as
        -- the game starts; a running app writes again within half a second)
        if last_seq ~= nil then
            last_new_t, data = t, panels
            clock.when = when
            clock.here = app_to_here(when, t)
        end
        last_seq = seq
    end
    if f and t - math.max(last_new_t or 0, f_opened or 0) > 5.0 then     -- (the file made again: opened again)
        f:close()
        f = nil
    end
    local fresh = last_new_t and t - last_new_t < STALE_S and data
    if ui and not (ui.w:IsValid() and ui.w:IsInViewport()) then           -- (a stage loaded: the viewport emptied)
        ui = nil
    end
    if not fresh then
        if ui and ui.on then
            ui.w:SetVisibility(K.COLLAPSED)
            ui.on = false
        end
        return
    end
    if not ui then
        if frame % 15 ~= 0 then return end                                -- (tried a few times a second)
        ui = build()
        if not ui then return end
        screen.at = -1
    end
    if not ui.on then
        ui.w:SetVisibility(K.NOT_HIT)
        ui.on = true
    end
    measure(t)
    local hud = data.hud or {}
    hud.place, hud.scale = hud.place or "dock", hud.scale or "1"
    put_column(ui.col, data.acr, data.note, data.board, hud, clock, t, dt)
    put_gate(ui.gate, data.gate, clock, t, dt)
    put_track(ui.track, data.track, t, dt)
end

return M
