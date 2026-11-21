-- DRIVE inside the game (0.2): the app's set-up (a daily, a time trial, an event's rally) made in the running game
-- through the game's own calls, then the game goes to the Service Park: no save written, no restart, no key presses.
-- (Part of the ACR Daily mod: appui.lua starts it on the app's command and ticks it every frame.)
--
-- Probed in the game 20 Nov 2026 (docs/ingame-app.md, "DRIVE without restarting the game"):
--   PlayerRaceConfiguration:ServerSetRaceEventConfigurationId({DefaultRaceEventConfigurations, DefaultRally}) and
--   PlayerFlow:ServerExecuteFlow("FSM.Flow.SetupRaceEvent")      = RACING > RALLY > RALLY WEEKEND (its race event made)
--   RaceEventUtilsFunctionLibrary: SetRaceEventRallyWeekendCalendarPreset, AddDefaultedRallyWeekendSubEvent   calendar
--   the sub-event's own fields (Day, PreRaceZoneConfigurationId, WeatherOptions...)        written directly, read back
--   SelectRallyWeekendSubEvent(0)                                  the first stage's weather taken as the event's own
--   PlayerRaceConfiguration:ServerSetCar(id)                       the car, as the game's car pick does it
--   AutoSetTiresAllocationForLocalPlayerParticipant                J on the tyre screen
--   PlayerFlow:ServerExecuteFlow("FSM.Flow.StartRaceEvent")        CONFIRM AND START RALLY: to the Service Park
-- Never: a car id that isn't the game's (the game crashed loading the stage: 'eligible' says yes to anything), the
-- event's own WeatherOptions written (crashed once: the game copies the stage's with SelectRallyWeekendSubEvent).
--
-- setup (from the app, ingamedrive.py): {preset, car, stages = [{track, day, service, weather, start, wet}],
--   rules = {respawn, damage, collisions, wear, failures, penalty, hardcore}, opponents, order,
--   tyres = {<compound row>: count} (optional: the game's own otherwise), livery = <livery name> (optional)}
-- Answers through tell("drive", "<n> ok" | "<n> error <why>" | "<n> step <what>").
local UEHelpers = require("UEHelpers")

local D = {}
local TAG = "[ACRDailyDrive] "
local function log(fmt, ...) print(TAG .. string.format(fmt, ...) .. "\n") end

local LIB = "/Script/acr.Default__RaceEventUtilsFunctionLibrary"
local WAIT_EVENT_S = 6.0          -- the Rally Weekend's race event made, at most this long after SetupRaceEvent
local WAIT_DIALOG_S = 15.0        -- the game's CONTINUE RALLY WEEKEND question up, at most this long (it loads the rally first)

local job = nil                   -- {n, setup, tell, step, at, t0}
local livery, livery_world, livery_at, livery_done = nil, nil, 0, 0   -- (dress(): the livery for the rally's stages)

local function lib()
    local l = StaticFindObject(LIB)
    if not (l and l:IsValid()) then error("no RaceEventUtilsFunctionLibrary") end
    return l
end

local function live(class)
    -- the live one: in a level or the engine's own objects (not a class default, not a blueprint's template)
    for _, x in ipairs(FindAllOf(class) or {}) do
        local ok, n = pcall(function() return x:GetFullName() end)
        if ok and x:IsValid() and not n:find("Default__", 1, true) and
           (n:find("PersistentLevel", 1, true) or n:find("/Engine/Transient", 1, true)) then
            return x
        end
    end
    return nil
end

local function in_main_menu()
    -- the game's main menu up (the live WB_MainMenu, in the menu's level)
    local ok, world = pcall(UEHelpers.GetWorld)
    local level = ok and world and world:IsValid() and world:GetFullName() or ""
    return live("WB_MainMenu_C") ~= nil and level:find("MainMenu", 1, true) ~= nil
end

local function fail(why)
    log("DRIVE %s: %s", tostring(job and job.n), why)
    if job then job.tell("drive", string.format("%s error %s", job.n, why)) end
    job = nil
end

local function step_said(what)
    if job then job.tell("drive", string.format("%s step %s", job.n, what)) end
end

-- the steps, each run once on its own frame; one returns true when done, false to be run again next frame (waiting)
local steps = {}

steps[1] = function(t)
    if not in_main_menu() then error("not in the game's main menu") end
    local cfg = live("PlayerRaceConfigurationComponent")
    local flow = live("PlayerFlowComponent")
    if not (cfg and flow) then error("the game's menu isn't ready") end
    cfg:ServerSetRaceEventConfigurationId({Table = FName("DefaultRaceEventConfigurations"), Row = FName("DefaultRally")})
    flow:ServerExecuteFlow(FName("FSM.Flow.SetupRaceEvent"))
    step_said("rally weekend")
    return true
end

steps[2] = function(t)
    -- wait for the Rally Weekend's race event and its settings
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    local ev = L:GetRaceEvent(pc)
    local ok = ev and ev:IsValid() and L:GetRaceEventConfigurationId(pc):ToString() == "DefaultRally"
    local c = ok and L:GetRaceEventRaceSettingsRallyWeekendComponent(pc)
    if not (c and c:IsValid()) then
        if t - job.at > WAIT_EVENT_S then error("the game's Rally Weekend didn't come up") end
        return false
    end
    -- (not IsRallyInProgress: it is true for any Rally Weekend set up in the menu, a save with none in progress too,
    -- seen 20 Nov 2026. A rally of the player's in progress is the app's to see, in the save: ingamedrive.ready)
    return true
end

steps[3] = function(t)
    local s = job.setup
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    L:SetRaceEventRallyWeekendCalendarPreset(pc, FName(s.preset))
    for k, st in ipairs(s.stages) do
        L:AddDefaultedRallyWeekendSubEvent(pc, FName(st.track), k == 1, not st.service, k - 1, false)
    end
    local c = L:GetRaceEventRaceSettingsRallyWeekendComponent(pc)
    local subs = c.RallyWeekendCalendar.RallyWeekendSubEvents
    if #subs ~= #s.stages then error(string.format("the calendar holds %d stages, not %d", #subs, #s.stages)) end
    for k, st in ipairs(s.stages) do
        local sub = subs[k]
        if sub.TrackId:ToString():lower() ~= st.track:lower() then
            error(string.format("stage %d is %s, not %s", k, sub.TrackId:ToString(), st.track))
        end
        sub.Day = st.day
        sub.PreRaceZoneConfigurationId = FName(st.service and "ServiceParkDefault" or "NoZone")
        local w = sub.WeatherOptions
        w.Preset.WeatherType = st.weather
        w.Preset.bRandom = false
        w.TargetPreset.WeatherType = st.weather
        w.TargetPreset.bRandom = false
        w.bDynamicWeather = false
        w.StartingTime.TimeSeconds = st.start + 0.0
        w.TimeSpeed = 0                      -- time stands still: the same light for everyone
        w.StartingWetness = (st.wet or 0) + 0.0
        w.StartingAccumulatedSnow = 0.0
        w.StartingGripLevel = 4              -- optimal
    end
    local cal = c.RallyWeekendCalendar
    cal.bIsCustomPreset = true
    -- read back
    for k, st in ipairs(s.stages) do
        local sub = c.RallyWeekendCalendar.RallyWeekendSubEvents[k]
        local w = sub.WeatherOptions
        if sub.Day ~= st.day or w.Preset.WeatherType ~= st.weather or math.abs(w.StartingTime.TimeSeconds - st.start) > 1 then
            error(string.format("stage %d didn't take its day / weather / time", k))
        end
    end
    L:SelectRallyWeekendSubEvent(pc, 0)
    if not L:IsRaceEventConsistent(pc) then error("the game says the calendar isn't consistent") end
    step_said("calendar")
    return true
end

steps[4] = function(t)
    -- the rules (the daily's / the event's), on the event's settings; read back
    local r, s = job.setup.rules or {}, job.setup
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    local set = L:GetRaceEventRaceSettingsComponent(pc)
    local o = set.RaceOptions
    o.Respawn.ManualRespawn = r.respawn
    o.CarDamage.bDamagesEnabled = r.damage == 1
    o.CarDamage.Collisions = r.collisions
    o.CarDamage.Wear = r.wear
    o.CarDamage.MechanicalFailures = r.failures
    set.RacePenaltyOptions.RacePenalty = r.penalty
    set.HardCoreOptions.bHardCore = r.hardcore == 1
    set.AIOptions.NumOfOpponents = s.opponents or 1
    local rally = L:GetRaceEventRaceSettingsRallyComponent(pc)
    rally.RunningOrderOptions.RunningOrderType = s.order_type or 1   -- custom
    rally.RunningOrderOptions.RunningOrder = s.order or 1             -- first on the road
    local o2 = L:GetRaceEventRaceSettingsComponent(pc).RaceOptions
    local d = o2.CarDamage
    local got = string.format("%d%d%d%d%d%d", o2.Respawn.ManualRespawn, d.bDamagesEnabled and 1 or 0, d.Collisions, d.Wear,
                              d.MechanicalFailures, L:GetRaceEventRaceSettingsComponent(pc).RacePenaltyOptions.RacePenalty)
    local want = string.format("%d%d%d%d%d%d", r.respawn, r.damage, r.collisions, r.wear, r.failures, r.penalty)
    if got ~= want then error("the rules didn't take: " .. got .. " not " .. want) end
    step_said("rules")
    return true
end

steps[5] = function(t)
    live("PlayerRaceConfigurationComponent"):ServerSetCar(FName(job.setup.car))
    step_said("car")
    -- (the livery picked, setup.livery: the car's official one's name, or "usergen_<folder>" for one in
    -- Documents\My Games\acr\Liveries\<car>: put on the car in each stage's level, dress() below. The garage's own
    -- pick for the car is left as it is)
    return true
end

-- The tyres: the game's own allocation first (J on its tyre screen: every compound the rally allows, its total), then
-- the player's counts (setup.tyres = {<compound row>: n}) written over it in place when they fit: only compounds the
-- game offers, adding up to its total (the map can't be passed from Lua: probed 21 Nov 2026). Otherwise the game's own
-- stays, and the answer says so.
local function own_participant_data()
    local want = UEHelpers.GetPlayerController().PlayerState.ParticipantId:ToString()
    for _, o in ipairs(FindAllOf("BC_RaceParticipant_C") or {}) do
        local ok, id = pcall(function() return o.ID:ToString() end)
        if ok and id == want then return o.RaceParticipantData end
    end
    return nil
end

local function chosen_tyres(wanted)
    local d = own_participant_data()
    if not d then return "no participant" end
    local ta = d.TiresAllocation
    local m = ta.Compounds
    local have, total = {}, 0
    m:ForEach(function(k, v) have[k:get().Row:ToString()] = true end)
    for row, n in pairs(wanted) do
        if not have[row] then return "not in this rally: " .. row end
        total = total + n
    end
    if total <= 0 then return "no tyres" end
    -- (the app counts out of 16, the game's tyre screen for a short rally; a rally that takes another number gets the
    -- same shares of it, the largest remainders rounded up)
    local scaled, given, rest = {}, 0, {}
    for row, n in pairs(wanted) do
        local x = n * ta.Count / total
        scaled[row] = math.floor(x)
        given = given + scaled[row]
        rest[#rest + 1] = {row = row, r = x - scaled[row]}
    end
    table.sort(rest, function(a, b) return a.r > b.r end)
    for i = 1, ta.Count - given do scaled[rest[(i - 1) % #rest + 1].row] = scaled[rest[(i - 1) % #rest + 1].row] + 1 end
    m:ForEach(function(k, v) v:set(scaled[k:get().Row:ToString()] or 0) end)
    live("PlayerRaceConfigurationComponent"):ServerSetTiresAllocation(ta)
    return nil
end

steps[6] = function(t)
    local L = lib()
    local pc = UEHelpers.GetPlayerController()
    L:AutoSetTiresAllocationForLocalPlayerParticipant(pc)
    if not L:HasTiresAllocatedForLocalPlayerParticipant(pc) then error("no tyres allocated") end
    if type(job.setup.tyres) == "table" and next(job.setup.tyres) then
        local ok, why = pcall(chosen_tyres, job.setup.tyres)
        if ok and why == nil then
            step_said("tyres chosen")
        else
            L:AutoSetTiresAllocationForLocalPlayerParticipant(pc)      -- (the game's own again: whatever was half done)
            step_said("tyres auto " .. tostring(why))
        end
    end
    if not L:IsRaceEventConsistent(pc) then error("the game says the rally isn't consistent") end
    step_said("tyres")
    return true
end

steps[7] = function(t)
    live("PlayerFlowComponent"):ServerExecuteFlow(FName("FSM.Flow.StartRaceEvent"))
    log("DRIVE %s: started (%s, %s, %d stages)", tostring(job.n), job.setup.preset, job.setup.car, #job.setup.stages)
    job.tell("drive", string.format("%s ok", job.n))
    job = nil
    return true
end

-- CONTINUE (a rally of the player's in progress in the game: an event's, set up before): the game's own way back into
-- it, its buttons pressed from here as the player would (probed 21 Nov 2026). The flow "ResumeRaceEvent" alone, sent
-- with no menu screen, started the default calendar instead (Wales, not the rally in progress: the menu loads the rally
-- from the save as its RALLY WEEKEND screen opens). So: the RACING page's RALLY tile, the RALLY page's RALLY WEEKEND
-- tile (its second), and the game's own question CONTINUE RALLY WEEKEND: RESUME (its first button). Buttons found by
-- their class and place, never their words (the game's language). Each pressed with HandleButtonClicked, as a click.
local function transient(class)
    local out = {}
    for _, x in ipairs(FindAllOf(class) or {}) do
        local ok, n = pcall(function() return x:GetFullName() end)
        if ok and x:IsValid() and n:find("/Engine/Transient", 1, true) and not n:find("Default__", 1, true) then
            out[#out + 1] = x
        end
    end
    return out
end

local function visible(list)
    local out = {}
    for _, b in ipairs(list) do
        local ok, v = pcall(function() return b:IsVisible() end)
        if ok and v then out[#out + 1] = b end
    end
    return out
end

local function press(b, what)
    b:HandleButtonClicked()
    step_said(what)
    return true
end

local PANEL_, CONTENT_ = nil, nil
local function find(root, name)
    PANEL_ = PANEL_ or StaticFindObject("/Script/UMG.PanelWidget")
    CONTENT_ = CONTENT_ or StaticFindObject("/Script/UMG.ContentWidget")
    local hit
    local function walk(w, d)
        if hit or d > 12 or not (w and w:IsValid()) then return end
        if w:GetFName():ToString() == name then hit = w return end
        if w:IsA(PANEL_) then
            for i = 0, w:GetChildrenCount() - 1 do walk(w:GetChildAt(i), d + 1) end
        elseif w:IsA(CONTENT_) then
            local ok, ch = pcall(function() return w:GetContent() end)
            if ok then walk(ch, d + 1) end
        end
    end
    walk(root, 0)
    return hit
end

local resume_steps = {
    function(t)                                  -- RACING's RALLY tile (the switcher's second page)
        if not in_main_menu() then error("not in the game's main menu") end
        local sel = transient("WB_SelectWidget_C")[1]
        if not sel then error("the game's menu isn't ready") end
        local sw = find(sel.WidgetTree.RootWidget, "OptionSwitcher")
        local racing = sw and sw:GetChildAt(1)
        local slot = racing and find(racing.WidgetTree.RootWidget, "RallyContainer")
        local tile = slot and slot:GetContent() and slot:GetContent():GetContent()
        if not (tile and tile:IsValid()) then error("no RALLY tile in the game's menu") end
        return press(tile, "rally")
    end,
    function(t)                                  -- the RALLY page's second tile: RALLY WEEKEND
        local subs = visible(transient("WB_SubSelectionButton_C"))
        if #subs < 2 then
            if t - job.at > WAIT_EVENT_S then error("the game's RALLY page didn't come up") end
            return false
        end
        return press(subs[2], "rally weekend")
    end,
    function(t)                                  -- its question CONTINUE RALLY WEEKEND: RESUME (its confirm button; CREATE
        local btns = visible(transient("WB_ConfirmationButton_C"))   -- NEW is another kind), or none: no rally
        local asked = #visible(transient("WB_DialogConfirm_C")) > 0
        if #btns < 1 or not asked then
            if t - job.at > WAIT_DIALOG_S then error("no rally in progress in the game") end
            return false
        end
        press(btns[1], "resume")
        log("CONTINUE %s: resumed", tostring(job.n))
        job.tell("drive", string.format("%s ok", job.n))
        job = nil
        return true
    end,
}
--- The app's DRIVE: n (its number), setup (above), tell (appui's). -> false when one is already being done.
function D.start(n, setup, tell, t)
    if job then
        tell("drive", string.format("%s error busy", n))
        return false
    end
    local resume = type(setup) == "table" and setup.resume == true
    if not resume and (type(setup) ~= "table" or type(setup.stages) ~= "table" or #setup.stages == 0 or not setup.car
                       or not setup.preset) then
        tell("drive", string.format("%s error bad set-up", n))
        return false
    end
    job = {n = n, setup = setup, tell = tell, step = 1, at = t, wait = 2, steps = resume and resume_steps or steps}
    -- the livery for the stages to come (or none: the game's own pick)
    livery = (type(setup.livery) == "string" and setup.livery ~= "") and setup.livery or nil
    livery_world = nil
    log("DRIVE %s: %s, %s", tostring(n), setup.preset, setup.car)
    return true
end

function D.busy() return job ~= nil end

-- The livery picked, put on the car in each stage's level (the game dresses the car from its own per-car pick as a
-- level loads: the menu's OnLiveryChanged didn't reach the stage, PlayerCustomization:ApplyLivery on the stage's own
-- player did, probed 21 Nov 2026). A few times after the level came: the game dresses the car from its own pick later
-- than 6 s (it was its livery again then), and one put on at the Service Park stays to the start line and on.
local LIVERY_AT = {2.0, 6.0, 12.0, 20.0, 35.0}
local function dress(t)
    if not livery then return end
    local okw, w = pcall(UEHelpers.GetWorld)
    local name = okw and w and w:IsValid() and w:GetFullName() or ""
    if name == "" or name:find("MainMenu", 1, true) then
        livery_world = nil
        return
    end
    if livery_world ~= name then
        livery_world, livery_at, livery_done = name, t, 0
    end
    local due = LIVERY_AT[livery_done + 1]
    if not due or t - livery_at < due then return end
    livery_done = livery_done + 1
    local c = nil
    for _, x in ipairs(FindAllOf("PlayerCustomizationComponent") or {}) do
        local ok, n = pcall(function() return x:GetFullName() end)
        if ok and n:find("PersistentLevel", 1, true) and n:find("RacePlayerController", 1, true) then c = x end
    end
    if c then
        local ok = pcall(function() c:ApplyLivery(FName(livery)) end)
        log("livery %s on the stage's car: %s", livery, ok and "ok" or "failed")
    end
end

--- every frame (appui.lua)
function D.tick(t)
    pcall(dress, t)
    if not job then return end
    if job.wait > 0 then
        job.wait = job.wait - 1
        return
    end
    local f = job.steps[job.step]
    if not f then job = nil return end
    local ok, done = pcall(f, t)
    if not ok then
        fail(tostring(done):gsub("^.-:%d+: ", ""))
        return
    end
    if done and job then
        job.step = job.step + 1
        job.at = t
        job.wait = 6                     -- (a few frames between steps: the game's own calls settle)
    end
end

return D
