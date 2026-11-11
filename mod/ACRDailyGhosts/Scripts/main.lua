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
-- ingame-camera.txt:   CAM <seq> <X> <Y> <Z> <Pitch> <Yaw> <Roll> <horizontal fov> <seq>   (padded to 160 characters)
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
    local out, warm_now = {}, {}
    for line in text:sub(1, stop):gmatch("\n([^\n]+)") do               -- (up to the end: never what lies after it)
        local w = {}
        for x in line:gmatch("%S+") do w[#w + 1] = x end
        if #w >= 15 and w[15] ~= seq then return nil end                -- (a line of another update)
        if w[1] == "warm" and #w >= 4 then                               -- warm <class> <how many> <seq>
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
    return seq, tonumber(when), out, warm_now
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
    cam_f:seek("set", 0)                            -- (always 160 characters: a shorter line leaves nothing of the last)
    cam_f:write(line .. string.rep(" ", math.max(0, 159 - #line)) .. "\n")
    cam_f:flush()
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
    write_camera(pc)
    local seq, when, ghosts, warm_now = read_ghosts(t)
    local fresh = seq and seq ~= last_seq
    if fresh then last_seq, last_new_t, warm = seq, t, warm_now end
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
            if frame % 60 == 0 then quiet_gauges(c) end
            if me_loc then detail(c, me_loc) end
        end
    end
    trace_frame(t)
end

-- On the game thread, every frame (one loop for the mod's whole life: no callback made per frame). A UE4SS without
-- frame loops: as often as it runs delayed ones (each game frame, at most).
local errors = 0
local function step()
    local ok, err = pcall(tick)
    if not ok then
        errors = errors + 1
        if errors <= 3 or errors % 300 == 0 then log("error (%d): %s", errors, tostring(err)) end
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
