-- ACR Daily's in-game displays: the building blocks (hud.lua lays the displays out with them).
--
-- Every widget is made once from Lua (StaticConstructObject on the UMG classes, as the game's own would be from a
-- blueprint) and only what changes is set again. Checked in this game (Unreal 5.4, UE4SS 3.0.1, 19 Nov 2026): rounded
-- panels with an outline (Slate's RoundedBox brush), pictures from a PNG file (KismetRenderingLibrary's
-- ImportFileAsTexture2D), the game's font in its five weights, with Japanese and Chinese through its own fallback,
-- progress bars, blur, shear, and opacity / position / scale animated a frame at a time.
local UEHelpers = require("UEHelpers")

local K = {}

K.VISIBLE, K.COLLAPSED, K.HIDDEN, K.NOT_HIT, K.SELF_HIT = 0, 1, 2, 3, 4   -- ESlateVisibility (NOT_HIT: drawn, never
                                                     -- takes a click or the keyboard; SELF_HIT: its children may)
K.FONT = "/Game/Data/UI/Fonts/Rajdhani-Medium_Font.Rajdhani-Medium_Font"   -- the game's own UI font
K.FACES = {light = "Light", regular = "Regular", medium = "Medium", semi = "SemiBold", bold = "Bold"}

-- ---------------------------------------------------------------------- colours
local lin_cache = {}
--- 'RRGGBB' or 'RRGGBBAA' (sRGB, as the app's colours) [, alpha 0..1 over it] -> FLinearColor; '-' / nil: clear
function K.lin(hex, a)
    hex = hex or "-"
    local key = a and (hex .. "/" .. a) or hex
    local c = lin_cache[key]
    if c then return {R = c.R, G = c.G, B = c.B, A = c.A} end
    if hex == "-" or #hex < 6 then
        c = {R = 0.0, G = 0.0, B = 0.0, A = 0.0}
    else
        local function ch(i)
            local v = (tonumber(hex:sub(i, i + 1), 16) or 0) / 255
            return v <= 0.04045 and v / 12.92 or ((v + 0.055) / 1.055) ^ 2.4
        end
        local alpha = #hex >= 8 and (tonumber(hex:sub(7, 8), 16) or 255) / 255 or 1.0
        c = {R = ch(1), G = ch(3), B = ch(5), A = alpha * (a or 1.0)}
    end
    lin_cache[key] = c
    return {R = c.R, G = c.G, B = c.B, A = c.A}
end

--- a mix of two linear colours (k 0..1)
function K.mix(a, b, k)
    return {R = a.R + (b.R - a.R) * k, G = a.G + (b.G - a.G) * k, B = a.B + (b.B - a.B) * k, A = a.A + (b.A - a.A) * k}
end

function K.slate(c) return {SpecifiedColor = c, ColorUseRule = 0} end

-- ---------------------------------------------------------------------- easing
function K.clamp(x, a, b) return x < a and a or (x > b and b or x) end
function K.out3(x) x = K.clamp(x, 0, 1) return 1 - (1 - x) ^ 3 end
function K.inout(x) x = K.clamp(x, 0, 1) return x < 0.5 and 4 * x ^ 3 or 1 - (-2 * x + 2) ^ 3 / 2 end
--- moves v towards target, a share of the way each second (frame-rate independent)
function K.approach(v, target, rate, dt)
    return target + (v - target) * math.exp(-rate * dt)
end

-- ---------------------------------------------------------------------- the widgets
local classes = {}
local function class(path)
    local c = classes[path]
    if not (c and c:IsValid()) then
        c = StaticFindObject(path)
        classes[path] = c
    end
    return c
end

function K.new(kind, outer)
    local path = kind:find("/") and kind or ("/Script/UMG." .. kind)
    local o = StaticConstructObject(class(path), outer)
    if not (o and o:IsValid()) then error("can't make " .. path) end
    return o
end

--- A UserWidget with a canvas, in the viewport (z-order), made from nothing: -> {w, tree, canvas}
function K.root(z)
    local gi = UEHelpers.GetGameInstance()
    if not (gi and gi:IsValid()) then return nil end
    local w = K.new("UserWidget", gi)
    local tree = K.new("WidgetTree", w)
    w.WidgetTree = tree
    local canvas = K.new("CanvasPanel", tree)
    tree.RootWidget = canvas
    w:AddToViewport(z or 50)
    w:SetVisibility(K.NOT_HIT)
    return {w = w, tree = tree, canvas = canvas}
end

function K.pad(l, t, r, b)
    return {Left = l + 0.0, Top = (t or l) + 0.0, Right = (r or l) + 0.0, Bottom = (b or t or l) + 0.0}
end

local game_font = nil
local function font_object()
    if game_font == nil or (game_font and not game_font:IsValid()) then
        local ok, f = pcall(StaticFindObject, K.FONT)
        game_font = ok and f and f:IsValid() and f or false
    end
    return game_font
end

--- A text: {size, face (K.FACES key), colour hex, spacing (1/1000 em), shadow (true: a soft dark one), wrap, justify
--- (0 left, 1 centre, 2 right)}
function K.text(tree, o)
    local tb = K.new("TextBlock", tree)
    K.font(tb, o.size or 16, o.face or "semi", o.spacing or 0)
    if o.colour then tb:SetColorAndOpacity(K.slate(K.lin(o.colour))) end
    if o.shadow ~= false then
        tb:SetShadowOffset({X = 1.0, Y = 1.0})
        tb:SetShadowColorAndOpacity(K.lin("000000", 0.55))
    end
    if o.wrap then tb:SetAutoWrapText(true) end
    if o.justify then tb:SetJustification(o.justify) end
    if o.text then tb:SetText(FText(o.text)) end
    return tb
end

function K.font(tb, size, face, spacing)
    local fi = tb.Font
    local f = font_object()
    if f then fi.FontObject = f end
    fi.Size = size
    fi.TypefaceFontName = FName(K.FACES[face] or face or "SemiBold")
    fi.LetterSpacing = spacing or 0
    tb:SetFont(fi)
end

--- A panel (Border): {fill hex, alpha, radius, outline hex, outline width, pad {l,t,r,b}}
function K.panel(tree, o)
    local b = K.new("Border", tree)
    K.brush(b, o)
    if o.pad then b:SetPadding(K.pad(table.unpack(o.pad))) else b:SetPadding(K.pad(0)) end
    return b
end

--- A panel's look again: rounded, its fill (BrushColor) and outline
function K.brush(b, o)
    local br = b.Background
    br.DrawAs = (o.radius or 0) > 0 and 4 or 1          -- RoundedBox, else Box (a plain fill)
    if (o.radius or 0) > 0 or o.outline then
        br.DrawAs = 4
        local r = (o.radius or 0) + 0.0
        br.OutlineSettings.CornerRadii = {X = r, Y = r, Z = r, W = r}
        br.OutlineSettings.RoundingType = 0
        br.OutlineSettings.Width = o.outline and (o.outline_w or 1.0) or 0.0
        br.OutlineSettings.Color = K.slate(K.lin(o.outline or "-"))
    end
    b:SetBrush(br)
    b:SetBrushColor(K.lin(o.fill or "-", o.alpha))
end

--- An outline's colour and width alone (a glow pulsing): costs a SetBrush, so only while it moves
function K.outline(b, colour, width)
    local br = b.Background
    br.OutlineSettings.Color = K.slate(colour)
    br.OutlineSettings.Width = width
    b:SetBrush(br)
end

-- (which kind each box is: UE4SS answers any name on an object, a missing function too, so it can't be asked)
local vertical = setmetatable({}, {__mode = "k"})
function K.vbox(tree)
    local b = K.new("VerticalBox", tree)
    vertical[b] = true
    return b
end
function K.hbox(tree) return K.new("HorizontalBox", tree) end

--- child into a vertical / horizontal box: {pad {l,t,r,b}, fill (true: takes what's left), h (0 fill, 1 left, 2 centre,
--- 3 right), v (0 fill, 1 top, 2 centre, 3 bottom)}
function K.add(box, child, o)
    o = o or {}
    local s = vertical[box] and box:AddChildToVerticalBox(child) or box:AddChildToHorizontalBox(child)
    if o.pad then s:SetPadding(K.pad(table.unpack(o.pad))) end
    if o.fill then s:SetSize({SizeRule = 1, Value = 1.0}) end
    if o.h then s:SetHorizontalAlignment(o.h) end
    if o.v then s:SetVerticalAlignment(o.v) end
    return s
end

function K.size(tree, child, w, h)
    local sb = K.new("SizeBox", tree)
    if w then sb:SetWidthOverride(w + 0.0) end
    if h then sb:SetHeightOverride(h + 0.0) end
    if child then sb:SetContent(child) end
    return sb
end

--- A bar: its track (a panel) and its fill (a panel in a size box whose width is set) -> {track, fill, sb, w}
function K.bar(tree, w, h, track, fill)
    local t = K.panel(tree, {fill = track or "FFFFFF", alpha = track and nil or 0.12, radius = h / 2})
    local row = K.hbox(tree)
    t:SetContent(row)
    local f = K.panel(tree, {fill = fill or "FFFFFF", radius = h / 2})
    local sb = K.size(tree, f, 0, h)
    K.add(row, sb, {h = 1})
    local outer = K.size(tree, t, w, h)
    -- its fill drawn inside it only (ClipToBounds): the waiting sweep moves a piece across and past both ends, and it
    -- showed past the note's edge (19 Nov 2026)
    for _, x in ipairs({t, outer}) do pcall(function() x:SetClipping(1) end) end
    return {track = t, fill = f, sb = sb, w = w, h = h, frac = -1, outer = outer}
end

function K.bar_set(bar, frac, colour)
    frac = K.clamp(frac or 0, 0, 1)
    if math.abs(frac - bar.frac) > 0.0005 then
        bar.frac = frac
        bar.sb:SetWidthOverride(math.max(0.0, bar.w * frac))
        bar.fill:SetVisibility(frac > 0.002 and K.NOT_HIT or K.COLLAPSED)
    end
    if colour and colour ~= bar.colour then
        bar.colour = colour
        bar.fill:SetBrushColor(K.lin(colour))
    end
end

-- ---------------------------------------------------------------------- pictures (PNG / JPG files)
-- (A Lua reference doesn't keep a texture alive: once nothing of the game's holds it, the engine's garbage collection
-- frees it, at the latest when a level loads, and another object can take its place, which IsValid() still calls
-- valid. Using such a one crashed the game on the way back to the menu from a stage, 20 Nov 2026. So a texture is used
-- again only while it is still the same object: its full name as when it was made.)
local textures = {}             -- path -> {tex, name}
local KRL = nil

-- The game's own pictures (0.2, the user, 21 Nov 2026: "can we use pictures which are already in-game?"): a source
-- "ue:stage:<stage id>" is the game's picture of that stage (its track variant's VariantImage, 1720 x 448: what its
-- stage picker shows; a community stage's too), "ue:loc:<location row>" its location's (DT_TracksLocationsBackgrounds),
-- "ue:/Game/..." a texture by path. Its asset path found once in the game's tables (probed 21 Nov 2026).
local game_paths = nil
local function game_tables()
    if game_paths then return game_paths end
    local KSL = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local function soft(v)
        local s = nil
        pcall(function() s = KSL:Conv_SoftObjectReferenceToString(v):ToString() end)
        return s
    end
    local function rows(path, fn)
        local dt = StaticFindObject(path)
        if not (dt and dt:IsValid()) then return end
        pcall(function()
            dt:ForEachRow(function(name, data)
                local nm = type(name) == "string" and name or nil
                if not nm then pcall(function() nm = name:ToString() end) end
                if nm then pcall(fn, nm, data) end
            end)
        end)
    end
    local tex, out = {}, {stage = {}, loc = {}}
    rows("/Game/Data/Database/Main/TrackSelection/DT_TracksTextures.DT_TracksTextures",
         function(nm, d) tex[nm] = soft(d.Value) end)
    rows("/Game/Data/Database/Main/TrackSelection/DT_TracksVariants.DT_TracksVariants",
         function(nm, d) out.stage[nm:lower()] = tex[d.VariantImage.Row:ToString()] end)
    rows("/Game/Data/Database/Main/TrackSelection/DT_TracksLocationsBackgrounds.DT_TracksLocationsBackgrounds",
         function(nm, d) out.loc[nm:lower()] = soft(d.Value) end)
    out.livery = {}                                       -- (a livery's preview, as the garage shows it: "ue:livery:")
    rows("/Game/Data/Database/Main/Customization/DT_Liveries.DT_Liveries",
         function(nm, d) out.livery[nm:lower()] = soft(d.Icon) end)
    -- a car's picture, as CHANGE CAR shows it ("ue:car:<car id>": DT_Cars' CarTexture, a row of DT_CarsTextures)
    out.car = {}
    local by = {}
    for _, dt in ipairs(FindAllOf("DataTable") or {}) do
        local ok, nm = pcall(function() return dt:GetFName():ToString() end)
        if ok and (nm == "DT_Cars" or nm == "DT_CarsTextures") then by[nm] = dt:GetFullName():match("^%S+%s+(.+)$") end
    end
    local ctex = {}
    if by.DT_CarsTextures then rows(by.DT_CarsTextures, function(nm, d) ctex[nm] = soft(d.Value) end) end
    if by.DT_Cars then rows(by.DT_Cars, function(nm, d) out.car[nm:lower()] = ctex[d.CarTexture.Row:ToString()] end) end
    local nc = 0
    for _ in pairs(out.car) do nc = nc + 1 end
    print(string.format("[hudkit] game pictures: %s stages, %d cars (%s / %s)\n", next(out.stage) and "some" or "no",
                        nc, tostring(by.DT_Cars), tostring(by.DT_CarsTextures)))
    if next(out.stage) and nc > 0 then game_paths = out end   -- (the tables not there yet: looked at again later)
    return out
end

--- "ue:..." -> the game asset's path, or nil
function K.game_path(src)
    local key = src:sub(4)
    if key:sub(1, 1) == "/" then return key end
    local kind, id = key:match("^(%a+):(.+)$")
    if not kind then return nil end
    local t = game_tables()[kind]
    return t and t[id:lower()] or nil
end

--- a picture file (or a game picture: "ue:...") -> a texture (loaded once while it lives), or nil
function K.texture(path)
    if not path or path == "" or path == "-" then return nil end
    local c = textures[path]
    if c then
        local ok, same = pcall(function() return c.tex:IsValid() and c.tex:GetFullName() == c.name end)
        if ok and same then return c.tex end
        textures[path] = nil
    end
    if path:sub(1, 3) == "ue:" then
        local p = K.game_path(path)
        local ok, tex = false, nil
        if p then ok, tex = pcall(LoadAsset, p) end
        if ok and tex and tex:IsValid() then
            textures[path] = {tex = tex, name = tex:GetFullName()}
            return tex
        end
        return nil
    end
    if not (KRL and KRL:IsValid()) then KRL = StaticFindObject("/Script/Engine.Default__KismetRenderingLibrary") end
    local ok, tex = pcall(function() return KRL:ImportFileAsTexture2D(UEHelpers.GetWorld(), path) end)
    if ok and tex and tex:IsValid() then
        textures[path] = {tex = tex, name = tex:GetFullName()}
        return tex
    end
    return nil
end

--- every texture forgotten (a new level: the old ones are the engine's to free)
function K.forget_textures()
    textures = {}
end

--- a picture w x h (fitted in it, its shape kept) -> {img, box (the size box to add), w, h}
function K.image(tree, w, h)
    local img = K.new("Image", tree)
    local sb = K.size(tree, nil, w, h)
    local inner = K.new("ScaleBox", tree)          -- (fits the picture in the box, its shape kept)
    sb:SetContent(inner)
    inner:SetContent(img)
    return {img = img, box = sb, w = w, h = h}
end

--- a picture on an image (only when it changed) -> whether it has one
function K.picture(pic, state, path)
    if state.path == path then
        if not path then return state.tex ~= nil end
        local ok, same = pcall(function() return state.tex and state.tex:IsValid() and state.tex:GetFullName() == state.name end)
        if ok and same then return true end            -- (still the same texture: see K.texture)
    end
    state.path = path
    local tex = K.texture(path)
    state.tex = tex
    state.name = tex and tex:GetFullName() or nil
    if tex then
        pic.img:SetBrushFromTexture(tex, true)      -- (its own size: the scale box fits it)
        pic.box:SetVisibility(K.NOT_HIT)
    else
        pic.box:SetVisibility(K.COLLAPSED)
    end
    return tex ~= nil
end

-- ---------------------------------------------------------------------- what's set, only when it changed
--- set(cache, key, value, fn): fn(value) only when value differs from the last one set under key
function K.set(cache, key, value, fn)
    if cache[key] ~= value then
        cache[key] = value
        fn(value)
    end
end

function K.show(cache, key, w, on)
    K.set(cache, key, on and true or false, function(v) w:SetVisibility(v and K.NOT_HIT or K.COLLAPSED) end)
end

function K.say(cache, key, tb, s)
    K.set(cache, key, s or "", function(v) tb:SetText(FText(v)) end)
end

function K.tint(cache, key, tb, hex)
    K.set(cache, key, hex or "FFFFFF", function(v) tb:SetColorAndOpacity(K.slate(K.lin(v))) end)
end

function K.fill(cache, key, b, hex, a)
    K.set(cache, key, (hex or "-") .. "/" .. tostring(a), function() b:SetBrushColor(K.lin(hex or "-", a)) end)
end

-- ---------------------------------------------------------------------- times
--- ms -> '1:23.45' (cs: hundredths), '1:23.456' (ms), '1:02:03.45' past an hour; negative: '-'
function K.clock(ms, digits)
    if not ms then return "" end
    local neg = ms < 0
    ms = math.abs(ms)
    digits = digits or 2
    local unit = digits == 3 and 1 or (digits == 1 and 100 or 10)
    local whole = math.floor(ms / unit)
    local frac = whole % (1000 // unit)
    local s = math.floor(ms / 1000)
    local h, m, sec = s // 3600, (s // 60) % 60, s % 60
    local f = digits > 0 and string.format(".%0" .. digits .. "d", frac) or ""
    local out = h > 0 and string.format("%d:%02d:%02d%s", h, m, sec, f) or string.format("%d:%02d%s", m, sec, f)
    return (neg and "-" or "") .. out
end

--- seconds left -> '1:20' ('0:07'), past an hour '1:02:03'
function K.left(ms)
    local s = math.max(0, math.ceil((ms or 0) / 1000))
    local h, m, sec = s // 3600, (s // 60) % 60, s % 60
    return h > 0 and string.format("%d:%02d:%02d", h, m, sec) or string.format("%d:%02d", m, sec)
end

return K
