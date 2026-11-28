-- ACR DAILY inside the game (0.2, private build): the app's pages drawn by the game (part of the ACR Daily mod:
-- main.lua runs M.tick every frame).
--
-- The app (client/acr_daily/ingameapp.py) stays the brain: the server, the save, the timing. It writes what its pages
-- show to %APPDATA%\ACR Daily\ingame-app.txt, as a tree of boxes, words, pictures and buttons; this draws that tree with
-- the game's own widgets (hudkit.lua) and tells the app what was clicked. In the game's main menu, MULTIPLAYER gets an
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
-- DRIVE in the running game: drive.lua, loaded from this file's own folder (not require: UE4SS kept the first copy
-- loaded past a dev reload, 20 Nov 2026); hudkit.lua too (its game pictures: 21 Nov 2026)
local HERE = (debug.getinfo(1, "S").source or ""):match("^@(.*[/\\])")
local ok_kit, K = pcall(function() return HERE and dofile(HERE .. "hudkit.lua") or require("hudkit") end)
if not ok_kit or type(K) ~= "table" then K = require("hudkit") end
local ok_drive, drive = pcall(function() return HERE and dofile(HERE .. "drive.lua") or require("drive") end)
if not ok_drive or type(drive) ~= "table" then
    print("[ACRDailyApp] no drive.lua: " .. tostring(drive) .. "\n")
    drive = nil
end

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
-- The last KEEP events, oldest first, then "end <session>.<n>" (the app takes each new one in order: two in one frame,
-- words typed then OK clicked, are both read). Overwritten in place, what's left of a longer one blanked.
local ev_f, ev_n, ev_size = nil, 0, 0
local ev_lines = {}
local KEEP = 20
local SESSION = tostring(os.time())
local function tell(what, id)
    if not ev_f then ev_f = io.open(EVENTS, "w") end
    if not ev_f then return end
    ev_n = ev_n + 1
    ev_lines[#ev_lines + 1] = string.format("ACRAPP %s.%d %s %s", SESSION, ev_n, what,
                                            (tostring(id or ""):gsub("[\r\n]+", " ")))
    while #ev_lines > KEEP do table.remove(ev_lines, 1) end
    local body = table.concat(ev_lines, "\n") .. string.format("\nend %s.%d\n", SESSION, ev_n)
    ev_f:seek("set", 0)
    ev_f:write(body .. string.rep(" ", math.max(0, ev_size - #body)))
    ev_f:flush()
    ev_size = #body
end

-- ---------------------------------------------------------------------- keys
-- (once for the game's life; the press only noted here, done on the next frame on the game thread)
if not rawget(_G, "ACRDAILY_APPKEYS") and type(RegisterKeyBind) == "function" and Key then
    _G.ACRDAILY_APPKEYS = true
    for _, k in ipairs({"ESCAPE", "RETURN", "Q", "E"}) do
        pcall(RegisterKeyBind, Key[k], function() _G.ACRDAILY_APPKEY = k end)
    end
end
if not rawget(_G, "ACRDAILY_APPKEYS2") and type(RegisterKeyBind) == "function" and Key then
    _G.ACRDAILY_APPKEYS2 = true                         -- (Left / Right, 21 Nov 2026: across a page's columns)
    for _, k in ipairs({"LEFT_ARROW", "RIGHT_ARROW", "UP_ARROW", "DOWN_ARROW"}) do
        pcall(RegisterKeyBind, Key[k], function() _G.ACRDAILY_APPKEY = k end)
    end
end
if not rawget(_G, "ACRDAILY_APPKEYS3") and type(RegisterKeyBind) == "function" and Key then
    _G.ACRDAILY_APPKEYS3 = true                         -- (RANKED's chat on the stage, 22 Nov 2026: chat_tick)
    for _, k in ipairs({"T", "PAGE_UP", "PAGE_DOWN"}) do
        pcall(RegisterKeyBind, Key[k], function() _G.ACRDAILY_APPKEY = k end)
    end
end

-- ---------------------------------------------------------------------- the game's menu: MULTIPLAYER's tile
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

local menu = {}          -- {main (WB_MainMenu), page (its MULTIPLAYER layout), tile, sb (the slot it is in)}
local TILE_CLASS = "/Game/Data/UI/Widgets_Buttons/WB_MainMenuListButton.WB_MainMenuListButton_C"
local TILE_W, TILE_H = 532.0, 175.0       -- (the game's own small tile: CREATE LOBBY's size)
local TILE_SLOT = "FreePracticeContainer" -- MULTIPLAYER's third place, empty in the game (hidden): ACR DAILY's

local function live(class)
    -- the live one of a menu widget class (FindFirstOf can give the blueprint's own template: no use)
    for _, x in ipairs(FindAllOf(class) or {}) do
        if x:IsValid() and x:GetFullName():find("/Engine/Transient", 1, true) then return x end
    end
    return nil
end

local function main_menu()
    -- the game's main menu on screen: the game makes a new one when it comes back from a mode's own screens, the old
    -- one still there a while, off the screen (the tile went on that one and was never seen: the user, 22 Nov 2026).
    -- The menu itself never says it is in the viewport (the game shows it through its root layout's MenuLayer), so it
    -- is told by its root layout (WB_RootGameLayout, the menu's outer's outer): only the live one is in the viewport. The
    -- first one found was taken before, and after a level change that could be the old level's, still there until the
    -- engine cleared it: the tile went on it, unseen (the user, 25 Nov 2026: "go back - then there is no ACR Daily tile").
    -- Coming back from SEARCH LOBBIES (the same level, no new world): the old menu and a new one can both be in the
    -- viewport through the one root layout, so "in the viewport" was true of both and the first found was taken: the
    -- tile went on the old one, and the new one (on screen) had none (the user, 26 Nov 2026, the third time). The one on
    -- screen is the one the game has ACTIVE (a CommonUI screen: only the top one is), then the one visible.
    local cands, top = {}, -1
    for _, x in ipairs(FindAllOf("WB_MainMenu_C") or {}) do
        if x:IsValid() and x:GetFullName():find("/Engine/Transient", 1, true) then
            local s = 0
            pcall(function() if x:IsActivated() then s = s + 4 end end)
            pcall(function()
                local on = x:IsInViewport()
                if not on then
                    local tree = x:GetOuter()
                    local root = tree and tree:IsValid() and tree:GetOuter()
                    on = root ~= nil and root:IsValid() and root:IsInViewport()
                end
                if on then s = s + 2 end
            end)
            pcall(function() if x:IsVisible() then s = s + 1 end end)
            cands[#cands + 1] = {x = x, s = s}
            if s > top then top = s end
        end
    end
    menu.n_menus = #cands
    local tops = {}
    for _, c in ipairs(cands) do
        if c.s == top then tops[#tops + 1] = c.x end
    end
    if #tops == 1 then return tops[1] end
    -- (several as good as each other: the one the tile is on stays, else none taken until it's clear)
    if menu.main and menu.main:IsValid() then
        for _, x in ipairs(tops) do
            local ok, same = pcall(function() return x:GetAddress() == menu.main:GetAddress() end)
            if ok and same then return x end
        end
    end
    return nil
end

local function multiplayer_layout()
    -- the game's main menu and its MULTIPLAYER page (the third page of its switcher: HOME, RACING, MULTIPLAYER,
    -- PROFILE, SETTINGS; SEARCH LOBBIES and CREATE LOBBY on it), or nil (not in the main menu)
    local main = main_menu()
    if not main then return nil end
    local sel = nil                                  -- (its own switcher: the one inside this main menu)
    local mname = main:GetFullName():match("([^%.]+)$") or ""
    for _, x in ipairs(FindAllOf("WB_SelectWidget_C") or {}) do
        if x:IsValid() and x:GetFullName():find(mname .. ".", 1, true) then sel = x break end
    end
    sel = sel or live("WB_SelectWidget_C")
    if not sel then return nil end
    local sw = find(sel.WidgetTree.RootWidget, "OptionSwitcher")
    if not sw or sw:GetChildrenCount() < 3 then return nil end
    local page = sw:GetChildAt(2)
    if not (page and page:IsValid() and page:GetClass():GetFName():ToString():find("RaceLayout")) then return nil end
    return main, page, sel
end

local function to_multiplayer()
    -- the game's menu on its MULTIPLAYER tab (the tile's): ACR DAILY closed after a stage left the game on HOME, the
    -- focus sent to the tile landing in HOME's third place (GARAGE), where the wheel's next OK went (25 Nov 2026)
    local sel = menu.sel
    if not (sel and sel:IsValid()) then return end
    local id = sel:GetTabIdAtIndex(2)
    if sel:GetSelectedTabId():ToString() ~= id:ToString() then sel:SelectTabByID(id, true) end
end

local function make_tile(t)
    local main, page, sel = multiplayer_layout()
    if not main then return false end
    local sb = find(page.WidgetTree.RootWidget, TILE_SLOT)
    if not sb then return false end
    -- one made already (this file loaded again): taken over
    local ok, inner = pcall(function() return sb:GetContent() end)
    local id = ""
    if ok and inner and inner:IsValid() then pcall(function() id = inner.MenuButtonId:ToString() end) end
    local tile = id == "ACRDaily" and inner or nil
    if not tile then
        local WBL = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        tile = WBL:Create(UEHelpers.GetWorld(), StaticFindObject(TILE_CLASS), UEHelpers.GetPlayerController())
        if not (tile and tile:IsValid()) then return false end
        tile.MenuButtonId = FName("ACRDaily")
        sb:SetContent(tile)                  -- (in the game's own place for a third tile, its size and spot kept)
        log("ACR DAILY tile on MULTIPLAYER")
    end
    menu.main, menu.page, menu.tile, menu.sb, menu.sel = main, page, tile, sb, sel
    menu.made_t, menu.dressed = t, nil
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
    -- its label as the game's unselected tiles have it: the game colours a tile's label box (TextBorder) red while the
    -- tile is selected and a dark see-through grey otherwise, as focus moves; a tile made new starts red (its
    -- designer's look) until focus first leaves it. Given the grey of a sibling that is not selected (the game's own
    -- colour) once made; from then on the game's focus handling colours it as its own (checked 20 Nov 2026).
    local focused = false
    pcall(function() focused = tile:HasAnyUserFocus() or tile:IsHovered() end)
    if not focused then
        pcall(function()
            local grey = {R = 0.006, G = 0.001, B = 0.006, A = 0.35}   -- (measured: CREATE LOBBY's, not selected)
            local root = menu.page.WidgetTree.RootWidget
            for _, n in ipairs({"RallyContainer", "TimeAttackContainer"}) do
                local sb = find(root, n)
                local t = sb and sb:GetContent()
                if t and t:IsValid() and t:GetClass():GetFName():ToString():find("Border") then t = t:GetContent() end
                local tb = t and t:IsValid() and find(t.WidgetTree.RootWidget, "TextBorder")
                local c = tb and tb.BrushColor
                if c and c.A < 0.9 then grey = {R = c.R, G = c.G, B = c.B, A = c.A} end
            end
            local mine = find(tile.WidgetTree.RootWidget, "TextBorder")
            if mine then mine:SetBrushColor(grey) end
        end)
    end
    menu.dressed = key
end

local function tile_ok()
    if not (menu.tile and menu.tile:IsValid() and menu.sb and menu.sb:IsValid() and menu.page and menu.page:IsValid()) then
        return false
    end
    -- (still in its place: the game can fill that place again when it builds the page anew)
    local ok, inner = pcall(function() return menu.sb:GetContent() end)
    return ok and inner ~= nil and inner:IsValid() and inner:GetAddress() == menu.tile:GetAddress()
end

local function tile_heal(t)
    -- The tile is where the game's menu shows MULTIPLAYER NOW, not where it once was made (the user, 26 Nov 2026, the
    -- third time: the tile, BACK, SEARCH LOBBIES, BACK, and the tile was gone: the game had a menu or a page of its own
    -- again and the tile still sat on the old one, "in its place" by the old checks). Every half second, in the game's
    -- main menu: the live menu's MULTIPLAYER page and its slot are looked up anew and the tile made there when it
    -- isn't the very one in that very slot. (Looked at twice a second: FindAllOf goes through every object.)
    local main, page, sel = multiplayer_layout()
    if not main then
        if menu.tile and t - (menu.lost_note or -1e9) > 10 then
            menu.lost_note = t
            log("tile: the MULTIPLAYER page not found (main menus: %s)", tostring(menu.n_menus))
        end
        return
    end
    local sb = find(page.WidgetTree.RootWidget, TILE_SLOT)
    if not sb then return end
    local why = nil
    if not (menu.tile and menu.tile:IsValid() and menu.main and menu.main:IsValid() and menu.page and menu.page:IsValid()
            and menu.sb and menu.sb:IsValid()) then
        why = "none"
    elseif menu.main:GetAddress() ~= main:GetAddress() then
        why = "another menu"
    elseif menu.page:GetAddress() ~= page:GetAddress() then
        why = "another page"
    elseif menu.sb:GetAddress() ~= sb:GetAddress() then
        why = "another slot"
    elseif not tile_ok() then
        why = "slot refilled"
    end
    if not why then return end
    menu.tile = nil
    local ok = make_tile(t)
    log("tile: made again (%s): %s", why, ok and "ok" or "failed")
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
local page = nil         -- {w, tree, canvas, buttons = {...}, scrolls = {id -> ScrollBox}, rev}
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
    local v = align(n.va, nil)
    if n.t == "btn" and n.s and not n.fill then         -- (a button with words: its own size, not stretched to the
        if not h and (parent_kind == "col" or parent_kind == "scroll") then h = 1 end   -- room: left in a column,
        if not v and parent_kind == "row" then v = 2 end                                 -- in the middle of a row)
    end
    if h then s:SetHorizontalAlignment(h) end
    if v then pcall(function() s:SetVerticalAlignment(v) end) end
end

local function text_widget(P, n)
    local tb = K.text(P.tree, {size = n.sz or 16, face = n.f or "semi", colour = n.fg or "F4F4F5", spacing = n.sp,
                              shadow = n.sh == true, wrap = n.wrap, justify = n.j, text = n.s or ""})
    if n.max then pcall(function() tb:SetWrapTextAt(n.max + 0.0) end) end
    P.texts[#P.texts + 1] = {w = tb, s = n.s or ""}      -- (in the order texts_of walks: words changed in place)
    return tb
end

-- What a page is made of, its words left out: two trees alike but for their words are drawn once, and the words then
-- set in place (a clock ticking on RANKED redrew the whole page every second: the user, 20 Nov 2026). texts_of walks
-- the tree in the order build() makes the words.
local function shape(n, out)
    if type(n) ~= "table" then
        out[#out + 1] = tostring(n)
        return out
    end
    local keys = {}
    for k in pairs(n) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local words = n.t == "txt" or (n.t == "btn" and n.s ~= nil)
    out[#out + 1] = "{"
    for _, k in ipairs(keys) do
        if not (words and k == "s") and not (n.lv and LIVE_KEYS[k]) then
            out[#out + 1] = tostring(k) .. "="
            shape(n[k], out)
            out[#out + 1] = ","
        end
    end
    out[#out + 1] = "}"
    return out
end

-- A node marked lv (live: WATCH's broadcast, a speedometer's bars, 21 Nov 2026): its size, colours and alpha left out
-- of its shape too, and set in place (P.lives, in the order lives_of walks the tree: as build() makes them)
LIVE_KEYS = {w = true, h = true, bg = true, fg = true, a = true, src = true}   -- (src: a picture swapped, the gauge's arcs)
local function lives_of(n, out)
    if type(n) ~= "table" then return out end
    local t = n.t
    if n.lv and (t == "box" or t == "size" or t == "sp" or t == "txt" or t == "img") then out[#out + 1] = n end
    if t == "col" or t == "row" or t == "stack" or t == "scroll" then
        for _, c in ipairs(n.c or {}) do lives_of(c, out) end
    elseif t == "box" or t == "size" or t == "sp" or (t == "btn" and not n.s) then
        lives_of(n.c, out)
    end
    return out
end

local function set_lives(P, node)
    local now = lives_of(node, {})
    if #now ~= #P.lives then return false end
    for i, n in ipairs(now) do
        local x = P.lives[i]
        if x.t == "box" then
            if n.bg ~= x.bg or n.a ~= x.a then
                x.bg, x.a = n.bg, n.a
                pcall(function() x.w:SetBrushColor(K.lin(n.bg or "-", n.a)) end)
            end
        elseif x.t == "img" then
            if n.src ~= x.src then
                x.src = n.src
                pcall(K.picture, x.pic, x.state, n.src)
            end
        elseif x.t == "txt" then
            if n.fg ~= x.fg then
                x.fg = n.fg
                pcall(function() x.w:SetColorAndOpacity(K.slate(K.lin(n.fg or "F4F4F5"))) end)
            end
        else
            if n.w ~= x.w_ then
                x.w_ = n.w
                pcall(function() x.w:SetWidthOverride((n.w or 0) + 0.0) end)
            end
            if n.h ~= x.h_ then
                x.h_ = n.h
                pcall(function() x.w:SetHeightOverride((n.h or 0) + 0.0) end)
            end
        end
    end
    return true
end

local function texts_of(n, out)
    if type(n) ~= "table" then return out end
    local t = n.t
    if t == "txt" then
        out[#out + 1] = n.s or ""
    elseif t == "btn" then
        if n.s then out[#out + 1] = n.s else texts_of(n.c, out) end
    elseif t == "col" or t == "row" or t == "stack" or t == "scroll" then
        for _, c in ipairs(n.c or {}) do texts_of(c, out) end
    elseif t == "box" or t == "size" or t == "sp" then
        texts_of(n.c, out)
    end
    return out
end

local function shape_of(data)
    return table.concat(shape({page = data.page, dialog = data.dialog or false}, {}))
end

local build_raw
function build(P, n)
    -- a node -> its widget (nil: nothing); sk: slanted (degrees: WATCH's broadcast's slashes)
    local w = build_raw(P, n)
    if w and type(n) == "table" and n.sk then
        pcall(function() w:SetRenderShear({X = n.sk + 0.0, Y = 0.0}) end)
    end
    return w
end

function build_raw(P, n)
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
        if n.lv and P.lives then P.lives[#P.lives + 1] = {t = "box", w = b, bg = n.bg, a = n.a} end
        local cw = build(P, n.c)
        if cw then b:SetContent(cw) end
        return b
    elseif t == "txt" then
        local tb = text_widget(P, n)
        if n.lv and P.lives then P.lives[#P.lives + 1] = {t = "txt", w = tb, fg = n.fg} end
        return tb
    elseif t == "img" then
        local pic = K.image(tree, n.w, n.h)
        -- (a game picture, "ue:...": cropped to fill the box; none in this game: the picture file instead, alt)
        local pst = {}
        local ok = K.picture(pic, pst, n.src)
        if n.lv and P.lives then P.lives[#P.lives + 1] = {t = "img", pic = pic, state = pst, src = n.src} end
        if not ok and n.alt then K.picture(pic, {}, n.alt) end
        local fill = n.fill_crop and ok
        if n.stretch or fill then pcall(function() pic.box:GetContent():SetStretch(n.stretch or 5) end) end
        if fill then pcall(function() pic.box:SetClipping(1) end) end
        return pic.box
    elseif t == "size" or t == "sp" then
        local sb = K.size(tree, nil, n.w, n.h)
        if n.lv and P.lives then P.lives[#P.lives + 1] = {t = "size", w = sb, w_ = n.w, h_ = n.h} end
        if n.clip then pcall(function() sb:SetClipping(1) end) end
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
        -- the bar always there (its room kept): a list just made doesn't know its height yet, so the engine hid the bar
        -- for its first 2-3 frames and the page shook right by the bar's width at every redraw (the user, 24 Nov 2026;
        -- seen in screen captures: 3-5 px for ~30 ms, the bar gone in exactly those frames)
        if n.bar ~= false then
            if not pcall(function() sc:SetAlwaysShowScrollbar(true) end) then
                pcall(function() sc.AlwaysShowScrollbar = true end)
            end
        end
        -- the wheel's / pad's arrows move the focus down a list: the list follows it (EScrollWhenFocusChanges
        -- InstantScroll; the user, 21 Nov 2026)
        pcall(function() sc:SetScrollWhenFocusChanges(1) end)
        -- a thin, dark bar, not the engine's wide white one (a review, 22 Nov 2026); each part on its own: never an error
        if not pcall(function() sc:SetScrollbarThickness({X = 4.0, Y = 4.0}) end) then
            pcall(function() sc.ScrollbarThickness = {X = 4.0, Y = 4.0} end)
        end
        pcall(function()
            local bs = sc.WidgetBarStyle
            local tint = K.slate(K.lin("3A3A44"))
            for _, k in ipairs({"NormalThumbImage", "HoveredThumbImage", "DraggedThumbImage"}) do
                pcall(function() bs[k].TintColor = tint end)
            end
            sc:SetWidgetBarStyle(bs)
        end)
        for _, c in ipairs(n.c or {}) do
            local cw = build(P, c)
            if cw then place("scroll", sc, cw, c) end
        end
        if n.id then P.scrolls[n.id] = sc end
        if n.bottom then                                 -- (a chat: kept at its newest line, at the bottom)
            P.bottoms = P.bottoms or {}
            P.bottoms[#P.bottoms + 1] = sc
        end
        return sc
    elseif t == "edit" then
        -- a box to type in: the game's font; its words go to the app when Enter is pressed or the box is left
        local et = K.new(n.multi and "MultiLineEditableText" or "EditableText", tree)
        pcall(function()
            local st = et.WidgetStyle
            local fi = st.Font
            local fo = StaticFindObject(K.FONT)
            if fo and fo:IsValid() then fi.FontObject = fo end
            fi.Size = n.sz or 18
            fi.TypefaceFontName = FName("Medium")
            st.ColorAndOpacity = K.slate(K.lin(n.fg or "F4F4F5"))
            et:SetFont(fi)
        end)
        pcall(function() et:SetText(FText(n.s or "")) end)
        if n.hint and n.hint ~= "" then pcall(function() et:SetHintText(FText(n.hint)) end) end
        P.edits[#P.edits + 1] = {w = et, id = n.id, had = false, after = #P.buttons}
        if n.w or n.h then return K.size(tree, et, n.w, n.h) end
        return et
    elseif t == "btn" then
        local btn = K.new("Button", tree)
        local st = btn.WidgetStyle
        for _, k in ipairs({"Normal", "Hovered", "Pressed", "Disabled"}) do st[k].DrawAs = 0 end
        st.NormalPadding = K.pad(0)
        st.PressedPadding = K.pad(0)
        btn:SetStyle(st)
        local b = K.panel(tree, {fill = n.bg or "-", alpha = n.a, radius = n.r, outline = n.ol, outline_w = n.olw,
                                 pad = type(n.p) == "table" and n.p or (n.p and {n.p, n.p, n.p, n.p}) or nil})
        -- its words in its middle; what it holds otherwise (a list's row, a tile) across all of it (cal: as asked)
        b:SetHorizontalAlignment(align(n.cal or (n.s and "c" or "f"), 2))
        b:SetVerticalAlignment(n.s and 2 or 0)
        local texts = {}
        local cw
        if n.s then                          -- (a plain button: its words)
            cw = text_widget(P, {s = n.s, sz = n.sz or 18, f = n.f or "semi", fg = n.fg or "F4F4F5", sp = n.sp})
            texts[1] = cw
        else
            cw = build(P, n.c)
        end
        if cw then b:SetContent(cw) end
        -- the panel across the whole button: its place in the button (a ButtonSlot) centres it by default
        local bs = btn:SetContent(b)
        pcall(function()
            bs = (bs and bs:IsValid()) and bs or b.Slot
            bs:SetPadding(K.pad(0))
            bs:SetHorizontalAlignment(0)
            bs:SetVerticalAlignment(0)
        end)
        P.buttons[#P.buttons + 1] = {btn = btn, box = b, id = n.id, fid = n.fid, foc = n.foc, look = 0,
                                     bg = n.bg or "-", a = n.a, hov = n.hov or n.bg or "-",
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
    local P = {w = w, tree = tree, canvas = canvas, buttons = {}, scrolls = {}, edits = {}, texts = {}, lives = {}}
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
        -- (the page's own buttons out of the arrows' reach meanwhile: only the question's: a review, 21 Nov 2026)
        for _, b in ipairs(P.buttons) do pcall(function() b.btn:SetIsFocusable(false) end) end
        P.behind = #P.buttons
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

-- WATCH's broadcast (0.2, the app's ig_watch.py): drawn over the stage from data.overlay, never taking a click or a key,
-- no backdrop; its words set in place when only they change (a clock ticking), made again otherwise.
local ov = nil             -- {w, tree, texts, buttons, scrolls, edits, shape, k}

-- The broadcast's size for this screen: its panels are laid out in 1080-tall units, so on a narrower screen than 21:9
-- they take more of its width (the user's players at 16:9, 27 Nov 2026: "a bit too big compared to the screen").
-- Full size from 21:9 up, smaller with a narrower screen, never under 80 %. -> k, the screen's {w, h} in units
local WLL = nil
local function ov_scale()
    local k, w, h = 1.0, 1920.0, 1080.0
    pcall(function()
        if not (WLL and WLL:IsValid()) then WLL = StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary") end
        local world = UEHelpers.GetWorld()
        local size, sc = WLL:GetViewportSize(world), WLL:GetViewportScale(world)
        if size and sc and sc > 0 and size.X > 0 and size.Y > 0 then
            w, h = size.X / sc, size.Y / sc
            k = math.max(0.8, math.min(1.0, (w / h) / (21 / 9)))
        end
    end)
    return k, w, h
end

local function drop_overlay()
    if ov and ov.w and ov.w:IsValid() then ov.w:RemoveFromParent() end
    ov = nil
end

local function overlay(node)
    if type(node) ~= "table" then
        if ov then drop_overlay() end
        return
    end
    local sh = table.concat(shape(node, {}))
    local k, sw, shh = ov_scale()
    if ov and ov.shape == sh and ov.k == k and ov.w:IsValid() and ov.w:IsInViewport() then
        local words = texts_of(node, {})
        if #words == #ov.texts and set_lives(ov, node) then
            for i, s in ipairs(words) do
                local x = ov.texts[i]
                if x.s ~= s then
                    x.s = s
                    pcall(function() x.w:SetText(FText(s)) end)
                end
            end
            return
        end
    end
    drop_overlay()
    local gi = UEHelpers.GetGameInstance()
    if not (gi and gi:IsValid()) then return end
    local w = K.new("UserWidget", gi)
    local tree = K.new("WidgetTree", w)
    w.WidgetTree = tree
    local canvas = K.new("CanvasPanel", tree)
    tree.RootWidget = canvas
    w:AddToViewport(Z - 10)
    local P = {w = w, tree = tree, canvas = canvas, buttons = {}, scrolls = {}, edits = {}, texts = {}, lives = {}}
    local body = build(P, node)
    if body then
        local s = canvas:AddChildToCanvas(body)
        if k < 1.0 then
            -- laid out over a screen 1/k as big, then drawn k as big from the top left: the same layout, smaller
            s:SetAnchors({Minimum = {X = 0.0, Y = 0.0}, Maximum = {X = 0.0, Y = 0.0}})
            s:SetAlignment({X = 0.0, Y = 0.0})
            s:SetPosition({X = 36.0, Y = 30.0})
            s:SetSize({X = (sw - 72.0) / k, Y = (shh - 60.0) / k})
            body:SetRenderTransformPivot({X = 0.0, Y = 0.0})
            body:SetRenderScale({X = k, Y = k})
        else
            s:SetAnchors({Minimum = {X = 0.0, Y = 0.0}, Maximum = {X = 1.0, Y = 1.0}})
            s:SetOffsets({Left = 36.0, Top = 30.0, Right = 36.0, Bottom = 30.0})
        end
    end
    -- (with a button in it, RANKED's chat: the mouse reaches it; anything else over the stage never takes a click)
    w:SetVisibility(#P.buttons > 0 and K.SELF_HIT or K.NOT_HIT)
    P.shape, P.k = sh, k
    ov = P
end

local function drop_page()
    if page and page.w and page.w:IsValid() then page.w:RemoveFromParent() end
    page = nil
end

-- RANKED's chat on the stage (the app's ig_chat.py, 22 Nov 2026): T opens a box to write a line, the keyboard the
-- box's alone meanwhile (the game's input to the UI: the car isn't driven by the letters typed); Enter sends it, Esc
-- puts it away. Only while the app says the chat is on the stage (data.chat).
local chatbox = nil      -- {w, e (the EditableText), had (it had the keyboard), esc_t}
local function chat_input(pc, ui)
    pcall(function()
        local wbl = StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary")
        if ui then
            wbl:SetInputMode_UIOnlyEx(pc, ui, 0, false)
        else
            wbl:SetInputMode_GameOnly(pc, false)
        end
    end)
end

local function chat_close(t)
    if chatbox and chatbox.w and chatbox.w:IsValid() then chatbox.w:RemoveFromParent() end
    chatbox = nil
    chat_input(UEHelpers.GetPlayerController(), nil)
    tell("chatkey", "idle")
end

local function chat_open(t)
    local gi = UEHelpers.GetGameInstance()
    if not (gi and gi:IsValid()) then return end
    local w = K.new("UserWidget", gi)
    local tree = K.new("WidgetTree", w)
    w.WidgetTree = tree
    local canvas = K.new("CanvasPanel", tree)
    tree.RootWidget = canvas
    w:AddToViewport(Z + 20)
    local P = {w = w, tree = tree, canvas = canvas, buttons = {}, scrolls = {}, edits = {}, texts = {}, lives = {}}
    local body = build(P, {t = "box", bg = "0A1428", a = 0.94, p = {14, 10, 14, 10}, ol = "FF2D3A", olw = 2,
                           c = {t = "size", w = 492, c = {t = "edit", id = "chat", s = "", sz = 17,
                                                          hint = "Write to the others, Enter to send"}}})
    if not body then w:RemoveFromParent() return end
    local s = canvas:AddChildToCanvas(body)
    s:SetAutoSize(true)
    s:SetAnchors({Minimum = {X = 0.0, Y = 1.0}, Maximum = {X = 0.0, Y = 1.0}})
    s:SetAlignment({X = 0.0, Y = 1.0})
    s:SetPosition({X = 36.0, Y = -250.0})
    local e = P.edits[1]
    if not e then w:RemoveFromParent() return end
    chatbox = {w = w, e = e.w, had = false, t = t}
    pcall(function() w:SetIsFocusable(true) end)
    chat_input(UEHelpers.GetPlayerController(), e.w)
    pcall(function() e.w:SetKeyboardFocus() end)
    tell("chatkey", "typing")
end

local function chat_tick(t, key, on_stage)
    if chatbox then
        if not on_stage or not (chatbox.w and chatbox.w:IsValid()) then chat_close(t) return end
        if key == "ESCAPE" then
            chatbox.esc_t = t
            if not chatbox.had then chat_close(t) return end
        end
        local f = false
        pcall(function() f = chatbox.e:HasKeyboardFocus() end)
        if f then chatbox.had = true end
        if chatbox.had and not f then                   -- (Enter, or the box left: sent unless Esc left it)
            if not (chatbox.esc_t and t - chatbox.esc_t < 0.4) then
                local ok, words = pcall(function() return chatbox.e:GetText():ToString() end)
                if ok and words and words:gsub("%s", "") ~= "" then tell("chat", words) end
            end
            chat_close(t)
        elseif not chatbox.had and t - chatbox.t > 1.0 then
            pcall(function() chatbox.e:SetKeyboardFocus() end)   -- (the keyboard not on it yet: once more)
        end
        return
    end
    if not on_stage then return end
    if key == "T" then
        chat_open(t)
    elseif key == "PAGE_UP" or key == "PAGE_DOWN" then
        tell("chatkey", key == "PAGE_UP" and "up" or "down")
    end
end

local function game_menu(on)
    -- the game's own menu put away while ours is on screen (none of its buttons under ours), and back
    -- (back on: the one put away, not another found meanwhile; put away: the live one, else the one the tile is on)
    local main = on and menu.hidden_main or main_menu() or (menu.main and menu.main:IsValid() and menu.main or nil)
    if main and main:IsValid() then
        if not on and not menu.main_vis then menu.main_vis = main:GetVisibility() end
        -- The game's menu is a CommonUI screen: while active, its own input (the wheel's / pad's Select, Back, tabs,
        -- and its navigation set-up) still worked under ours, hidden or not: a wheel's OK took testers to the game's
        -- own places, its tabs changed behind ours (25 Nov 2026). Deactivated while ours is up, as the game does when
        -- it covers it with a screen of its own, and active again after (checked in the game: it comes back on the
        -- same tab, the tile focused).
        if not on then pcall(function() if main:IsActivated() then main:DeactivateWidget() end end) end
        main:SetVisibility(on and (menu.main_vis or K.VISIBLE) or K.COLLAPSED)
        if on then pcall(function() if not main:IsActivated() then main:ActivateWidget() end end) end
        if on then menu.main_vis = nil end
        -- (and switched off: hidden, it still took the wheel's own presses, its Down / Select going through the game's
        -- menu behind ours: a stage loading, a leaderboard opening; the user, 22 Nov 2026)
        pcall(function() main:SetIsEnabled(on) end)
        menu.hidden_main = not on and main or nil
    end
end

-- The wheel's / pad's arrows (0.2, 21 Nov 2026): the app sends the arrow keys for them, but the wheel's own press
-- reaches the game too, and its hidden main menu takes the keyboard focus off the pages: the key then moved nothing.
-- So while the pages are on screen, the focus is put back on the last button of theirs that had it (focus_guard);
-- the wheel's Select clicks the focused button (cmd "press").
local show, focus_guard          -- (defined below: press_focused / the commands use them)
-- One press, one click: a wheel's or pad's OK can reach the pages twice, as the game's own press of the focused button
-- and as the app's cmd "press" a moment later; the second then clicked whatever the first had opened (testers, 25 Nov
-- 2026: "it moved them to some random places"). A click within ONE_PRESS_S of the last one is dropped.
local ONE_PRESS_S = 0.6
local click_t = -1e9
local function click_once(id)
    local t = os.clock()
    if t - click_t < ONE_PRESS_S then
        print("[ACRDailyApp] second click dropped: " .. tostring(id) .. "\n")
        return
    end
    click_t = t
    if id == "close" then show(false) else tell("click", id) end
end
local function press_focused()
    if not page then return end
    for _, b in ipairs(page.buttons) do
        if b.btn:IsValid() and b.btn:HasKeyboardFocus() and b.id then
            click_once(b.id)
            return
        end
    end
end

local function focus_on(id)
    -- the keyboard (and a game pad: the game's UI moves between focusable widgets) on the button with that id, or on
    -- the one the app names (data.focus: the tab on screen), or on the first -> whether one took it
    if not page then return false end
    local want = id or (state.data and state.data.focus)
    for _, e in ipairs(page.edits) do                    -- (a box to type in named: a question that wants words)
        if want and e.id == want and e.w:IsValid() then
            e.w:SetKeyboardFocus()
            return true
        end
    end
    local first = nil
    for _, b in ipairs(page.buttons) do
        if b.btn:IsValid() then
            first = first or b
            if want and (b.id == want or b.fid == want) then
                b.btn:SetKeyboardFocus()
                -- (its list scrolled to it: the app moves the wheel's focus itself now, ignav.py)
                for _, sc in pairs(page.scrolls) do
                    pcall(function() sc:ScrollWidgetIntoView(b.btn, false, 0, 24.0) end)
                end
                return true
            end
        end
    end
    if first and not id then
        first.btn:SetKeyboardFocus()
        return true
    end
    return false
end

local function focused_id()
    if not page then return nil end
    for _, b in ipairs(page.buttons) do
        if b.btn:IsValid() and b.btn:HasKeyboardFocus() then return b.id or b.fid end   -- (fid: a list's row)
    end
    return nil
end

local guard = {b = nil, page = nil, put_back = 0}
function focus_guard(t)
    -- Every frame the pages are up: the keyboard focus still on one of their buttons (or boxes)? The one that had it is
    -- looked at first (one call); lost, the others; none has it (the game's hidden menu took it: a wheel's or pad's own
    -- press reaches the game too), it is put back on the one that had it, else on what the app names.
    if guard.page ~= page then guard.b, guard.page = nil, page end
    local b = guard.b
    if b and b.btn:IsValid() and b.btn:HasKeyboardFocus() then return end
    for _, x in ipairs(page.buttons) do
        if x.btn:IsValid() and x.btn:HasKeyboardFocus() then guard.b = x return end
    end
    for _, e in ipairs(page.edits) do
        if e.w:IsValid() and e.w:HasKeyboardFocus() then return end
    end
    guard.put_back = guard.put_back + 1
    if guard.put_back <= 5 or guard.put_back % 50 == 0 then
        print(string.format("[ACRDailyApp] focus put back on the pages (%d)\n", guard.put_back))
    end
    if b and b.btn:IsValid() then
        b.btn:SetKeyboardFocus()
        if b.btn:HasKeyboardFocus() then return end
    end
    focus_on(nil)
end

function show(on)               -- (the local declared above)
    if on == shown then return end
    shown = on
    if on then
        game_menu(false)
        if page then page.w:SetVisibility(K.SELF_HIT) end
        pcall(focus_on, nil)
        tell("open")
    else
        if page then page.w:SetVisibility(K.COLLAPSED) end
        game_menu(true)
        local ok, e = pcall(to_multiplayer)
        if not ok then print("[ACRDailyApp] to MULTIPLAYER: " .. tostring(e) .. "\n") end
        pcall(function()
            if menu.tile and menu.tile:IsValid() then menu.tile:SetKeyboardFocus() end
        end)
        menu.refocus_t = os.clock() + 0.25           -- (and again once the tab's switch has run: tick)
        tell("close")
    end
end

local function redraw()
    -- the app's pages, made again (a new rev): where each list was scrolled to kept. Only words changed: set in place.
    local new_shape = shape_of(state.data)
    if page and page.shape == new_shape and page.w:IsValid() then
        local words = texts_of(state.data.page, {})
        texts_of(state.data.dialog, words)
        if #words == #page.texts and set_lives(page, state.data.page) then
            for i, s in ipairs(words) do
                local x = page.texts[i]
                if x.s ~= s then
                    x.s = s
                    pcall(function() x.w:SetText(FText(s)) end)
                end
            end
            return
        end
    end
    local offsets = {}
    if page then
        for id, sc in pairs(page.scrolls) do
            local ok, o = pcall(function() return sc:GetScrollOffset() end)
            if ok then offsets[id] = o end
        end
    end
    local had = nil
    if shown then pcall(function() had = focused_id() end) end
    drop_page()
    page = make_page(state.data)
    if not page then return end
    page.shape = new_shape
    local dialog = state.data.dialog ~= nil
    if shown then          -- (the keyboard where it was: the same button, if still there; a question come or gone: on
        pcall(function()   -- what the app names, its button or the tab)
            if dialog ~= menu.had_dialog or state.data.focus ~= menu.focus_hint or not (had and focus_on(had)) then
                focus_on(nil)                           -- (a question come or gone, another tab: on what the app names)
            end
        end)
    end
    menu.had_dialog = dialog
    menu.focus_hint = state.data.focus
    if next(offsets) or page.bottoms then pcall(function() page.w:ForceLayoutPrepass() end) end
    for id, o in pairs(offsets) do
        local sc = page.scrolls[id]
        if sc then pcall(function() sc:SetScrollOffset(o) end) end
    end
    for _, sc in ipairs(page.bottoms or {}) do pcall(function() sc:ScrollToEnd() end) end
    -- (and again for a few frames: a list just made has no height yet, so the first set can be cut to the top, the
    -- page jumping up when a car was picked, the user 22 Nov 2026)
    if next(offsets) or page.bottoms then page.keep = {offsets = offsets, n = 6} end
    page.w:SetVisibility(shown and K.SELF_HIT or K.COLLAPSED)
end

local function keep_scrolls()
    local k = page and page.keep
    if not k then return end
    k.n = k.n - 1
    local bottom = {}
    for _, sc in ipairs(page.bottoms or {}) do
        bottom[sc] = true
        pcall(function() sc:ScrollToEnd() end)
    end
    for id, o in pairs(k.offsets) do
        local sc = page.scrolls[id]
        if sc and not bottom[sc] then
            pcall(function()
                if math.abs(sc:GetScrollOffset() - o) > 0.5 then sc:SetScrollOffset(o) end
            end)
        end
    end
    if k.n <= 0 then page.keep = nil end
end

-- One highlight at a time (the user, 22 Nov 2026: "2 highlighted tiles, one with mouse and one with controller"): the
-- mouse's hover look only while the mouse is the one in use (it moved since the keys / wheel / pad last moved the
-- focus), and the focus follows the mouse onto the button it moves over.
local WLL = nil
local function mouse_moved()
    local ok, p = pcall(function()
        if not (WLL and WLL:IsValid()) then WLL = StaticFindObject("/Script/UMG.Default__WidgetLayoutLibrary") end
        return WLL:GetMousePositionOnPlatform()
    end)
    if not (ok and p) then return false end
    local moved = menu.mx ~= nil and (math.abs(p.X - menu.mx) + math.abs(p.Y - menu.my)) > 2
    menu.mx, menu.my = p.X, p.Y
    return moved
end

local function one_highlight()
    if mouse_moved() then
        menu.mouse_on = true
        for _, b in ipairs(page.buttons) do                -- (the focus onto what the mouse is over: Enter acts on it)
            if b.btn:IsValid() and b.btn:IsHovered() then
                if not b.btn:HasKeyboardFocus() then pcall(function() b.btn:SetKeyboardFocus() end) end
                break
            end
        end
    end
    local f = nil
    for _, b in ipairs(page.buttons) do
        if b.btn:IsValid() and b.btn:HasKeyboardFocus() then f = b break end
    end
    if f ~= menu.last_focus then
        if f and not f.btn:IsHovered() then menu.mouse_on = false end   -- (moved by the keys / wheel / pad)
        menu.last_focus = f
    end
end

local function buttons(t)
    -- hover looks and clicks: a press let go over the button (or with the keyboard on it) is a click
    if not page then return end
    local poll_all = frame % 3 == 0
    if poll_all then pcall(one_highlight) end
    if frame % 6 == 0 then                               -- (where the keyboard / wheel / pad is: told to the app, which
        local f = ""                                     -- moves it across a page's columns: ingameapp.nav_tick)
        for _, b in ipairs(page.buttons) do
            if b.btn:IsValid() and b.btn:HasKeyboardFocus() then f = b.id or b.fid or "" end
        end
        if f ~= menu.told_focus then menu.told_focus = f tell("focus", f) end
    end
    for _, b in ipairs(page.buttons) do
        if b.btn:IsValid() then
            if poll_all or b.hover or b.pressed then
                -- under the mouse: its hover colour; the keyboard / wheel / pad on it: its focus colour (foc: a list's
                -- row, whose hover grey is its panel's own, showed nothing as the wheel went down it: 21 Nov 2026)
                local mouse = menu.mouse_on and b.btn:IsHovered()
                local kb = not mouse and b.btn:HasKeyboardFocus()
                local h = mouse or kb
                local look = mouse and 1 or (kb and 2 or 0)
                if look ~= b.look then
                    b.look = look
                    b.hover = h
                    b.box:SetBrushColor(K.lin(mouse and b.hov or (kb and (b.foc or b.hov)) or b.bg, b.a))
                    if b.hfg then
                        for _, tb in ipairs(b.texts) do tb:SetColorAndOpacity(K.slate(K.lin(h and b.hfg or b.fg))) end
                    end
                end
                local p = b.btn:IsPressed()
                if p ~= b.pressed then
                    if p and b.btn:IsHovered() then menu.mouse_on = true end   -- (a click: the mouse in use)
                    -- (let go over it with the mouse in use, or with the focus on it: a press "under the mouse" while
                    -- the wheel / pad was the one in use is not a click: CommonUI can press where the resting cursor is)
                    if b.pressed and not p and ((menu.mouse_on and b.btn:IsHovered()) or b.btn:HasKeyboardFocus())
                            and b.id then
                        click_once(b.id)
                    end
                    b.pressed = p
                end
            end
        end
    end
end

local typing = {on = nil, esc_t = nil}     -- the box being typed in (nothing is drawn again meanwhile: its words
                                           -- would go), and when Esc was pressed in it (not sent)
local function edits(t)
    -- a box typed in, then left (Enter, a click elsewhere, Esc): its words to the app, unless Esc left it
    if not page then return end
    local now_on = nil
    for _, e in ipairs(page.edits) do
        if e.w:IsValid() then
            local f = e.w:HasKeyboardFocus()
            if f then now_on = e end
            if e.had and not f then
                if not (typing.esc_t and t - typing.esc_t < 0.4) and e.id then
                    local ok, words = pcall(function() return e.w:GetText():ToString() end)
                    tell("text", e.id .. " " .. (ok and words or ""))
                end
                -- left by Enter / Esc, the keyboard nowhere: on the button after the box (FIND, SEND, OK), so the
                -- arrows and a wheel / pad go on working (a review, 21 Nov 2026)
                local any = false
                for _, b in ipairs(page.buttons) do
                    if b.btn:IsValid() and b.btn:HasKeyboardFocus() then any = true break end
                end
                local nb = page.buttons[(e.after or 0) + 1] or page.buttons[#page.buttons]
                if not any and nb and nb.btn:IsValid() then pcall(function() nb.btn:SetKeyboardFocus() end) end
            end
            e.had = f
        end
    end
    typing.on = now_on
end

local WBL_ = nil
local function let_go_of_keys()
    -- the keyboard out of a box being typed in (Esc): to the page's root, so the next Esc closes the pages
    pcall(function()
        if page and page.w:IsValid() then
            page.w:SetIsFocusable(true)
            page.w:SetKeyboardFocus()
        end
    end)
end

--- (this file about to be loaded again, testing: its pages away, the game's menu back; the tile is kept and taken over)
function M.unload()
    if shown then show(false) end
    drop_page()
    drop_overlay()                                       -- (WATCH's broadcast: not left behind by a dev reload)
    if f then f:close() f = nil end
    if ev_f then ev_f:close() ev_f = nil end
end

-- ---------------------------------------------------------------------- every frame
local world_at, world_name = nil, nil
-- The game taken to its stages by ACR DAILY: a DRIVE or CONTINUE done here, or the game started by the app with the
-- set-up in its save (data.own: when the app started it, taken in the first main menu of a game started just after).
-- Kept until the game's main menu is back from a stage, and told to main.lua (_G.ACRDAILY_OURS: in ingame-setup.txt):
-- a stage the player got to any other way doesn't count (the user, 21 Nov 2026: a Rally Weekend set up by hand with a
-- daily's settings must do nothing).
local ours = false
local watched = false             -- (a stage the game went to for WATCH: not ours, but ACR DAILY opens after it all the same)
local LOADED = os.time()
local own_used = nil
local function set_ours(v)
    ours = v
    _G.ACRDAILY_OURS = v
end
set_ours(false)
local function drive_tell(what, rest)
    if what == "drive" and type(rest) == "string" and rest:match("^%d+ ok") then set_ours(true) end
    tell(what, rest)
end
local function new_world()
    -- A level loaded (a stage, or back to the menu): every widget kept from the old one is gone with it, and its
    -- memory may hold other objects now (still "valid" to IsValid). They are only forgotten, never touched again: the
    -- tile is made anew on MULTIPLAYER, the pages drawn anew when opened. (Touching them crashed the game on the way
    -- back from a stage, 20 Nov 2026.)
    local cmd_n = menu.cmd_n
    menu = {cmd_n = cmd_n}
    page = nil
    ov = nil                                             -- (WATCH's broadcast: gone with the old level, made anew)
    if shown then
        shown = false
        tell("close")
    end
    K.forget_textures()
end

-- (testing only: while %APPDATA%\ACR Daily\app-dev.on exists, a probe.lua put next to it is run once, then deleted)
local DEV_DIR = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\"
local function dev_probe()
    local flag = io.open(DEV_DIR .. "app-dev.on", "r")
    if not flag then return end
    flag:close()
    local pf = io.open(DEV_DIR .. "probe.lua", "r")
    if not pf then return end
    pf:close()
    local ok, e = pcall(dofile, DEV_DIR .. "probe.lua")
    os.remove(DEV_DIR .. "probe.lua")
    print("[PROBE] done " .. tostring(ok) .. " " .. tostring(e) .. "\n")
end

function M.tick(t)
    frame = frame + 1
    if frame % 30 == 0 then pcall(dev_probe) end
    local okw, wa, wname = pcall(function()
        local w = UEHelpers.GetWorld()
        if not (w and w:IsValid()) then return nil, nil end
        return w:GetAddress(), w:GetFullName()
    end)
    if not okw then wa, wname = nil, nil end
    if wa ~= world_at then
        if world_at ~= nil then new_world() end
        -- back in the game's main menu from a stage (GO TO MAIN MENU, QUIT): ACR DAILY opens, not the game's own menu
        -- (the user, 20 Nov 2026: "it should go to the ACR Daily app... let's be consistent")
        -- Only after a stage ACR DAILY took the game to (its DRIVE / CONTINUE here): the game's own modes (FREE
        -- PRACTICE...) go back to the game's menu as usual (21 Nov 2026).
        local to_menu = wname and wname:find("MainMenu", 1, true) ~= nil
        if to_menu and world_name and not world_name:find("MainMenu", 1, true) then
            if ours or watched then menu.open_on_menu = t end
            set_ours(false)
            watched = false
        end
        world_at, world_name = wa, wname
    end
    if not wa then return end                            -- (between levels: nothing to touch)
    -- the car at the finish line kept (drive.lua): whether the app is there or not at that moment
    if drive and drive.finish_tick then pcall(drive.finish_tick) end
    pcall(keep_scrolls)
    if frame % 6 == 0 then poll_file(t) end
    local alive = app_alive(t)
    -- COPILOT (the app's copilot.py): a crew's stage on, the game's own co-driver off (main.lua codriver_off)
    _G.ACRDAILY_COPILOT = alive and type(state.data) == "table" and state.data.copilot == 1 or nil
    -- an event without driving aids, its run on the start line: main.lua switches them off (force_aids_off)
    _G.ACRDAILY_AIDS_OFF = alive and type(state.data) == "table" and state.data.aidsOff == 1 or nil
    local own = alive and type(state.data) == "table" and tonumber(state.data.own)
    if own and own ~= own_used and LOADED >= own - 5 and LOADED - own < 300 and
            world_name and world_name:find("MainMenu", 1, true) then
        own_used = own
        set_ours(true)
    end
    local key = rawget(_G, "ACRDAILY_APPKEY")
    _G.ACRDAILY_APPKEY = nil
    local clicked = rawget(_G, "ACRDAILY_TILE_CLICKED")
    _G.ACRDAILY_TILE_CLICKED = nil

    -- the tile: on MULTIPLAYER while the app runs (made again after the menu is: a stage and back)
    if frame % 30 == 0 then
        if alive and world_name and world_name:find("MainMenu", 1, true) then
            pcall(tile_heal, t)
        end
        if tile_ok() then
            menu.sb:SetVisibility(alive and K.SELF_HIT or K.COLLAPSED)
        end
    end
    if tile_ok() and alive and t - (menu.made_t or t) > 0.3 then dress_tile(state.data.tile) end
    if menu.refocus_t and t >= menu.refocus_t then       -- (ACR DAILY closed: the tile focused once its tab is on)
        menu.refocus_t = nil
        if not shown and tile_ok() then pcall(function() menu.tile:SetKeyboardFocus() end) end
    end

    if not alive then
        if shown then show(false) end
        if page then drop_page() end
        return
    end
    if state.changed and not (shown and typing.on) then      -- (not while a box is typed in: drawn once it's left)
        state.changed = false
        if state.data.page == nil then
            -- (on a stage the app sends no page: none kept either, made anew in the menus: 21 Nov 2026)
            if page and not shown then drop_page() end
        elseif page or shown then
            redraw()
        end
        if state.data.open and not shown and state.data.page ~= nil then
            if not page then redraw() end
            show(true)
        end
    end
    -- the app's commands, each done once (data.cmd = {n, do}): "close" (B on a game pad, the app reads the pad);
    -- "drive" (DRIVE: the set-up made in the running game and the game on to the Service Park, drive.lua)
    local cmd = state.data.cmd
    if type(cmd) == "table" and cmd.n ~= menu.cmd_n then
        local first = menu.cmd_n == nil                      -- (the first one seen was for an earlier opening)
        menu.cmd_n = cmd.n
        if not first and cmd["do"] == "close" and shown then show(false) end
        if not first and cmd["do"] == "select" and not shown then menu.select_t = t end   -- (the wheel's Select: below)
        if not first and cmd["do"] == "focus" and shown and type(cmd.id) == "string" then pcall(focus_on, cmd.id) end
        if not first and cmd["do"] == "press" and shown then
            pcall(focus_guard, t)                            -- (the focus back on the pages first, if the game took it)
            local ok, e = pcall(press_focused)
            if not ok then print("[ACRDailyApp] press: " .. tostring(e) .. "\n") end
        end
        if cmd["do"] == "liveries" and drive and drive.rescan_liveries then pcall(drive.rescan_liveries) end
        -- "quit": the game closed the engine's own way (COMMUNITY: a stage installed with the game closed, then it
        -- starts again; a window's close message only opened the game's "quit?" question, and nothing happened, a
        -- driver 24 Nov 2026)
        if not first and cmd["do"] == "quit" then
            pcall(function()
                local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
                ksl:QuitGame(UEHelpers.GetWorld(), UEHelpers.GetPlayerController(), 0, false)
            end)
        end
        -- "menu": back to the game's main menu from a stage (a crew's co-driver whose host left: the app's copilot.py)
        if not first and cmd["do"] == "menu" and drive and drive.to_menu then
            local ok, e = pcall(drive.to_menu)
            if not ok then print("[ACRDailyApp] menu: " .. tostring(e) .. "\n") end
        end
        if not first and cmd["do"] == "drive" then
            if not drive then
                tell("drive", tostring(cmd.n) .. " error no drive.lua")
            elseif drive.start(cmd.n, cmd.setup, cmd.watch and tell or drive_tell, t) and shown then   -- (WATCH: not ours)
                watched = cmd.watch == true
                show(false)                                  -- (the game's own screens from here: the Service Park)
            end
        end
    end
    if drive then drive.tick(t) end
    -- WATCH's broadcast over the stage: each new state from the app (not over the pages, not in the game's menus)
    local on_stage = world_name and not world_name:find("MainMenu", 1, true)
    if on_stage and frame % 15 == 0 then                 -- (not over the game's PAUSE menu: looked at 4 times a second)
        local ok, p = pcall(function()
            return StaticFindObject("/Script/Engine.Default__GameplayStatics"):IsGamePaused(UEHelpers.GetWorld())
        end)
        menu.paused = ok and p == true
    end
    local want_ov = on_stage and not shown and not menu.paused and state.data.overlay or nil
    if state.rev ~= menu.ov_rev or (want_ov == nil) ~= (ov == nil) then
        menu.ov_rev = state.rev
        pcall(overlay, want_ov)
    end
    -- RANKED's chat on the stage: T to write, Page Up / Down to scroll back (chat_tick); or a click on it (its button
    -- "chat:open" in the overlay: the overlay then lets the mouse through to its buttons alone)
    local chat_on = on_stage and not shown and not menu.paused and state.data.chat == true
    if ov and ov.w and ov.w:IsValid() and #(ov.buttons or {}) > 0 then
        for _, b in ipairs(ov.buttons) do
            local okp, p = pcall(function() return b.btn:IsPressed() end)
            p = okp and p == true
            if p and not b.pressed and b.id == "chat:open" and chat_on and not chatbox then pcall(chat_open, t) end
            -- (its TURN OFF button, 28 Nov 2026: the app turns the chat off, the overlay goes with the next data)
            if p and not b.pressed and b.id == "chat:off" then
                if chatbox then pcall(chat_close, t) end
                tell("chatkey", "off")
            end
            b.pressed = p
        end
    end
    pcall(chat_tick, t, key, chat_on)
    -- ... and its keys (the keyboard's arrows: the driver before / after, the camera; Enter: the spectator menu)
    if want_ov and not chatbox and (key == "LEFT_ARROW" or key == "RIGHT_ARROW" or key == "UP_ARROW" or
                                    key == "DOWN_ARROW" or key == "RETURN") then
        tell("watchkey", ({LEFT_ARROW = "left", RIGHT_ARROW = "right", UP_ARROW = "up", DOWN_ARROW = "down",
                           RETURN = "select"})[key])
    end
    -- back from a stage: ACR DAILY opened once the game's menu (and so the tile) is up
    if menu.open_on_menu and not shown and tile_ok() and t - menu.open_on_menu > 1.0 then
        menu.open_on_menu = nil
        if not page then redraw() end
        if page then show(true) end
    end
    -- opened: the tile clicked, or Enter on it (the key, or the wheel's / pad's Select the app saw: cmd "select")
    local selected = menu.select_t ~= nil and t - menu.select_t < 0.5
    menu.select_t = nil
    local enter_on_tile = (key == "RETURN" or selected) and not shown and tile_ok() and
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
        if (key == "Q" or key == "E") and not typing.on then   -- (the game's own tab keys: the tab before / after)
            tell("tab", key == "Q" and "prev" or "next")
        elseif (key == "LEFT_ARROW" or key == "RIGHT_ARROW") and not typing.on then
            tell("arrow", key == "LEFT_ARROW" and "left" or "right")   -- (across a page's columns: the app, across())
        elseif key == "ESCAPE" and typing.on then           -- (Esc in a box: out of it, its words not sent)
            typing.esc_t = t
            let_go_of_keys()
        elseif key == "ESCAPE" and state.data.dialog then
            tell("click", "cancel")                      -- (a question up: Esc answers no, as B on a pad does)
        elseif key == "ESCAPE" and state.data.prep then
            tell("back", "")                             -- (DRIVE's set-up screen: back to the tab, the app's back())
        elseif key == "ESCAPE" then
            show(false)
        else
            edits(t)                                     -- (first: words typed then OK clicked come in that order)
            buttons(t)
        end
        if page and not typing.on then pcall(focus_guard, t) end
        if page and not page.w:IsInViewport() then          -- (a level loaded: the viewport emptied)
            page = nil
            shown = false
        end
    end
end

return M
