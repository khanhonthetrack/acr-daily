-- ACR Daily ghost cars, in the game (a UE4SS Lua mod).
--
-- The ACR Daily app writes where the other drivers' cars are (live) to %APPDATA%\ACR Daily\ingame-ghosts.txt about
-- 60 times a second; this mod puts a real car there for each: the driver's own car model (its physics off, nothing
-- to hit), moved every frame, its wheels set where that car's wheels sit at rest (wheels.lua). It also writes the
-- game's camera to %APPDATA%\ACR Daily\ingame-camera.txt, so the app can put the names above the cars exactly.
--
-- ingame-ghosts.txt:   ACRDG 2 <seq> [<when>]
--                      <id> <class> <X> <Y> <Z> <Pitch> <Yaw> <Roll> [<VX> <VY> <VZ> <VPitch> <VYaw> <VRoll> [<seq>]]
--                      end [<seq>]
--   the game's units: cm, degrees (one line per car); <class>: the driver's own car ('/Game/Data/Vehicles/.../
--   BC_X.BC_X_C'), or '-' (unknown: your car's). <when>: the app's clock (s) at that pose; V..: how it moves, per
--   second. With them the car is moved on every frame between the app's updates, from where the app said it was at
--   <when> (the app's clock mapped onto this one), and a small difference when the next update comes is eased out
--   instead of jumped: smooth at any frame rate. Without them (an older app): placed where it says, when read.
--   The update's <seq> again at the end of each line and after "end": the app overwrites the file in place, so a read
--   in the middle of a write (lines of two updates) is told and skipped.
--                      warm <class> <how many> <seq>   (the models of the drivers on the stage: made ahead of time)
--                      name <id> <seq> <shown> <colour> <the name>   (the driver's name, drawn over their car by the
--                      game: hud.lua; shown 0: out of sight behind trees or a hill, as the app works it out)
-- ingame-camera.txt:   CAM <seq> <X> <Y> <Z> <Pitch> <Yaw> <Roll> <horizontal fov> <seq> M <mode> <seq> [N 1 <seq>]
--                      [S ... <seq>] [A ... <seq>] [V ... <seq>] [H <id>... <seq>]
--                      (padded to 160 characters; M: the game's mode, race_mode; N: the game draws the names, hud.lua,
--                      the app's window then doesn't; S / A / V: the race's settings and the player's driving aids,
--                      read_settings / read_aids; H: the cars hidden while in yours, near_hide: no name over them)
--
-- Both files are kept open for the game's whole life, and overwritten in place: opening a file that was just changed
-- costs the game several ms each time (Windows' virus check: the game thread went from 5 to 10 ms a frame with the
-- app's 60 updates a second, measured 2026-11-10); read and written through the open files, about 0.1 ms.
local UEHelpers = require("UEHelpers")

local TAG = "[ACRDailyGhosts] "
local DIR = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\"
local GHOSTS_FILE = DIR .. "ingame-ghosts.txt"
local CAMERA_FILE = DIR .. "ingame-camera.txt"
local TRACE_FLAG = DIR .. "ghost-trace.on"   -- (for testing: while it exists, each frame's cars go to ghost-trace.txt)
local STALE_S = 1.5              -- the app's file not changing for this long: ghosts hidden
local GONE_S = 0.5               -- a ghost missing from the file this long: removed
local AHEAD_S = 0.25             -- carried on at its speed at most this long past the app's last word
local EASE_S = 0.06              -- a difference between where a car was carried and the app's next word: eased out
local SNAP_CM = 300              -- a bigger one (a reset onto the road): jumped

local cars = {}                  -- id -> {actor, leader, cls, base, vel, t, err, err_t, seen_t}
local ghost_names = {}           -- id -> {text, shown, colour}: the drivers' names, from the app's file
local names_by_game = false      -- hud.lua loaded: it draws the names over the cars (camera line: N)
local NAME_UP = 170              -- a name this far over its car's root (cm)
local trace = nil                -- (testing: ghost-trace.txt open while ghost-trace.on exists)
local last_seq, last_new_t = nil, nil
local frame = 0
local cam_seq = 0
local spawned_this_frame = false

local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end
log("loaded")

-- This mod's clock (seconds, wall time since the game started: the C library's clock() on Windows), and the app's
-- clock mapped onto it: the app writes a file at most a frame or so before it is read here, so the smallest
-- (read here - written there) seen is the gap between the two clocks (it creeps up 1 ms a second, in case).
local now = os.clock
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

local function pawn()
    local pc = UEHelpers.GetPlayerController()
    if pc and pc:IsValid() then
        local p = pc.Pawn
        if p and p:IsValid() and p.SetInputEnabled then return p, pc end
        return nil, pc
    end
end

local ghosts_f, ghosts_opened = nil, nil      -- (the app's file, kept open)

local function ghosts_text(t)
    if not ghosts_f then
        if frame % 30 ~= 1 then return nil end      -- (looked for twice a second until the app has made it)
        ghosts_f = io.open(GHOSTS_FILE, "r")
        if not ghosts_f then return nil end
        ghosts_opened = t
    end
    if not ghosts_f:seek("set", 0) then
        ghosts_f:close()
        ghosts_f = nil
        return nil
    end
    return ghosts_f:read("a")
end

local function reopen_ghosts()
    -- (nothing new for a while: the file may have been made again, an older app replaces it each time)
    if ghosts_f then ghosts_f:close() end
    ghosts_f = nil
end

local function read_ghosts(t)
    -- -> seq, the app's clock at it (or nil), {id -> {X, Y, Z, Pitch, Yaw, Roll, cls = , v = {per second} or nil}};
    -- nil when there is no whole update (being written: the next frame)
    local text = ghosts_text(t)
    if not text then return nil end
    local seq, when = text:match("^ACRDG 2 (%d+) ?([%d%.]*)")
    if not seq then return nil end
    local stop, tail = text:match("()\nend ?(%d*)")
    if not stop or (tail ~= "" and tail ~= seq) then return nil end     -- (no end yet, or another update's)
    local out, warm_now, names_now = {}, {}, {}
    for line in text:sub(1, stop):gmatch("\n([^\n]+)") do               -- (up to the end: never what lies after it)
        local w = {}
        for x in line:gmatch("%S+") do w[#w + 1] = x end
        if w[1] == "name" then                                           -- name <id> <seq> <shown> <colour> <the name>
            if w[3] ~= seq then return nil end
            local words = line:match("^name %S+ %S+ %S+ %S+ (.+)$")
            if words then names_now[w[2]] = {text = words, shown = w[4] == "1", colour = w[5]} end
        elseif #w >= 15 and w[15] ~= seq then return nil                 -- (a line of another update)
        elseif w[1] == "warm" and #w >= 4 then                           -- warm <class> <how many> <seq>
            if w[4] ~= seq then return nil end
            warm_now[w[2]] = tonumber(w[3]) or 0
        elseif #w >= 8 then
            local g = {cls = w[2]}
            for i = 1, 6 do g[i] = tonumber(w[i + 2]) end
            if #w >= 14 then
                g.v = {}
                for i = 1, 6 do g.v[i] = tonumber(w[i + 8]) or 0 end
            end
            if g[1] and g[2] and g[3] and g[4] and g[5] and g[6] then out[w[1]] = g end
        end
    end
    return seq, tonumber(when), out, warm_now, names_now
end

local function angle(a)            -- degrees, to -180..180
    return (a + 180) % 360 - 180
end

local function carried_raw(c, t)
    -- where car c is at this mod's clock t: the app's last pose, moved on at its speed (at most AHEAD_S)
    local b, v = c.base, c.vel
    local dt = math.max(0, math.min(AHEAD_S, t - c.t))
    local p = {}
    for i = 1, 6 do p[i] = b[i] + (v and v[i] or 0) * dt end
    return p
end

local function carried(c, t)
    -- ... plus what is left of the difference being eased out
    local p = carried_raw(c, t)
    if c.err then
        local k = math.exp(-(t - c.err_t) / EASE_S)
        if k < 0.005 then
            c.err = nil
        else
            for i = 1, 6 do p[i] = p[i] + c.err[i] * k end
        end
    end
    return p
end

local function took(c, g, t_pose, t)
    -- the app's new word on car c (pose g at this mod's clock t_pose), seen at t: from it on, the difference from
    -- where the car was being carried eased out (a reset: jumped)
    local before = c.base and carried(c, t)
    c.base, c.vel, c.t = g, g.v, t_pose
    if before then
        local after = carried_raw(c, t)
        local e = {before[1] - after[1], before[2] - after[2], before[3] - after[3],
                   angle(before[4] - after[4]), angle(before[5] - after[5]), angle(before[6] - after[6])}
        if math.abs(e[1]) + math.abs(e[2]) + math.abs(e[3]) < SNAP_CM then
            c.err, c.err_t = e, t
        else
            c.err = nil
        end
    end
end

local classes = {}               -- class path -> UClass (or false: could not load it)

local function class_for(path, me)
    if path == "-" then return me:GetClass() end
    local c = classes[path]
    if c == nil then
        c = StaticFindObject(path)
        if not (c and c:IsValid()) then
            local ok, got = pcall(LoadAsset, path)
            c = StaticFindObject(path)
            if not (c and c:IsValid()) and ok and got and got.IsValid and got:IsValid() then c = got end
        end
        if not (c and c:IsValid()) then
            log("can't load %s: your car instead", path)
            c = false
        end
        classes[path] = c
    end
    return c or me:GetClass()
end

local function skinned(actor)
    local out = {}
    local cls = StaticFindObject("/Script/Engine.SkinnedMeshComponent")
    local comps = actor:K2_GetComponentsByClass(cls)
    local function add(c)
        if c and c.IsValid and c:IsValid() then out[c:GetFName():ToString()] = c end
    end
    if type(comps) == "table" then
        for _, c in pairs(comps) do add(c.get and c:get() or c) end
    else
        comps:ForEach(function(_, e) add(e:get()) end)
    end
    return out
end

-- The body keeps its own shape: never your car's pose (another car's bones opened its doors; and the game hides parts
-- of your car in some views, the bumper camera its rear panels, which a copy of your pose hid on the ghost too). The
-- crew: the same car as yours seats it like yours; another car's is hidden (seated like yours, their heads came
-- through a low roof: Stratos, Alpine, Fiat 124). The suspension never follows yours either (your car's wheels would
-- stick out of a narrower car): place_wheels() sets it.
local function crew(name)   -- Driver, CoDriver, HelmetCoDriver, SuitCodriver, ..., Pacenotes (the co-driver's book)
    return name:find("[Dd]river") ~= nil or name:find("Pacenote") ~= nil
end

local function follow_pose(ghost, me)
    local same = ghost:GetClass():GetFullName() == me:GetClass():GetFullName()
    local mine = skinned(me)
    for name, c in pairs(skinned(ghost)) do
        if crew(name) then
            if same and mine[name] then
                c:SetLeaderPoseComponent(mine[name], true, false)
            else
                c:SetVisibility(false, true)
            end
        end
    end
end

-- The wheels. A car without physics never moves its wheels itself: the game's suspension animation keeps the four
-- wheel positions (world, from when the car appeared) until something sets them, so a moving ghost left its wheels
-- behind. Each frame they are set from where the car is, at the car's resting wheel positions (wheels.lua: measured
-- in the game with each car as your own); a car not measured keeps where its model has them.
local BONES = {"EXT_FL_Tire", "EXT_FR_Tire", "EXT_RL_Tire", "EXT_RR_Tire"}   -- (the animation's wheel order)
local ok_rest, REST = pcall(require, "wheels")
if not ok_rest or type(REST) ~= "table" then
    log("no wheels.lua (%s): wheels where the models have them", tostring(REST))
    REST = {}
end

local function wheels_of(a)
    local r = REST[a:GetClass():GetFName():ToString()]
    if r then return r end
    local sm, out, size = a.SuspensionsMesh, {}, 0
    for i, b in ipairs(BONES) do
        local t = sm:GetSocketTransform(FName(b), 2)            -- (the car's own space, cm)
        out[i] = {t.Translation.X, t.Translation.Y, t.Translation.Z}
        size = size + math.abs(t.Translation.X) + math.abs(t.Translation.Y)
    end
    if size < 100 then return nil end                          -- (no pose yet: left as the game has them)
    return out
end

local function rotation(p, y, r)
    -- Unreal's rotator -> its axes (X, Y, Z in the world) and quaternion
    local sp, cp = math.sin(math.rad(p)), math.cos(math.rad(p))
    local sy, cy = math.sin(math.rad(y)), math.cos(math.rad(y))
    local sr, cr = math.sin(math.rad(r)), math.cos(math.rad(r))
    local ax = {cp * cy, cp * sy, sp}
    local ay = {sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp}
    local az = {-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp}
    local hsp, hcp = math.sin(math.rad(p) / 2), math.cos(math.rad(p) / 2)
    local hsy, hcy = math.sin(math.rad(y) / 2), math.cos(math.rad(y) / 2)
    local hsr, hcr = math.sin(math.rad(r) / 2), math.cos(math.rad(r) / 2)
    local q = {X = hcr * hsp * hsy - hsr * hcp * hcy, Y = -hcr * hsp * hcy - hsr * hcp * hsy,
               Z = hcr * hcp * hsy - hsr * hsp * hcy, W = hcr * hcp * hcy + hsr * hsp * hsy}
    return ax, ay, az, q
end

local function place_wheels(c, g)
    if not c.wheels then return end
    local ai = c.anim
    if not (ai and ai:IsValid()) then
        ai = c.actor.SuspensionsMesh:GetAnimInstance()
        if not (ai and ai:IsValid()) then return end
        c.anim = ai
    end
    local ax, ay, az, q = rotation(g[4], g[5], g[6])
    local wt, st = ai.WheelTransforms, ai.SuspensionTransforms
    for i = 1, 4 do
        local l = c.wheels[i]
        local p = {X = g[1] + ax[1] * l[1] + ay[1] * l[2] + az[1] * l[3],
                   Y = g[2] + ax[2] * l[1] + ay[2] * l[2] + az[2] * l[3],
                   Z = g[3] + ax[3] * l[1] + ay[3] * l[2] + az[3] * l[3]}
        local w, s = wt[i], st[i]
        w.Translation, w.Rotation = p, q
        s.Translation, s.Rotation = p, q
    end
end

local function transform(g)
    local half = math.rad(g[5]) / 2
    return {Rotation = {X = 0.0, Y = 0.0, Z = math.sin(half), W = math.cos(half)},
            Translation = {X = g[1], Y = g[2], Z = g[3]}, Scale3D = {X = 1.0, Y = 1.0, Z = 1.0}}
end

-- The ghost's dash screens (GaugeComponent: the gear screen on the dash) are stopped: while a ghost's one ticked,
-- YOUR car's went black (the same car as yours, the Skoda's gear screen, seen in the game 2026-11-10; it came back as
-- soon as the ghost's stopped ticking). Checked again now and then (quiet_gauges), in case the game starts it again.
local function gauges(a)
    local out = {}
    local comps = a:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.ActorComponent"))
    local function add(c)
        if c and c.IsValid and c:IsValid() and c:GetClass():GetFName():ToString():find("Gauge") then
            out[#out + 1] = c
        end
    end
    if type(comps) == "table" then
        for _, c in pairs(comps) do add(c.get and c:get() or c) end
    else
        comps:ForEach(function(_, e) add(e:get()) end)
    end
    return out
end

local function quiet_gauges(c)
    for _, g in ipairs(c.gauges or {}) do
        if g:IsValid() and g:IsComponentTickEnabled() then g:SetComponentTickEnabled(false) end
    end
end

-- A ghost is a picture of a car: all that makes a car a car is stopped on it (its own update, its sound, dust and
-- smoke, damage, crew animations, the dash screens, and the update of each of its ~40 models); only its lights (night
-- stages) and its suspension (it places the wheels) go on. Its crew and its inside are drawn only when it is near
-- (NEAR_M, hidden again past FAR_M). Measured with 10 ghosts moving round in front of you (2026-11-10): the game
-- thread's time a frame went from 23 ms (5 without them) to about 9, the draw calls from 8600 to about 5000.
local KEEP_TICK = {SuspensionsMesh = true}
local KEEP_TICK_CLASS = {CarLightsComponent = true}
local NEAR_M, FAR_M = 40, 50

local function trim(a)
    a:SetActorTickEnabled(false)
    local scene = StaticFindObject("/Script/Engine.SceneComponent")
    local crew_parts, inside = {}, {}
    local comps = a:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.ActorComponent"))
    local list = {}
    if type(comps) == "table" then
        for _, c in pairs(comps) do list[#list + 1] = c.get and c:get() or c end
    else
        comps:ForEach(function(_, e) list[#list + 1] = e:get() end)
    end
    for _, c in ipairs(list) do
        if c and c.IsValid and c:IsValid() then
            local cls, name = c:GetClass():GetFName():ToString(), c:GetFName():ToString()
            if not KEEP_TICK[name] and not KEEP_TICK_CLASS[cls] and c:IsComponentTickEnabled() then
                c:SetComponentTickEnabled(false)
                if cls == "NiagaraComponent" or cls == "CarAudioComponent" then c:Deactivate() end
            end
            if c:IsA(scene) then
                if crew(name) then
                    crew_parts[#crew_parts + 1] = c
                elseif name:find("^Internal") then
                    inside[#inside + 1] = c
                end
            end
        end
    end
    return crew_parts, inside
end

local function detail(c, me_loc)
    -- the crew (if it is shown at all: the same car as yours) and the inside, near only
    local p = c.shown
    local d = math.sqrt((p[1] - me_loc.X) ^ 2 + (p[2] - me_loc.Y) ^ 2 + (p[3] - me_loc.Z) ^ 2) / 100
    local want = d < NEAR_M or (c.detail and d < FAR_M)
    if want == c.detail then return end
    c.detail = want
    for _, part in ipairs(c.inside) do
        if part:IsValid() then part:SetVisibility(want, false) end
    end
    if c.crew_shown then
        for _, part in ipairs(c.crew) do
            if part:IsValid() then part:SetVisibility(want, true) end
        end
    end
end

-- A ghost is hidden only while it is IN your car (its name stays: the app draws it): one driving through you filled the
-- screen. Close racing stays: a car side by side with you, or a few metres ahead or behind, is shown. "In your car":
-- its middle within OVERLAP_FWD of yours lengthways and OVERLAP_SIDE sideways (cars are 4.1-4.3 m long, 1.8 m wide:
-- wheels.lua), in your car's own axes (x = left, y = forward). In a chase view also within CAM_M of the camera (behind
-- your car: one passing through it). Shown again only a little further out (no blinking at the edge).
local OVERLAP_FWD, OVERLAP_SIDE, OVERLAP_UP = 400, 170, 300      -- cm
local CAM_M = 250
local CAM_OUT = 300                                              -- cm: the camera further from your car's middle: a chase view
local OUT = 60                                                   -- cm more to be shown again

local function near_hide(c, cam, me)
    local p = c.shown
    local was = c.near == true
    local m = was and OUT or 0
    local dx, dy, dz = p[1] - me.X, p[2] - me.Y, p[3] - me.Z
    local fwd = math.abs(-dx * me.sy + dy * me.cy)
    local side = math.abs(dx * me.cy + dy * me.sy)
    local inside = fwd < OVERLAP_FWD + m and side < OVERLAP_SIDE + m and math.abs(dz) < OVERLAP_UP + m
    local at_cam = me.cam_out and ((p[1] - cam.X) ^ 2 + (p[2] - cam.Y) ^ 2 + (p[3] - cam.Z) ^ 2) < (CAM_M + m) ^ 2
    local want = inside or at_cam == true                        -- (always true or false, never nil)
    if want == was then return end
    c.near = want
    c.actor:SetActorHiddenInGame(want)
end

local function spawn(me, g)
    local gs = UEHelpers.GetGameplayStatics()
    local t = transform(g)
    local a = gs:BeginDeferredActorSpawnFromClass(UEHelpers.GetWorld(), class_for(g.cls, me), t, 1, nil, 0)
    if not a or not a:IsValid() then return nil end
    a.bInitializePhysics = false                      -- a picture of a car: no physics, nothing to drive
    gs:FinishSpawningActor(a, t, 0)
    a:SetActorEnableCollision(false)
    -- (never SetInputEnabled(false) on it: the cars share one input set-up, and that switched off YOUR car's
    -- throttle and steering, for good, the first time a ghost came: seen in the game 2026-11-05)
    follow_pose(a, me)
    return a
end

-- Kept cars. Making a ghost costs the game about 45 ms (a hitch of a frame and a half at 30 frames a second, measured
-- 2026-11-11); hiding one and showing it again, under 1 ms. So a ghost that goes (out of range, or the app stops
-- telling) is hidden and kept for the next car of its model (POOL_MAX at most, POOL_KEEP_S each); and while your car
-- stands still (waiting at the start), the cars the app says are on the stage ("warm" lines) are made ahead of time,
-- one every WARM_S, so that none is made while you drive. 30 drivers setting off past you, 2 s apart: 30 frames of
-- 66-75 ms before, 0 after (all made while waiting).
local POOL_MAX = 10
local POOL_KEEP_S = 120
local WARM_S = 0.5
local pool = {}                  -- class path -> {car, ...}: hidden, trimmed, ready
local pooled = 0
local pool_leader = nil          -- (whose crew they follow: your car; another car of yours: they go)
local warm, warm_t = {}, -1e9

local function make(me, g, me_at)
    local a = spawn(me, g)
    if not a then return nil end
    local c = {actor = a, leader = me_at, cls = g.cls, wheels = wheels_of(a), gauges = gauges(a), detail = true,
               crew_shown = a:GetClass():GetFullName() == me:GetClass():GetFullName()}
    c.crew, c.inside = trim(a)
    quiet_gauges(c)
    if trace then trace:write(string.format("# spawn %d %s\n", frame, g.cls)) end
    return c
end

local function destroy(c)
    if c.actor and c.actor:IsValid() then c.actor:K2_DestroyActor() end
end

local function park(c, t)
    if pooled >= POOL_MAX or not c.actor:IsValid() then
        destroy(c)
        return
    end
    c.actor:SetActorHiddenInGame(true)
    c.base, c.vel, c.err, c.shown, c.parked_t = nil, nil, nil, nil, t
    pool[c.cls] = pool[c.cls] or {}
    table.insert(pool[c.cls], c)
    pooled = pooled + 1
end

local function take(cls, me_at)
    local list = pool[cls]
    while list and #list > 0 do
        local c = table.remove(list)
        pooled = pooled - 1
        if c.actor:IsValid() and c.leader == me_at then
            c.actor:SetActorHiddenInGame(false)
            c.near = false                             -- (shown: near_hide hides it again if it comes back close)
            return c
        end
        destroy(c)
    end
    return nil
end

local function empty_pool(keep_s, t)
    -- the kept cars removed: all (keep_s nil), or those unused for longer than keep_s
    for _, list in pairs(pool) do
        for i = #list, 1, -1 do
            local c = list[i]
            if not keep_s or t - c.parked_t > keep_s or not c.actor:IsValid() then
                table.remove(list, i)
                pooled = pooled - 1
                destroy(c)
            end
        end
    end
end

local function remove(id, t, gone)
    -- a ghost goes: kept for the next of its model (gone: removed for good)
    local c = cars[id]
    cars[id] = nil
    if not c then return end
    if gone then destroy(c) else park(c, t) end
end

local function warm_up(me, me_at, t)
    -- (while you stand still) one more car made ahead of time, of a model the app says may come and short of
    if spawned_this_frame or t - warm_t < WARM_S or pooled >= POOL_MAX then return end
    local ok, v = pcall(function() return me:GetVelocity() end)
    if not ok or not v or math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z) > 200 then return end
    for cls, want in pairs(warm) do
        local have = #(pool[cls] or {})
        for _, c in pairs(cars) do
            if c.cls == cls then have = have + 1 end
        end
        if have < want then
            local l, r = me:K2_GetActorLocation(), me:K2_GetActorRotation()
            local c = make(me, {l.X, l.Y, l.Z - 2000, 0, r.Yaw, 0, cls = cls}, me_at)   -- (made out of sight)
            spawned_this_frame, warm_t = true, t
            if c then park(c, t) end
            return
        end
    end
end

local cam_f = nil                              -- (the camera file, kept open)

-- The game's mode on the loaded stage: the race event the game made for it (its game state's RaceEventManagerComponent
-- .RaceEvent; checked in the game 2026-11-19): a Rally Weekend's (BC_RaceEventRally_C) has a
-- RaceEventRaceSettingsRallyWeekendComponent, a Single Rally Stage's is BC_RaceEventSingleEvent_C, Free Practice's
-- BC_RaceEventFreePractice_C, Time Attack's BC_RaceEventTimeAttack_C. -> 'weekend', 'single', 'practice', 'timeattack',
-- 'championship', 'other' (a race event, none of those), 'none' (no race event: the menus), 'unknown' (can't be told:
-- the game changed). The app counts a daily's or a time trial's run only in 'weekend' (app.py game_mode); the
-- game's save can't tell it before the finish (it writes the Rally Weekend once the stage is over).
local RW_SETTINGS = nil
local mode_now, mode_event, mode_frame = "none", nil, -1000

-- The race's settings on the loaded stage, as the game runs it (its race event's settings component: the fields of
-- RaceEventRaceSettingsComponent, probed in the game 2026-11-19, docs/hardcore-and-assists.md): manual respawn (0 off,
-- 1 full, 2 realistic), damage on (0 / 1), collisions, wear, mechanical failures (0 off, 1 light, 2 severe, 3
-- realistic), penalties (0 off, 1 light, 2 realistic), Hardcore (0 / 1), tyre damage (0 off, 1 light, 2 realistic, 3
-- severe) -> "rdcwfpht", one digit each, for the camera line (one word: a value can't be taken for the line's <seq>,
-- which ends each group); nil without a race event. The app checks them against the event's
-- rules on the start line (app.py settings_changed): a change in the game's menus is told before the run, not after.
-- (Only plain fields are read: reading every kind of field of the race event crashed the game in the probe.)
local settings_comp, settings_event, settings_now = nil, nil, nil
local function read_settings(ev)
    local at = ev:GetAddress()
    if settings_event ~= at or not (settings_comp and settings_comp:IsValid()) then
        settings_comp, settings_event = nil, at
        for _, o in ipairs(FindAllOf("RaceEventRaceSettingsComponent") or {}) do
            local ok, mine = pcall(function()
                local outer = o:GetOuter()
                return outer and outer:IsValid() and outer:GetAddress() == at
            end)
            if ok and mine then settings_comp = o end
        end
    end
    local s = settings_comp
    if not s then return nil end
    local o = s.RaceOptions
    local d = o.CarDamage
    local function b(x) return x and 1 or 0 end
    return string.format("%d%d%d%d%d%d%d%d", o.Respawn.ManualRespawn, b(d.bDamagesEnabled), d.Collisions, d.Wear,
        d.MechanicalFailures, s.RacePenaltyOptions.RacePenalty, b(s.HardCoreOptions.bHardCore),
        o.TyreManagement.TyresDamage)
end

-- The player's driving aids (probed 2026-11-19, docs/hardcore-and-assists.md): their race participant (the
-- BC_RaceParticipant_C whose ID is the player state's ParticipantId, LOCAL_PLAYER; in this level), its
-- RaceParticipantData.DrivingAids as the race applies them: gearbox (0 manual, 1 automatic), ABS, TC, starting handbrake
-- assist, clutch (0 manual, 1 automatic) -> "gatbc"; and the game's race viewmodel (the UI's own, UIViewmodelManager:
-- what the car's dash shows, aids switched in the car too): ABS, TC, gearbox, clutch -> "atgc". The app checks them
-- against an event without aids on the start line, and any change during a stage is a DNF (app.py _watch_run).
local aid_part, aid_event, aid_vm = nil, nil, nil
local function bit(x) return x and 1 or 0 end
local function read_aids(ev)
    local at = ev:GetAddress()
    if aid_event ~= at or not (aid_part and aid_part:IsValid()) then
        aid_part, aid_event = nil, at
        local want = UEHelpers.GetPlayerController().PlayerState.ParticipantId:ToString()
        local level = ev:GetOuter():GetAddress()
        for _, o in ipairs(FindAllOf("BC_RaceParticipant_C") or {}) do
            local ok, mine = pcall(function()
                return o.ID:ToString() == want and o:GetOuter():GetAddress() == level
            end)
            if ok and mine then aid_part = o.RaceParticipantData end
        end
    end
    if not (aid_vm and aid_vm:IsValid()) then
        aid_vm = nil
        for _, o in ipairs(FindAllOf("ViewmodelRace") or {}) do
            local ok, n = pcall(function() return o:GetFullName() end)
            if ok and n:find("UIViewmodelManager", 1, true) then aid_vm = o end
        end
    end
    local a, v = nil, nil
    if aid_part and aid_part:IsValid() then
        local d = aid_part.DrivingAids
        a = string.format("%d%d%d%d%d", d.Transmission, bit(d.bABSEnabled), bit(d.bTCSEnabled),
            bit(d.bHandbrakeStartingHelp), bit(d.bAutomaticClutch))
    end
    if aid_vm then
        local ok, s = pcall(function()
            return string.format("%d%d%d%d", bit(aid_vm.ABSEnabled), bit(aid_vm.TCSEnabled), aid_vm.Transmission,
                bit(aid_vm.bAutoClutch))
        end)
        v = ok and s or nil
    end
    return a, v
end
local aids_now, dash_now = nil, nil

-- The Rally Weekend's stage being driven as the game runs it (0.2): its track, weather, start time, time speed,
-- wetness, grip, random / dynamic weather, and its place in the calendar, to %APPDATA%\ACR Daily\ingame-setup.txt
-- ("ACRSETUP <n> <track> <weather> <seconds> <speed> <wet %> <grip> <random> <dynamic> <index> <ours>" / "ACRSETUP <n> none",
-- then "end <n>"), written when it changes. A run set up in the running game (drive.lua) is checked against it: the
-- game's save holds the set-up only once its results screen is left (it showed the one before as the screen came up,
-- 20 Nov 2026), so the app can't judge such a run from the save's first write (ingamedrive.py setup_changed).
local SETUP_FILE = DIR .. "ingame-setup.txt"
local UTIL = nil
local setup_now, setup_written, setup_f, setup_n = nil, false, nil, 0
local function read_setup(ev)
    local s = settings_comp                              -- (read_settings': this race event's settings)
    if not (s and s:IsValid()) then return nil end
    if not (UTIL and UTIL:IsValid()) then UTIL = StaticFindObject("/Script/acr.Default__RaceEventUtilsFunctionLibrary") end
    local i = UTIL:GetRallyWeekendSubEventIndex(UEHelpers.GetPlayerController())
    local sub = s.RallyWeekendCalendar.RallyWeekendSubEvents[i + 1]
    if not sub then return nil end
    local w = sub.WeatherOptions
    -- (last: did ACR DAILY take the game here? appui.lua's _G.ACRDAILY_OURS: 1 / 0, "-" with no appui)
    local o = rawget(_G, "ACRDAILY_OURS")
    return string.format("%s %d %d %d %d %d %d %d %d %s", sub.TrackId:ToString(), w.Preset.WeatherType,
        math.floor(w.StartingTime.TimeSeconds + 0.5), w.TimeSpeed, math.floor(w.StartingWetness * 100 + 0.5),
        w.StartingGripLevel, w.Preset.bRandom and 1 or 0, w.bDynamicWeather and 1 or 0, i,
        o == nil and "-" or (o and "1" or "0"))
end
local function write_setup()
    local line = setup_now or "none"
    if line == setup_written then return end
    if not setup_f then setup_f = io.open(SETUP_FILE, "w") end
    if not setup_f then return end
    setup_n = setup_n + 1
    local body = string.format("ACRSETUP %d %s\nend %d\n", setup_n, line, setup_n)
    setup_f:seek("set", 0)
    setup_f:write(body .. string.rep(" ", 120 - #body))
    setup_f:flush()
    setup_written = line
end

local function race_mode()
    if frame - mode_frame < 30 then return mode_now end   -- (twice a second is enough: it changes with a level)
    mode_frame = frame
    settings_now, aids_now, dash_now = nil, nil, nil
    setup_now = nil                                     -- (read again below for a Rally Weekend's race event)
    local ok, m = pcall(function()
        local world = UEHelpers.GetWorld()
        if not (world and world:IsValid()) then return "none" end
        local gs = world.GameState
        if not (gs and gs:IsValid()) then return "none" end
        local rem = gs.RaceEventManagerComponent
        if not (rem and rem.IsValid and rem:IsValid()) then return "none" end
        local ev = rem.RaceEvent
        if not (ev and ev.IsValid and ev:IsValid()) then return "none" end
        local sok, s = pcall(read_settings, ev)
        settings_now = sok and s or nil
        if mode_now == "weekend" and mode_event == ev:GetAddress() then
            local wok, w = pcall(read_setup, ev)
            setup_now = wok and w or nil
        end
        local aok, a, v = pcall(read_aids, ev)
        if aok then aids_now, dash_now = a, v end
        local at = ev:GetAddress()
        if at == mode_event and mode_now ~= "unknown" and mode_now ~= "none" then return mode_now end
        mode_event = at
        if not (RW_SETTINGS and RW_SETTINGS:IsValid()) then
            RW_SETTINGS = StaticFindObject("/Script/acr.RaceEventRaceSettingsRallyWeekendComponent")
        end
        if not (RW_SETTINGS and RW_SETTINGS:IsValid()) then return "unknown" end
        local comps = ev:K2_GetComponentsByClass(RW_SETTINGS)
        if comps and #comps > 0 then return "weekend" end
        local cn = ev:GetClass():GetFName():ToString():lower()
        if cn:find("singleevent", 1, true) then return "single" end
        if cn:find("practice", 1, true) then return "practice" end       -- (BC_RaceEventFreePractice_C)
        if cn:find("timeattack", 1, true) then return "timeattack" end   -- (BC_RaceEventTimeAttack_C)
        if cn:find("championship", 1, true) then return "championship" end
        return "other"
    end)
    if not ok then log("mode: %s", tostring(m)) end
    pcall(write_setup)
    local was = mode_now
    mode_now = ok and m or "unknown"
    if mode_now ~= was then log("mode: %s", mode_now) end
    return mode_now
end

local function write_camera(pc)
    local cm = pc and pc.PlayerCameraManager
    if not (cm and cm:IsValid()) then return end
    if not cam_f then
        cam_f = io.open(CAMERA_FILE, "w")          -- (made once; then overwritten in place)
        if not cam_f then return end
    end
    local l, r = cm:GetCameraLocation(), cm:GetCameraRotation()
    cam_seq = cam_seq + 1
    local line = string.format("CAM %d %.2f %.2f %.2f %.4f %.4f %.4f %.4f %d", cam_seq, l.X, l.Y, l.Z, r.Pitch, r.Yaw,
        r.Roll, cm:GetFOVAngle(), cam_seq)
    -- the game's mode (race_mode): "M <mode> <seq>"; the race's settings (read_settings): "S <rdcwfpht> <seq>"
    line = line .. string.format(" M %s %d", race_mode(), cam_seq)
    if names_by_game then line = line .. string.format(" N 1 %d", cam_seq) end
    if settings_now then line = line .. string.format(" S %s %d", settings_now, cam_seq) end
    -- the player's driving aids (read_aids): "A <gatbc> <seq>", the car's as its dash shows them: "V <atgc> <seq>"
    if aids_now then line = line .. string.format(" A %s %d", aids_now, cam_seq) end
    if dash_now then line = line .. string.format(" V %s %d", dash_now, cam_seq) end
    -- the cars hidden in your car (near_hide, last frame): "H <id>... <seq>", so the app draws no name over them either
    -- (an older app reads the line up to the first <seq> only)
    local hidden = {}
    for id, c in pairs(cars) do
        if c.near then hidden[#hidden + 1] = id end
    end
    if #hidden > 0 then
        local tail = string.format(" %d", cam_seq)
        local add = " H"
        for _, id in ipairs(hidden) do
            if #line + #add + #id + 1 + #tail > 159 then break end   -- (the line stays 160 characters at most)
            add = add .. " " .. id
        end
        line = line .. add .. tail
    end
    cam_f:seek("set", 0)                            -- (always 160 characters: a shorter line leaves nothing of the last)
    cam_f:write(line .. string.rep(" ", math.max(0, 159 - #line)) .. "\n")
    cam_f:flush()
    -- (where the camera is: near_hide; and which way it looks: the names over the cars, hud.lua)
    return {X = l.X, Y = l.Y, Z = l.Z, P = r.Pitch, Yw = r.Yaw, R = r.Roll, fov = cm:GetFOVAngle()}
end

local trace_check = -1

local function trace_frame(t)
    if frame - trace_check >= 120 then              -- (looked for every 120 frames)
        trace_check = frame
        local on = io.open(TRACE_FLAG, "r")
        if on then on:close() end
        if on and not trace then
            trace = io.open(DIR .. "ghost-trace.txt", "w")
        elseif not on and trace then
            trace:close()
            trace = nil
        end
    end
    if not trace then return end
    if frame % 120 == 0 and offset then trace:write(string.format("# offset %.4f\n", offset)) end
    for id, c in pairs(cars) do
        if c.shown then
            local p = c.shown
            trace:write(string.format("%d %.4f %s %.1f %.1f %.1f %.3f\n", frame, t, id, p[1], p[2], p[3], p[5]))
        end
    end
end

local function tick()
    frame = frame + 1
    spawned_this_frame = false
    local t = now()
    local me, pc = pawn()
    local cam = write_camera(pc)
    _G.ACRDAILY_NAMES = nil                            -- (the names over the cars, for hud.lua: set again below)
    local seq, when, ghosts, warm_now, names_now = read_ghosts(t)
    local fresh = seq and seq ~= last_seq
    if fresh then last_seq, last_new_t, warm, ghost_names = seq, t, warm_now, names_now or {} end
    if ghosts_f and t - math.max(last_new_t or 0, ghosts_opened or 0) > 2.0 then reopen_ghosts() end
    if not me then                                     -- (no car of yours: a menu, another stage loading)
        for id in pairs(cars) do remove(id, t, true) end
        empty_pool()
        pool_leader = nil
        return
    end
    local me_at = me:GetAddress()                      -- (Lua wrappers differ each time: compare the objects)
    if pool_leader ~= me_at then                       -- (another car of yours, a restart: the kept ones follow the old)
        empty_pool()
        pool_leader = me_at
    end
    if last_new_t and t - last_new_t > STALE_S then
        for id in pairs(cars) do remove(id, t) end     -- (the app stopped telling: kept for when it tells again)
        return
    end
    if fresh then
        local t_pose = when and app_to_here(when, t) or t
        for id, g in pairs(ghosts) do
            local c = cars[id]
            if c and (not c.actor:IsValid() or c.leader ~= me_at or c.cls ~= g.cls) then
                remove(id, t, c.leader ~= me_at)       -- (your car was replaced: a restart; or they changed car)
                c = nil
            end
            if not c then
                c = take(g.cls, me_at)                 -- (one kept: at once, no hitch)
                if not c and not spawned_this_frame then
                    c = make(me, g, me_at)             -- (else one new car a frame at most: the next file brings it)
                    spawned_this_frame = true
                end
                if c then cars[id] = c end
            end
            if c then
                c.seen_t = t
                took(c, g, t_pose, t)
            end
        end
    end
    warm_up(me, me_at, t)
    if frame % 60 == 0 then empty_pool(POOL_KEEP_S, t) end
    local me_loc = frame % 15 == 0 and me:K2_GetActorLocation() or nil   -- (near or far: a few times a second)
    local here = nil                                   -- (where your car is and which way it faces: near_hide)
    if next(cars) then
        local l, r = me:K2_GetActorLocation(), me:K2_GetActorRotation()
        local yaw = math.rad(r.Yaw)
        here = {X = l.X, Y = l.Y, Z = l.Z, cy = math.cos(yaw), sy = math.sin(yaw)}
        -- (the camera behind your car, a chase view: checked there too; bonnet, dash, helmet, bumper: it is in your car)
        here.cam_out = cam ~= nil and ((cam.X - l.X) ^ 2 + (cam.Y - l.Y) ^ 2 + (cam.Z - l.Z) ^ 2) > CAM_OUT ^ 2
    end
    for id, c in pairs(cars) do
        if t - (c.seen_t or t) > GONE_S then
            remove(id, t)
        elseif c.base and c.actor:IsValid() then       -- every frame: where it is now
            -- (moved, not teleported: the picture then knows how it moves, like every other car, for the motion
            -- blur and for DLSS / TAA and frame generation, which smeared or stuttered a car that teleported each
            -- frame; it has no physics and no collision, so nothing else changes)
            local p = carried(c, t)
            c.actor:K2_SetActorLocationAndRotation({X = p[1], Y = p[2], Z = p[3]},
                {Pitch = p[4], Yaw = p[5], Roll = p[6]}, false, {}, false)
            place_wheels(c, p)
            c.shown = p
            if here then near_hide(c, cam, here) end
            if frame % 60 == 0 then quiet_gauges(c) end
            if me_loc then detail(c, me_loc) end
        end
    end
    -- the drivers' names over their cars, drawn by hud.lua with the game's camera (not over one hidden in your car,
    -- nor one out of sight, as the app says)
    if cam and names_by_game then
        local list = {}
        for id, c in pairs(cars) do
            local n = ghost_names[id]
            if n and n.shown and c.shown and not c.near then
                list[#list + 1] = {x = c.shown[1], y = c.shown[2], z = c.shown[3] + NAME_UP, text = n.text,
                                   colour = n.colour}
            end
        end
        _G.ACRDAILY_NAMES = {cam = cam, list = list, t = t}
    end
    trace_frame(t)
end

-- The app's timer drawn in the game, for VR (hud.lua): when the app writes ingame-hud.txt.
local ok_hud, hud = pcall(require, "hud")
if not ok_hud or type(hud) ~= "table" then
    log("no hud.lua (%s): no timer in the game", tostring(hud))
    hud = nil
end
names_by_game = hud ~= nil                             -- (it draws the drivers' names over their cars too)

-- ACR DAILY inside the game (appui.lua, 0.2): MULTIPLAYER's ACR DAILY tile and the app's pages, while the app writes
-- ingame-app.txt. While %APPDATA%\ACR Daily\app-dev.on exists, appui.lua is loaded again when it changes on disk.
local ok_app, appui = pcall(require, "appui")
if not ok_app or type(appui) ~= "table" then
    log("no appui.lua (%s): no ACR DAILY in the game's menu", tostring(appui))
    appui = nil
end
local APP_DEV = DIR .. "app-dev.on"
local APP_HERE = (debug.getinfo(1, "S").source or ""):match("^@(.*[/\\])") or ""
local app_dev_size = nil
local function app_dev_reload()
    local flag = io.open(APP_DEV, "r")
    if not flag then return end
    flag:close()
    local size = ""
    for _, n in ipairs({"appui.lua", "drive.lua"}) do
        local h = io.open(APP_HERE .. n, "rb")
        if h then
            size = size .. tostring(h:seek("end")) .. "/"
            h:close()
        end
    end
    if app_dev_size == nil then app_dev_size = size end
    if size == app_dev_size then return end
    app_dev_size = size
    if appui and appui.unload then pcall(appui.unload) end
    package.loaded["drive"] = nil
    local ok, fresh = pcall(dofile, APP_HERE .. "appui.lua")
    log("dev: appui.lua loaded again: %s", ok and "ok" or tostring(fresh))
    if ok and type(fresh) == "table" then appui = fresh end
end

-- On the game thread, every frame (one loop for the mod's whole life: no callback made per frame). A UE4SS without
-- frame loops: as often as it runs delayed ones (each game frame, at most).
local errors, hud_errors, app_errors = 0, 0, 0
local function step()
    local ok, err = pcall(tick)
    if not ok then
        errors = errors + 1
        if errors <= 3 or errors % 300 == 0 then log("error (%d): %s", errors, tostring(err)) end
    end
    if hud then
        local ok2, err2 = pcall(hud.tick, now())
        if not ok2 then
            hud_errors = hud_errors + 1
            if hud_errors <= 3 or hud_errors % 300 == 0 then log("timer error (%d): %s", hud_errors, tostring(err2)) end
        end
    end
    if frame % 60 == 0 then pcall(app_dev_reload) end
    if appui then
        local ok3, err3 = pcall(appui.tick, now())
        if not ok3 then
            app_errors = app_errors + 1
            if app_errors <= 3 or app_errors % 300 == 0 then log("ACR DAILY pages error (%d): %s", app_errors, tostring(err3)) end
        end
    end
    return false
end
if type(LoopInGameThreadAfterFrames) == "function" then
    LoopInGameThreadAfterFrames(1, step)
    log("moving the cars every frame")
else
    LoopInGameThreadWithDelay(1, step)
    log("moving the cars every 1 ms at most (no frame loop in this UE4SS)")
end
