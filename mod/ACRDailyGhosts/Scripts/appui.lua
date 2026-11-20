-- ACR DAILY inside the game (0.2, private build): the app's pages drawn by the game (part of the ACR Daily mod:
-- main.lua runs M.tick every frame).
--
-- The app (client/acr_daily/ingameapp.py) stays the brain: the server, the save, the timing. It writes what its pages
-- show to %APPDATA%\ACR Daily\ingame-app.txt, as a tree of boxes, words, pictures and buttons; this draws that tree with
-- the game's own widgets (hudkit.lua) and tells the app what was clicked. In the game's main menu, HOME gets an
-- ACR DAILY tile (the game's own tile, WB_MainMenuListButton): clicking it puts the game's menu away and shows the
-- app's pages in its place; Esc (or BACK TO THE GAME) brings the game's menu back.
--
--   ACRAPP 1 <seq> <rev>          seq: each write (the app is alive while it changes); rev: what the pages say (only a
--   <json>                        new rev is read and drawn again)
--   end <seq>
--
--   json: {"tile": {"label", "img"}, "open": true|false (the app asks for its pages, e.g. after DRIVE),
--          "page": <node>, "dialog": <node> | null}
--   node: {"t": "col"|"row"|"stack"|"box"|"txt"|"img"|"btn"|"scroll"|"size"|"sp", ...}, its place in its parent:
--         "fill" (a share of what's left), "al"/"va" (l c r f / t c b f), "pad" [l, t, r, b]
--
-- Back to the app, %APPDATA%\ACR Daily\ingame-app-events.txt: "ACRAPP <session>.<n> <what> [<id>]" (what: open,
-- close, click).
local UEHelpers = require("UEHelpers")
local K = require("hudkit")

local M = {}
local TAG = "[ACRDailyApp] "
local DIR = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\"
local FILE = DIR .. "ingame-app.txt"
local EVENTS = DIR .. "ingame-app-events.txt"
local ALIVE_S = 4.0              -- the app's file not written for this long: the app is gone (tile and pages away)
local Z = 400                    -- over the game's menus and our other displays

local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end
log("loaded")

-- ---------------------------------------------------------------------- JSON (the app's pages)
local json_decode
do
    local esc = {['"'] = '"', ['\\'] = '\\', ['/'] = '/', b = '\b', f = '\f', n = '\n', r = '\r', t = '\t'}
    local function utf8_of(cp)
        if cp < 0x80 then return string.char(cp) end
        if cp < 0x800 then return string.char(0xC0 | (cp >> 6), 0x80 | (cp & 0x3F)) end
        return string.char(0xE0 | (cp >> 12), 0x80 | ((cp >> 6) & 0x3F), 0x80 | (cp & 0x3F))
    end
    local function ws(s, i)
        return s:find("[^ \t\r\n]", i) or #s + 1
    end
    local value
    local function str(s, i)                -- s:sub(i, i) == '"'
        local out, j = {}, i + 1
        while true do
            local k = s:find('["\\]', j)
            if not k then error("unfinished string") end
            out[#out + 1] = s:sub(j, k - 1)
            if s:sub(k, k) == '"' then return table.concat(out), k + 1 end
            local c = s:sub(k + 1, k + 1)
            if c == "u" then
                out[#out + 1] = utf8_of(tonumber(s:sub(k + 2, k + 5), 16) or 63)
                j = k + 6
            else
                out[#out + 1] = esc[c] or c
                j = k + 2
            end
        end
    end
    function value(s, i)
        i = ws(s, i)
        local c = s:sub(i, i)
        if c == "{" then
            local t = {}
            i = ws(s, i + 1)
            if s:sub(i, i) == "}" then return t, i + 1 end
            while true do
                local key
                key, i = str(s, ws(s, i))
                i = ws(s, i)
                if s:sub(i, i) ~= ":" then error("':' expected at " .. i) end
                t[key], i = value(s, i + 1)
                i = ws(s, i)
                local d = s:sub(i, i)
                if d == "}" then return t, i + 1 end
                if d ~= "," then error("',' expected at " .. i) end
                i = i + 1
            end
        elseif c == "[" then
            local t = {}
            i = ws(s, i + 1)
            if s:sub(i, i) == "]" then return t, i + 1 end
            while true do
                t[#t + 1], i = value(s, i)
                i = ws(s, i)
                local d = s:sub(i, i)
                if d == "]" then return t, i + 1 end
                if d ~= "," then error("',' expected at " .. i) end
                i = i + 1
            end
        elseif c == '"' then
            return str(s, i)
        elseif s:sub(i, i + 3) == "true" then return true, i + 4
        elseif s:sub(i, i + 4) == "false" then return false, i + 5
        elseif s:sub(i, i + 3) == "null" then return nil, i + 4
        end
        local num = s:match("^-?%d+%.?%d*[eE]?[-+]?%d*", i)
        if not num or num == "" then error("bad value at " .. i) end
        return tonumber(num), i + #num
    end
    function json_decode(s)
        local ok, v = pcall(value, s, 1)
        if ok then return v end
        log("bad pages from the app: %s", tostring(v))
        return nil
    end
end
M.json_decode = json_decode            -- (tests)

-- ---------------------------------------------------------------------- the app's file
local f = nil
local frame = 0
local state = {seq = nil, seq_t = nil, rev = nil, data = nil}

local function read_file()
    if not f then
        f = io.open(FILE, "rb")
        if not f then return nil end
    end
    if not f:seek("set", 0) then
        f:close()
        f = nil
        return nil
    end
    return f:read("a")
end

local function poll_file(t)
    local text = read_file()
    if not text then return end
    local seq, rev, body = text:match("^ACRAPP 1 (%d+) (%S+)\r?\n(.*)$")
    if not seq then return end
    if seq ~= state.seq then
        if state.seq ~= nil then state.seq_t = t end         -- (the first one seen: maybe left by an app now closed)
        state.seq = seq
    end
    if rev ~= state.rev then
        local json, tail = body:match("^(.-)\r?\nend (%d+)")
        if tail ~= seq then return end                      -- (read in the middle of a write: next time)
        local data = json_decode(json)
        if data then
            state.rev, state.data = rev, data
            state.changed = true
        end
    end
end

local function app_alive(t)
    return state.seq_t ~= nil and t - state.seq_t < ALIVE_S and state.data ~= nil
end

-- ---------------------------------------------------------------------- back to the app
local ev_f, ev_n = nil, 0
local SESSION = tostring(os.time())
local function tell(what, id)
    if not ev_f then ev_f = io.open(EVENTS, "w") end
    if not ev_f then return end
    ev_n = ev_n + 1
    local line = string.format("ACRAPP %s.%d %s %s", SESSION, ev_n, what, (tostring(id or ""):gsub("[\r\n]+", " ")))
    ev_f:seek("set", 0)
    ev_f:write(line .. "\n" .. string.rep(" ", math.max(0, 600 - #line)) .. "\n")
    ev_f:flush()
end

-- ---------------------------------------------------------------------- keys
-- (once for the game's life; the press only noted here, done on the next frame on the game thread)
if not rawget(_G, "ACRDAILY_APPKEYS") and type(RegisterKeyBind) == "function" and Key then
    _G.ACRDAILY_APPKEYS = true
    for _, k in ipairs({"ESCAPE", "RETURN"}) do
        pcall(RegisterKeyBind, Key[k], function() _G.ACRDAILY_APPKEY = k end)
    end
end

-- ---------------------------------------------------------------------- the game's menu: HOME's tile
local PANEL = nil
local CONTENT = nil
local function find(root, name)
    PANEL = PANEL or StaticFindObject("/Script/UMG.PanelWidget")
    CONTENT = CONTENT or StaticFindObject("/Script/UMG.ContentWidget")
    local hit
    local function walk(w, d)
        if hit or d > 12 or not (w and w:IsValid()) then return end
        if w:GetFName():ToString() == name then hit = w return end
        if w:IsA(PANEL) then
            for i = 0, w:GetChildrenCount() - 1 do walk(w:GetChildAt(i), d + 1) end
        elseif w:IsA(CONTENT) then
            local ok, ch = pcall(function() return w:GetContent() end)
            if ok then walk(ch, d + 1) end
        end
    end
    walk(root, 0)
    return hit
end

local menu = {}          -- {main (WB_MainMenu), home (its HOME layout), tile, sb, tex_path, moved}
local TILE_CLASS = "/Game/Data/UI/Widgets_Buttons/WB_MainMenuListButton.WB_MainMenuListButton_C"
local TILE_W, TILE_H = 532.0, 716.0

local function home_layout()
    -- the game's main menu and its HOME page (the first page of its switcher: HOME, RACING, MULTIPLAYER, PROFILE,
    -- SETTINGS), or nil (not in the main menu)
    local main = FindFirstOf("WB_MainMenu_C")
    if not (main and main:IsValid()) then return nil end
    local sel = FindFirstOf("WB_SelectWidget_C")
    if not (sel and sel:IsValid()) then return nil end
    local sw = find(sel.WidgetTree.RootWidget, "OptionSwitcher")
    if not sw then return nil end
    local home = sw:GetChildAt(0)
    if not (home and home:IsValid()) then return nil end
    return main, home
end

local function make_tile(t)
    local main, home = home_layout()
    if not main then return false end
    local root = home.WidgetTree.RootWidget
    local tc = find(root, "TilesContainer")
    if not tc then return false end
    local ov = tc:GetContent()
    -- one made already (this file loaded again): taken over
    for i = 0, ov:GetChildrenCount() - 1 do
        local c = ov:GetChildAt(i)
        local ok, inner = pcall(function() return c:GetContent() end)
        local id = ""
        if ok and inner and inner:IsValid() then pcall(function() id = inner.MenuButtonId:ToString() end) end
        if id == "ACRDaily" then
            menu.main, menu.home, menu.tile, menu.sb = main, home, inner, c
            menu.made_t, menu.dressed = t, nil
            return true
        end
    end
    -- the box made wider to the right, its left edge where it was; the game's three tiles to its left side
    local cs = tc.Slot
    local L = cs:GetLayout()
    if L.Alignment.X ~= 0.0 then
        L.Offsets.Left = L.Offsets.Left - L.Offsets.Right * L.Alignment.X
        L.Offsets.Right = L.Offsets.Right + TILE_W + 18
        L.Alignment.X = 0.0
        cs:SetLayout(L)
    end
    for _, n in ipairs({"RallyContainer", "TimeAttackContainer", "FreePracticeContainer"}) do
        local c = find(root, n)
        if c then
            c.Slot:SetHorizontalAlignment(1)
            local p = c.Slot.Padding
            p.Left = 9.0
            c.Slot:SetPadding(p)
        end
    end
    local bkg = find(root, "Bkg")
    if bkg then bkg:SetVisibility(K.COLLAPSED) end
    local WBL = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
    local tile = WBL:Create(UEHelpers.GetWorld(), StaticFindObject(TILE_CLASS), UEHelpers.GetPlayerController())
    if not (tile and tile:IsValid()) then return false end
    tile.MenuButtonId = FName("ACRDaily")
    local sb = K.new("SizeBox", home.WidgetTree)
    sb:SetWidthOverride(TILE_W)
    sb:SetHeightOverride(TILE_H)
    sb:SetContent(tile)
    local s = ov:AddChildToOverlay(sb)
    s:SetHorizontalAlignment(3)
    s:SetVerticalAlignment(1)
    s:SetPadding(K.pad(0, 8, 9, 0))
    menu.main, menu.home, menu.tile, menu.sb = main, home, tile, sb
    menu.made_t, menu.dressed = t, nil
    log("ACR DAILY tile on HOME")
    return true
end

local function dress_tile(td)
    -- its words and picture: set after the game has built it (its own set-up puts its default ones in)
    local tile = menu.tile
    local label = td and td.label or "ACR DAILY"
    local img = td and td.img or nil
    local key = label .. "|" .. tostring(img)
    if menu.dressed == key then return end
    pcall(function() tile:SetButtonText(FText(label)) end)
    pcall(function() tile.TextBlock:SetText(FText(label)) end)
    local tex = K.texture(img)
    if tex then
        local bi = tile.ButtonImage
        bi:SetBrushFromTexture(tex, false)
        local b = bi.Brush
        b.ImageSize = {X = TILE_W, Y = TILE_H}
        bi:SetBrush(b)
        bi:SetColorAndOpacity(K.lin("FFFFFF"))
    end
    menu.dressed = key
end

local function tile_ok()
    return menu.tile and menu.tile:IsValid() and menu.sb and menu.sb:IsValid() and menu.home and menu.home:IsValid()
end

-- the tile clicked (the mouse): the game's buttons all go through this
if not rawget(_G, "ACRDAILY_TILEHOOK") then
    _G.ACRDAILY_TILEHOOK = true
    pcall(RegisterHook, "/Script/CommonUI.CommonButtonBase:HandleButtonClicked", function(self)
        local ok, b = pcall(function() return self:get() end)
        if ok and b and b:IsValid() then
            local id = ""
            pcall(function() id = b.MenuButtonId:ToString() end)
            if id == "ACRDaily" then _G.ACRDAILY_TILE_CLICKED = true end
        end
    end)
end

-- ---------------------------------------------------------------------- the pages
local page = nil           -- {w, tree, canvas, buttons = {...}, scrolls = {id -> ScrollBox}, rev}
local shown = false        -- the pages on screen (the game's menu put away)

local function align(x, default)
    -- 'l' 'c' 'r' 'f' / 't' 'c' 'b' 'f' -> EHorizontalAlignment / EVerticalAlignment (0 fill, 1 left/top, 2 centre, 3)
    if x == "l" or x == "t" then return 1 end
    if x == "c" then return 2 end
    if x == "r" or x == "b" then return 3 end
    if x == "f" then return 0 end
    return default
end

local function padding(p)
    if type(p) == "number" then return K.pad(p) end
    if type(p) == "table" then return K.pad(p[1] or 0, p[2] or p[1] or 0, p[3] or p[1] or 0, p[4] or p[2] or p[1] or 0) end
    return nil
end

local build
local function place(parent_kind, parent, child, n)
    -- child into parent, its slot from n's fill / al / va / pad
    local s
    if parent_kind == "col" or parent_kind == "row" then
        s = parent_kind == "col" and parent:AddChildToVerticalBox(child) or parent:AddChildToHorizontalBox(child)
        if n.fill then s:SetSize({SizeRule = 1, Value = (n.fill == true and 1 or n.fill) + 0.0}) end
    elseif parent_kind == "stack" then
        s = parent:AddChildToOverlay(child)
    elseif parent_kind == "scroll" then
        s = parent:AddChild(child)
    else
        return
    end
    local p = padding(n.pad)
    if p then s:SetPadding(p) end
    local h = align(n.al, nil)
    if h then s:SetHorizontalAlignment(h) end
    local v = align(n.va, nil)
    if v then pcall(function() s:SetVerticalAlignment(v) end) end
end

local function text_widget(P, n)
    local tb = K.text(P.tree, {size = n.sz or 16, face = n.f or "semi", colour = n.fg or "F4F4F5", spacing = n.sp,
                              shadow = n.sh == true, wrap = n.wrap, justify = n.j, text = n.s or ""})
    if n.max then pcall(function() tb:SetWrapTextAt(n.max + 0.0) end) end
    return tb
end

function build(P, n)
    -- a node -> its widget (nil: nothing)
    if type(n) ~= "table" then return nil end
    local t = n.t
    local tree = P.tree
    if t == "col" or t == "row" or t == "stack" then
        local w = t == "col" and K.vbox(tree) or (t == "row" and K.hbox(tree) or K.new("Overlay", tree))
        for i, c in ipairs(n.c or {}) do
            local cw = build(P, c)
            if cw then
                if n.gap and i > 1 and t ~= "stack" and not c.pad then
                    c.pad = t == "col" and {0, n.gap, 0, 0} or {n.gap, 0, 0, 0}
                end
                place(t, w, cw, c)
            end
        end
        return w
    elseif t == "box" then
        local b = K.panel(tree, {fill = n.bg, alpha = n.a, radius = n.r, outline = n.ol, outline_w = n.olw,
                                 pad = type(n.p) == "table" and n.p or (n.p and {n.p, n.p, n.p, n.p}) or nil})
        if n.al then b:SetHorizontalAlignment(align(n.al, 0)) end
        if n.va then b:SetVerticalAlignment(align(n.va, 0)) end
        local cw = build(P, n.c)
        if cw then b:SetContent(cw) end
        return b
    elseif t == "txt" then
        return text_widget(P, n)
    elseif t == "img" then
        local pic = K.image(tree, n.w, n.h)
        K.picture(pic, {}, n.src)
        if n.stretch then pcall(function() pic.box:GetContent():SetStretch(n.stretch) end) end
        return pic.box
    elseif t == "size" or t == "sp" then
        local sb = K.size(tree, nil, n.w, n.h)
        if n.minw then sb:SetMinDesiredWidth(n.minw + 0.0) end
        if n.minh then sb:SetMinDesiredHeight(n.minh + 0.0) end
        if n.maxw then sb:SetMaxDesiredWidth(n.maxw + 0.0) end
        if n.c then
            local cw = build(P, n.c)
            if cw then sb:SetContent(cw) end
        end
        return sb
    elseif t == "scroll" then
        local sc = K.new("ScrollBox", tree)
        pcall(function() sc:SetScrollBarVisibility(n.bar == false and 1 or 0) end)
        for _, c in ipairs(n.c or {}) do
            local cw = build(P, c)
            if cw then place("scroll", sc, cw, c) end
        end
        if n.id then P.scrolls[n.id] = sc end
        return sc
    elseif t == "btn" then
        local btn = K.new("Button", tree)
        local st = btn.WidgetStyle
        for _, k in ipairs({"Normal", "Hovered", "Pressed", "Disabled"}) do st[k].DrawAs = 0 end
        st.NormalPadding = K.pad(0)
        st.PressedPadding = K.pad(0)
        btn:SetStyle(st)
        local b = K.panel(tree, {fill = n.bg or "-", alpha = n.a, radius = n.r, outline = n.ol, outline_w = n.olw,
                                 pad = type(n.p) == "table" and n.p or (n.p and {n.p, n.p, n.p, n.p}) or nil})
        b:SetHorizontalAlignment(align(n.cal or "c", 2))
        b:SetVerticalAlignment(2)
        local texts = {}
        local cw
        if n.s then                          -- (a plain button: its words)
            cw = text_widget(P, {s = n.s, sz = n.sz or 18, f = n.f or "semi", fg = n.fg or "F4F4F5", sp = n.sp})
            texts[1] = cw
        else
            cw = build(P, n.c)
        end
        if cw then b:SetContent(cw) end
        btn:SetContent(b)
        pcall(function() btn.Slot:SetPadding(K.pad(0)) end)
        pcall(function() btn.Slot:SetHorizontalAlignment(0) end)
        pcall(function() btn.Slot:SetVerticalAlignment(0) end)
        P.buttons[#P.buttons + 1] = {btn = btn, box = b, id = n.id, bg = n.bg or "-", a = n.a, hov = n.hov or n.bg or "-",
                                     fg = n.fg or "F4F4F5", hfg = n.hfg, texts = texts, hover = false, pressed = false}
        if n.w or n.h then return K.size(tree, btn, n.w, n.h) end
        return btn
    end
    return nil
end

local function make_page(data)
    local gi = UEHelpers.GetGameInstance()
    if not (gi and gi:IsValid()) then return nil end
    local w = K.new("UserWidget", gi)
    local tree = K.new("WidgetTree", w)
    w.WidgetTree = tree
    local canvas = K.new("CanvasPanel", tree)
    tree.RootWidget = canvas
    w:AddToViewport(Z)
    local P = {w = w, tree = tree, canvas = canvas, buttons = {}, scrolls = {}}
    -- the backdrop: the game's scene behind, darkened and blurred
    local blur = K.new("BackgroundBlur", tree)
    pcall(function() blur:SetBlurStrength(8.0) end)
    local bs = canvas:AddChildToCanvas(blur)
    bs:SetAnchors({Minimum = {X = 0.0, Y = 0.0}, Maximum = {X = 1.0, Y = 1.0}})
    bs:SetOffsets({Left = 0.0, Top = 0.0, Right = 0.0, Bottom = 0.0})
    local dark = K.panel(tree, {fill = "07070A", alpha = 0.78})
    blur:SetContent(dark)
    -- the page, across the middle 16:9 (and no wider than 1920 units on a wide screen)
    local body = build(P, data.page)
    if body then
        local holder = K.size(tree, body, nil, nil)
        holder:SetMaxDesiredWidth(1920.0)
        local hs = canvas:AddChildToCanvas(holder)
        hs:SetAnchors({Minimum = {X = 0.5, Y = 0.0}, Maximum = {X = 0.5, Y = 1.0}})
        hs:SetAlignment({X = 0.5, Y = 0.0})
        hs:SetOffsets({Left = 0.0, Top = 40.0, Right = 1840.0, Bottom = 40.0})
    end
    -- a question over it all (DRIVE's: the game restarts into that daily)
    if data.dialog then
        local veil = K.panel(tree, {fill = "000000", alpha = 0.6})
        local vs = canvas:AddChildToCanvas(veil)
        vs:SetAnchors({Minimum = {X = 0.0, Y = 0.0}, Maximum = {X = 1.0, Y = 1.0}})
        vs:SetOffsets({Left = 0.0, Top = 0.0, Right = 0.0, Bottom = 0.0})
        veil:SetHorizontalAlignment(2)
        veil:SetVerticalAlignment(2)
        local dw = build(P, data.dialog)
        if dw then veil:SetContent(dw) end
    end
    w:SetVisibility(K.SELF_HIT)
    return P
end

local function drop_page()
    if page and page.w and page.w:IsValid() then page.w:RemoveFromParent() end
    page = nil
end

local function game_menu(on)
    -- the game's own menu put away while ours is on screen (none of its buttons under ours), and back
    local main = FindFirstOf("WB_MainMenu_C")
    if main and main:IsValid() then
        if not on and not menu.main_vis then menu.main_vis = main:GetVisibility() end
        main:SetVisibility(on and (menu.main_vis or K.VISIBLE) or K.COLLAPSED)
        if on then menu.main_vis = nil end
    end
end

local function show(on)
    if on == shown then return end
    shown = on
    if on then
        game_menu(false)
        if page then page.w:SetVisibility(K.SELF_HIT) end
        tell("open")
    else
        if page then page.w:SetVisibility(K.COLLAPSED) end
        game_menu(true)
        pcall(function()
            if menu.tile and menu.tile:IsValid() then menu.tile:SetKeyboardFocus() end
        end)
        tell("close")
    end
end

local function redraw()
    -- the app's pages, made again (a new rev): where each list was scrolled to kept
    local offsets = {}
    if page then
        for id, sc in pairs(page.scrolls) do
            local ok, o = pcall(function() return sc:GetScrollOffset() end)
            if ok then offsets[id] = o end
        end
    end
    drop_page()
    page = make_page(state.data)
    if not page then return end
    for id, o in pairs(offsets) do
        local sc = page.scrolls[id]
        if sc then pcall(function() sc:SetScrollOffset(o) end) end
    end
    page.w:SetVisibility(shown and K.SELF_HIT or K.COLLAPSED)
end

local function buttons(t)
    -- hover looks and clicks: a press let go over the button (or with the keyboard on it) is a click
    if not page then return end
    local poll_all = frame % 3 == 0
    for _, b in ipairs(page.buttons) do
        if b.btn:IsValid() then
            if poll_all or b.hover or b.pressed then
                local h = b.btn:IsHovered()
                if h ~= b.hover then
                    b.hover = h
                    b.box:SetBrushColor(K.lin(h and b.hov or b.bg, b.a))
                    if b.hfg then
                        for _, tb in ipairs(b.texts) do tb:SetColorAndOpacity(K.slate(K.lin(h and b.hfg or b.fg))) end
                    end
                end
                local p = b.btn:IsPressed()
                if p ~= b.pressed then
                    if b.pressed and not p and (b.hover or b.btn:HasKeyboardFocus()) and b.id then
                        if b.id == "close" then
                            show(false)
                        else
                            tell("click", b.id)
                        end
                    end
                    b.pressed = p
                end
            end
        end
    end
end

--- (this file about to be loaded again, testing: its pages away, the game's menu back; the tile is kept and taken over)
function M.unload()
    if shown then show(false) end
    drop_page()
    if f then f:close() f = nil end
    if ev_f then ev_f:close() ev_f = nil end
end

-- ---------------------------------------------------------------------- every frame
function M.tick(t)
    frame = frame + 1
    if frame % 6 == 0 then poll_file(t) end
    local alive = app_alive(t)
    local key = rawget(_G, "ACRDAILY_APPKEY")
    _G.ACRDAILY_APPKEY = nil
    local clicked = rawget(_G, "ACRDAILY_TILE_CLICKED")
    _G.ACRDAILY_TILE_CLICKED = nil

    -- the tile: on HOME while the app runs (made again after the menu is: a stage and back)
    if frame % 30 == 0 then
        if alive and not tile_ok() then
            menu.tile = nil
            pcall(make_tile, t)
        end
        if tile_ok() then
            menu.sb:SetVisibility(alive and K.SELF_HIT or K.COLLAPSED)
        end
    end
    if tile_ok() and alive and t - (menu.made_t or t) > 0.3 then dress_tile(state.data.tile) end

    if not alive then
        if shown then show(false) end
        if page then drop_page() end
        return
    end
    if state.changed then
        state.changed = false
        if page or shown then redraw() end
        if state.data.open and not shown then
            if not page then redraw() end
            show(true)
        end
    end
    -- opened: the tile clicked, or Enter on it
    local enter_on_tile = key == "RETURN" and not shown and tile_ok() and
        (function()
            local ok, v = pcall(function() return menu.tile:HasUserFocusedDescendants(UEHelpers.GetPlayerController()) end)
            local ok2, v2 = pcall(function() return menu.tile:HasAnyUserFocus() end)
            return (ok and v) or (ok2 and v2)
        end)()
    if (clicked or enter_on_tile) and not shown then
        if not page then redraw() end
        if page then show(true) end
    end
    if shown then
        if key == "ESCAPE" then
            show(false)
        else
            buttons(t)
        end
        if page and not page.w:IsInViewport() then          -- (a level loaded: the viewport emptied)
            page = nil
            shown = false
        end
    end
end

return M
