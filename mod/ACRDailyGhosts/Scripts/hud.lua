-- ACR Daily's timer, in the game (part of the ACR Daily mod: main.lua runs it every frame).
--
-- The app's timer and its ranked turn window are windows over the game; in VR (UEVR) only the game's own picture
-- reaches the headset, with its UI on a plane in front of you. So, when the app's "timer in the game" is on, it writes
-- what they say to %APPDATA%\ACR Daily\ingame-hud.txt (about 20 times a second, the file kept open and overwritten in
-- place, as ingame-ghosts.txt) and this draws it as a widget on the game's own screen, which UEVR shows like the
-- game's HUD:
--
--   ACRHUD 1 <seq> <anchor x> <anchor y> <align x> <align y> <width> <shown 0/1> <panel colour>
--   R <seq> <row colour or ->                                   a row (a line of the timer), top to bottom
--   S <seq> <colour> <background or -> <size> <b/r>[f] <text>   a piece of it, left to right (b: bold; f: it takes the
--                                                              width left and wraps in it, so what follows sits at the
--                                                              right; none: the last piece without a background)
--   end <seq>
-- colours: RRGGBB (sRGB), or RRGGBBAA. The update's <seq> on every line: a read in the middle of a write is skipped.
-- Nothing new from the app for STALE_S: hidden.
local UEHelpers = require("UEHelpers")

local M = {}
local TAG = "[ACRDailyHud] "
local FILE = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\ingame-hud.txt"
local MAX_ROWS, MAX_SEGS = 20, 4
local STALE_S = 3.0
local COLLAPSED, NOT_HIT = 1, 3          -- ESlateVisibility: Collapsed, HitTestInvisible (never takes a click)

local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end

local f, f_opened = nil, nil             -- the app's file, kept open
local last_seq, last_new_t = nil, nil
local ui = nil                           -- the widget and its rows (build)
local shown = nil                        -- what is on it now (only what changed is set again)
local frame = 0
local fonts_logged = false

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

local function parse(text)
    -- -> seq, head {ax, ay, alx, aly, width, shown, panel}, rows {{bg = , segs = {{fg, bg, size, bold, text}}}};
    -- nil when there is no whole update
    if not text then return nil end
    local seq, rest = text:match("^ACRHUD 1 (%d+) ([^\n]*)")
    if not seq then return nil end
    local stop, tail = text:match("()\nend (%d+)")
    if not stop or tail ~= seq then return nil end
    local h = {}
    for x in rest:gmatch("%S+") do h[#h + 1] = x end
    local head = {ax = tonumber(h[1]) or 0.02, ay = tonumber(h[2]) or 0.2, alx = tonumber(h[3]) or 0,
                  aly = tonumber(h[4]) or 0, width = tonumber(h[5]) or 320, shown = h[6] == "1", panel = h[7] or "0A0A0BE6"}
    local rows = {}
    for line in text:sub(1, stop):gmatch("\n([^\n]+)") do
        local kind, s = line:match("^(%u) (%d+) ")
        if kind and s ~= seq then return nil end           -- (a line of another update)
        if kind == "R" then
            local bg = line:match("^R %d+ (%S+)")
            rows[#rows + 1] = {bg = bg, segs = {}}
        elseif kind == "S" and #rows > 0 then
            local fg, bg, size, w, words = line:match("^S %d+ (%S+) (%S+) (%d+) (%a+) ?(.*)$")
            if fg then
                local segs = rows[#rows].segs
                segs[#segs + 1] = {fg = fg, bg = bg, size = tonumber(size), bold = w:find("b") ~= nil,
                                   fill = w:find("f") ~= nil, text = words or ""}
            end
        end
    end
    return seq, head, rows
end

-- ---------------------------------------------------------------------- the widget
local classes = {}
local function class(path)
    local c = classes[path]
    if not (c and c:IsValid()) then
        c = StaticFindObject(path)
        classes[path] = c
    end
    return c
end

local function new(path, outer)
    local o = StaticConstructObject(class(path), outer)
    if not (o and o:IsValid()) then error("can't make " .. path) end
    return o
end

local function linear(hex)
    -- RRGGBB[AA] (sRGB, as the app's colours) -> FLinearColor; '-' or nothing: transparent
    if not hex or hex == "-" or #hex < 6 then return {R = 0.0, G = 0.0, B = 0.0, A = 0.0} end
    local function ch(i)
        local v = (tonumber(hex:sub(i, i + 1), 16) or 0) / 255
        return v <= 0.04045 and v / 12.92 or ((v + 0.055) / 1.055) ^ 2.4
    end
    local a = #hex >= 8 and (tonumber(hex:sub(7, 8), 16) or 255) / 255 or 1.0
    return {R = ch(1), G = ch(3), B = ch(5), A = a}
end

local NO_PAD = {Left = 0.0, Top = 0.0, Right = 0.0, Bottom = 0.0}

local function build()
    local gi = UEHelpers.GetGameInstance()
    if not (gi and gi:IsValid()) then return nil end
    local w = new("/Script/UMG.UserWidget", gi)
    local tree = new("/Script/UMG.WidgetTree", w)
    w.WidgetTree = tree
    local canvas = new("/Script/UMG.CanvasPanel", tree)
    tree.RootWidget = canvas
    local panel = new("/Script/UMG.Border", tree)
    local slot = canvas:AddChildToCanvas(panel)
    slot:SetAutoSize(true)
    panel:SetPadding({Left = 12.0, Top = 8.0, Right = 12.0, Bottom = 10.0})
    local size = new("/Script/UMG.SizeBox", tree)
    panel:SetContent(size)
    local box = new("/Script/UMG.VerticalBox", tree)
    size:SetContent(box)
    local rows = {}
    for i = 1, MAX_ROWS do
        local rb = new("/Script/UMG.Border", tree)
        box:AddChildToVerticalBox(rb)
        rb:SetPadding({Left = 0.0, Top = 1.0, Right = 0.0, Bottom = 1.0})
        rb:SetBrushColor(linear("-"))
        local hb = new("/Script/UMG.HorizontalBox", tree)
        rb:SetContent(hb)
        local segs = {}
        for j = 1, MAX_SEGS do
            local sb = new("/Script/UMG.Border", tree)
            local hs = hb:AddChildToHorizontalBox(sb)
            hs:SetVerticalAlignment(2)                    -- (centred: a small piece beside the big time)
            hs:SetPadding({Left = j > 1 and 8.0 or 0.0, Top = 0.0, Right = 0.0, Bottom = 0.0})
            sb:SetPadding(NO_PAD)
            sb:SetBrushColor(linear("-"))
            local tb = new("/Script/UMG.TextBlock", tree)
            sb:SetContent(tb)
            segs[j] = {border = sb, text = tb, slot = hs}
        end
        rb:SetVisibility(COLLAPSED)
        rows[i] = {border = rb, segs = segs}
    end
    w:AddToViewport(50)
    w:SetVisibility(COLLAPSED)
    log("timer widget made")
    return {w = w, slot = slot, panel = panel, size = size, rows = rows}
end

-- The game's own UI font (narrow, as the app's timer's), else the engine's.
local GAME_FONT = "/Game/Data/UI/Fonts/Rajdhani-Medium_Font.Rajdhani-Medium_Font"
local game_font = nil

local function font(tb, size, bold)
    if game_font == nil then
        local ok, f = pcall(StaticFindObject, GAME_FONT)
        game_font = ok and f and f:IsValid() and f or false
        log("font: %s", game_font and GAME_FONT or "the engine's")
    end
    local fi = tb.Font
    if game_font then fi.FontObject = game_font end
    fi.Size = size
    fi.TypefaceFontName = FName(bold and "Bold" or "Regular")
    tb:SetFont(fi)
end

local function put(head, rows)
    -- what the app said, on the widget: only what changed (a widget set again costs the game a little)
    local was = shown or {rows = {}}
    local h = head
    local hk = string.format("%s %s %s %s %s %s", h.ax, h.ay, h.alx, h.aly, h.width, h.panel)
    if was.head ~= hk then
        ui.slot:SetAnchors({Minimum = {X = h.ax, Y = h.ay}, Maximum = {X = h.ax, Y = h.ay}})
        ui.slot:SetAlignment({X = h.alx, Y = h.aly})
        ui.slot:SetPosition({X = 0.0, Y = 0.0})
        ui.size:SetWidthOverride(h.width)
        ui.panel:SetBrushColor(linear(h.panel))
    end
    local now = {head = hk, rows = {}}
    for i = 1, MAX_ROWS do
        local r, w, before = rows[i], ui.rows[i], was.rows[i] or {segs = {}}
        local nr = {segs = {}}
        if r then
            nr.bg = r.bg
            if before.bg ~= r.bg then w.border:SetBrushColor(linear(r.bg)) end
            if not before.on then w.border:SetVisibility(NOT_HIT) end
            nr.on = true
            -- the piece that takes the width left and wraps in it (the others as wide as their words, never wrapped:
            -- a wrapped one beside it was squeezed to a word a line): marked f, else the last without a background
            local fi = 0
            for j, s in ipairs(r.segs) do
                if s.fill then fi = j break end
                if s.bg == "-" then fi = j end
            end
            nr.fi = fi
            if before.fi ~= fi then
                for j = 1, MAX_SEGS do
                    w.segs[j].slot:SetSize({SizeRule = j == fi and 1 or 0, Value = 1.0})
                    w.segs[j].text:SetAutoWrapText(j == fi)
                end
            end
            for j = 1, MAX_SEGS do
                local s, ws, bs = r.segs[j], w.segs[j], before.segs[j]
                if s then
                    local fk = s.size .. (s.bold and "b" or "r")
                    if not bs or bs.font ~= fk then font(ws.text, s.size, s.bold) end
                    if not bs or bs.fg ~= s.fg then
                        ws.text:SetColorAndOpacity({SpecifiedColor = linear(s.fg), ColorUseRule = 0})
                    end
                    if not bs or bs.bg ~= s.bg then
                        ws.border:SetBrushColor(linear(s.bg))
                        ws.border:SetPadding(s.bg ~= "-" and {Left = 6.0, Top = 0.0, Right = 6.0, Bottom = 0.0} or NO_PAD)
                    end
                    if not bs or bs.text ~= s.text then ws.text:SetText(FText(s.text)) end
                    if not bs or not bs.on then ws.border:SetVisibility(NOT_HIT) end
                    nr.segs[j] = {font = fk, fg = s.fg, bg = s.bg, text = s.text, on = true}
                elseif bs and bs.on then
                    ws.border:SetVisibility(COLLAPSED)
                end
            end
        elseif before.on then
            w.border:SetVisibility(COLLAPSED)
        end
        now.rows[i] = nr
    end
    shown = now
end

local function log_fonts()
    -- (once: the game's fonts, to pick one that has every language's letters)
    fonts_logged = true
    local all = FindAllOf("Font")
    if not all then return end
    local n = 0
    for _, x in ipairs(all) do
        n = n + 1
        if n <= 40 then log("font %s", x:GetFullName()) end
    end
end

function M.tick(t)
    frame = frame + 1
    local seq, head, rows = parse(read_file(t))
    if seq and seq ~= last_seq then last_seq, last_new_t = seq, t end
    if f and t - math.max(last_new_t or 0, f_opened or 0) > 5.0 then     -- (the file made again: opened again)
        f:close()
        f = nil
    end
    local want = last_new_t and t - last_new_t < STALE_S and head and head.shown
    if ui and not (ui.w:IsValid() and ui.w:IsInViewport()) then           -- (a stage loaded: the viewport emptied)
        ui, shown = nil, nil
    end
    if not want then
        if ui and ui.on then
            ui.w:SetVisibility(COLLAPSED)
            ui.on = false
        end
        return
    end
    if not ui then
        if frame % 15 ~= 0 then return end                                -- (tried a few times a second)
        ui = build()
        if not ui then return end
        if not fonts_logged then pcall(log_fonts) end
    end
    if seq then put(head, rows) end
    if not ui.on then
        ui.w:SetVisibility(NOT_HIT)
        ui.on = true
    end
end

return M
