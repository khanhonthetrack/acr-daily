-- ACR Daily ghost cars, in the game (a UE4SS Lua mod).
--
-- The ACR Daily app writes where the ghost cars are (your own last run, the other drivers live) to
-- %APPDATA%\ACR Daily\ingame-ghosts.txt about 60 times a second; this mod puts a real car there for each:
-- a copy of your own car (its physics off, nothing to hit), its suspension and body following your car's
-- (so it sits on its wheels), moved every frame. It also writes the game's camera to
-- %APPDATA%\ACR Daily\ingame-camera.txt, so the app can put the names above the cars exactly.
--
-- ingame-ghosts.txt:   ACRDG 1 <seq>
--                      <id> <X> <Y> <Z> <Pitch> <Yaw> <Roll>        (the game's units: cm, degrees; one per car)
--                      end
-- ingame-camera.txt:   CAM <seq> <X> <Y> <Z> <Pitch> <Yaw> <Roll> <horizontal fov>
local UEHelpers = require("UEHelpers")

local TAG = "[ACRDailyGhosts] "
local DIR = (os.getenv("APPDATA") or ".") .. "\\ACR Daily\\"
local GHOSTS_FILE = DIR .. "ingame-ghosts.txt"
local CAMERA_FILE = DIR .. "ingame-camera.txt"
local STALE_FRAMES = 90          -- the app's file not changing for this many frames (~1.5 s): ghosts hidden
local GONE_FRAMES = 30           -- a ghost missing from the file this long: removed

local cars = {}                  -- id -> {actor, seen, leader}
local last_seq, same_for = nil, 0
local frame = 0
local cam_seq = 0
local spawned_this_frame = false

local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end
log("loaded")

local function pawn()
    local pc = UEHelpers.GetPlayerController()
    if pc and pc:IsValid() then
        local p = pc.Pawn
        if p and p:IsValid() and p.SetInputEnabled then return p, pc end
        return nil, pc
    end
end

local function read_ghosts()
    local f = io.open(GHOSTS_FILE, "r")
    if not f then return nil end
    local text = f:read("a")
    f:close()
    if not text or not text:find("\nend") then return nil end   -- (being written: next frame)
    local seq = text:match("^ACRDG 1 (%d+)")
    if not seq then return nil end
    local out = {}
    for id, x, y, z, p, yaw, r in text:gmatch("\n(%S+) (%S+) (%S+) (%S+) (%S+) (%S+) (%S+)") do
        if id ~= "end" then
            out[id] = {tonumber(x), tonumber(y), tonumber(z), tonumber(p), tonumber(yaw), tonumber(r)}
        end
    end
    return seq, out
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

local function follow_pose(ghost, me)
    local mine = skinned(me)
    for name, c in pairs(skinned(ghost)) do
        if mine[name] then c:SetLeaderPoseComponent(mine[name], true, false) end
    end
end

local function transform(g)
    local half = math.rad(g[5]) / 2
    return {Rotation = {X = 0.0, Y = 0.0, Z = math.sin(half), W = math.cos(half)},
            Translation = {X = g[1], Y = g[2], Z = g[3]}, Scale3D = {X = 1.0, Y = 1.0, Z = 1.0}}
end

local function spawn(me, g)
    local gs = UEHelpers.GetGameplayStatics()
    local t = transform(g)
    local a = gs:BeginDeferredActorSpawnFromClass(UEHelpers.GetWorld(), me:GetClass(), t, 1, nil, 0)
    if not a or not a:IsValid() then return nil end
    a.bInitializePhysics = false                      -- a picture of a car: no physics, nothing to drive
    gs:FinishSpawningActor(a, t, 0)
    a:SetActorEnableCollision(false)
    a:SetInputEnabled(false)
    follow_pose(a, me)
    return a
end

local function remove(id)
    local c = cars[id]
    if c and c.actor and c.actor:IsValid() then c.actor:K2_DestroyActor() end
    cars[id] = nil
end

local function write_camera(pc)
    local cm = pc and pc.PlayerCameraManager
    if not (cm and cm:IsValid()) then return end
    local l, r = cm:GetCameraLocation(), cm:GetCameraRotation()
    cam_seq = cam_seq + 1
    local f = io.open(CAMERA_FILE .. ".tmp", "w")
    if not f then return end
    f:write(string.format("CAM %d %.2f %.2f %.2f %.4f %.4f %.4f %.4f\n", cam_seq, l.X, l.Y, l.Z, r.Pitch, r.Yaw, r.Roll,
        cm:GetFOVAngle()))
    f:close()
    os.remove(CAMERA_FILE)
    os.rename(CAMERA_FILE .. ".tmp", CAMERA_FILE)
end

local function tick()
    frame = frame + 1
    spawned_this_frame = false
    local me, pc = pawn()
    write_camera(pc)
    local seq, ghosts = read_ghosts()
    if seq then
        if seq == last_seq then same_for = same_for + 1 else same_for, last_seq = 0, seq end
    end
    if not me or same_for > STALE_FRAMES or not ghosts then
        if not me or same_for > STALE_FRAMES then
            for id in pairs(cars) do remove(id) end
        end
        return
    end
    local me_at = me:GetAddress()                      -- (Lua wrappers differ each time: compare the objects)
    for id, g in pairs(ghosts) do
        local c = cars[id]
        if c and (not c.actor:IsValid() or c.leader ~= me_at) then
            remove(id)                                 -- (your car was replaced: a restart)
            c = nil
        end
        if not c and spawned_this_frame then
            -- one new car a frame at most
        elseif not c then
            local a = spawn(me, g)
            spawned_this_frame = true
            if a then
                c = {actor = a, leader = me_at}
                cars[id] = c
            end
        end
        if c then
            c.seen = frame
            c.actor:K2_SetActorLocationAndRotation({X = g[1], Y = g[2], Z = g[3]},
                {Pitch = g[4], Yaw = g[5], Roll = g[6]}, false, {}, true)
        end
    end
    for id, c in pairs(cars) do
        if frame - (c.seen or 0) > GONE_FRAMES then remove(id) end
    end
end

-- on the game thread, every 16 ms (one loop for the mod's whole life: no callback made per frame)
LoopInGameThreadWithDelay(16, function()
    local ok, err = pcall(tick)
    if not ok and frame % 300 == 1 then log("error: %s", tostring(err)) end
    return false
end)
