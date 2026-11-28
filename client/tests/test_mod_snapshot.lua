-- The game mod's copy of the car at the finish line (drive.lua: snap_read / snap_write), run outside the game with
-- stand-ins for the engine's objects (test_mod_snapshot.py runs it with any Lua found). Prints "ok" or fails.
package.preload["UEHelpers"] = function() return {} end
RegisterHook = function() end
local here = arg[1]
local D = dofile(here .. "/drive.lua")
local S = D._snap
local function name(s) return {ToString = function() return s end} end
local function part(id, lp) return {ID = name(id), LifePoints = lp, bRepaired = false} end
local function wear(v) return {Wear = {Value = v}} end
local function bone(n, d) return {Name = name(n), State = {CurrentDeformation = d, DeformationRand = 3}} end
local function car(parts, bones, glass)
    return {
        CarState = {BrakesDiscsStatus = {wear(0.1), wear(0.2)}, BrakesPadsStatus = {wear(0.3)}, ClutchStatus = wear(0.4),
                    DifferentialsStatus = {wear(0.5)}},
        CarDestruction = {CarDeformer = {DeformableBones = bones},
            ConstrainedComponents = {ksState = {Components = {}, ComponentsConstraints = {}}, ConstrainedComponentsState = {}}},
        CarDamage = {PartsStates = parts},
        LightsDamage = {ZoneDamages = {0.1, 0.2}},
        CarFX = {ZonesData = {{Values = {1, 2}, Damages = 0.5}}, GenericDirt = 0.7},
        Windshields = {Windshields = {{ComponentName = name("Front"), BakedCracksIntensities = {X = glass, Y = 0, Z = 0, W = 0}}}},
    }
end
local function check(c, msg) if not c then error(msg, 2) end end

-- the car at the line: engine 0.5, one bent bone, a cracked windscreen
local at_line = S.read(car({part("Engine", 0.5), part("Radiator", 0.7)}, {bone("Bumper_F", 0.2)}, 0.6), S.CAR)
-- the game's store at NEXT STAGE, after a crash past the line: worse engine, front lights broken, more bones bent
local stored = car({part("Engine", 0.05), part("Radiator", 0.7), part("FrontLights", 0.0)},
    {bone("Bumper_F", 0.9), bone("Hood", 0.8)}, 1.0)
stored.CarState.ClutchStatus.Wear.Value = 0.9
stored.LightsDamage.ZoneDamages = {1.0, 1.0}
local st = {set = 0, skipped = 0}
S.write(stored, S.CAR, at_line, st)
check(stored.CarDamage.PartsStates[1].LifePoints == 0.5, "engine as at the line")
check(stored.CarDamage.PartsStates[3].LifePoints == 1.0, "front lights broken past the line: as new")
check(stored.CarDestruction.CarDeformer.DeformableBones[1].State.CurrentDeformation == 0.2, "bumper as at the line")
check(stored.CarDestruction.CarDeformer.DeformableBones[2].State.CurrentDeformation == 0.0, "hood bent past the line: straight")
check(stored.CarState.ClutchStatus.Wear.Value == 0.4, "clutch wear as at the line")
check(stored.LightsDamage.ZoneDamages[1] == 0.1, "lights as at the line")
check(stored.Windshields.Windshields[1].BakedCracksIntensities.X == 0.6, "windscreen as at the line")
check(st.set > 10, "fields written")

-- tyres by their id; a different list of lights is left alone (by place only when the lengths match)
local function tyre(id, n) return {ID = name(id), MaxTread = {1, 1}, PreviousEquippedIndex = 0,
    Damage = {Wear = {Tread = {1, 1}, Grain = 0, Blister = 0, Marbles = 0, FlatSpot = 0, Normalized = n}, Value = 0,
              Deflation = 0, bPunctured = false}} end
local t_line = S.read({ProviderState = {Tires = {tyre("Soft_0", 0.33), tyre("Soft_1", 0.1)}}}, S.TYRES)
local t_store = {ProviderState = {Tires = {tyre("Soft_1", 0.9), tyre("Soft_0", 0.9)}}}
t_store.ProviderState.Tires[2].Damage.bPunctured = true
S.write(t_store, S.TYRES, t_line, {set = 0, skipped = 0})
check(t_store.ProviderState.Tires[1].Damage.Wear.Normalized == 0.1, "tyre matched by id")
check(t_store.ProviderState.Tires[2].Damage.Wear.Normalized == 0.33, "tyre matched by id (2)")
check(t_store.ProviderState.Tires[2].Damage.bPunctured == false, "a puncture past the line: not kept")
local other = car({}, {}, 0)
other.LightsDamage.ZoneDamages = {0.9, 0.9, 0.9}
local st2 = {set = 0, skipped = 0}
S.write(other, S.CAR, at_line, st2)
check(other.LightsDamage.ZoneDamages[3] == 0.9 and st2.skipped > 0, "another list of lights: left")

-- the car kept on disk (ingame-finishcar.json) and back from the app as JSON: places come back as keys "1", "2"...,
-- norm makes them numbers again, and it writes into a new car exactly as the car kept in memory does
local function decode(s)                       -- (a small JSON reader for the test: objects, numbers, true/false, strings)
    local i = 1
    local function ws() i = s:find("%S", i) or #s + 1 end
    local val
    local function str()
        local j = s:find('"', i + 1, true)
        local out = s:sub(i + 1, j - 1):gsub("\\u(%x%x%x%x)", function(h) return string.char(tonumber(h, 16)) end)
        i = j + 1
        return out
    end
    function val()
        ws()
        local c = s:sub(i, i)
        if c == "{" then
            local t = {}
            i = i + 1
            ws()
            if s:sub(i, i) == "}" then i = i + 1 return t end
            while true do
                ws()
                local k = str()
                ws()
                i = i + 1                      -- (:)
                t[k] = val()
                ws()
                local sep = s:sub(i, i)
                i = i + 1
                if sep == "}" then return t end
            end
        elseif c == '"' then
            return str()
        elseif s:sub(i, i + 3) == "true" then
            i = i + 4 return true
        elseif s:sub(i, i + 4) == "false" then
            i = i + 5 return false
        end
        local j = s:find("[,}%]]", i)
        local n = tonumber(s:sub(i, j - 1))
        i = j
        return n
    end
    return val()
end
local text = S.json({v = 1, car = at_line, tyres = t_line, lights = "A,B"})
local back = S.norm(decode(text))
check(back.lights == "A,B", "lights' zone names kept")
local fresh = car({part("Engine", 1.0), part("Radiator", 1.0)}, {bone("Bumper_F", 0.0)}, 0)
local st3 = {set = 0, skipped = 0}
S.write(fresh, S.CAR, back.car, st3)
check(math.abs(fresh.CarDamage.PartsStates[1].LifePoints - 0.5) < 1e-6, "engine back from JSON")
check(math.abs(fresh.CarDestruction.CarDeformer.DeformableBones[1].State.CurrentDeformation - 0.2) < 1e-6, "bumper back from JSON")
check(math.abs(fresh.LightsDamage.ZoneDamages[2] - 0.2) < 1e-6, "lights by place back from JSON")
check(math.abs(fresh.CarFX.ZonesData[1].Values[2] - 2) < 1e-6, "dirt zones back from JSON")
check(math.abs(fresh.Windshields.Windshields[1].BakedCracksIntensities.X - 0.6) < 1e-6, "windscreen back from JSON")
local t_new = {ProviderState = {Tires = {tyre("Soft_0", 1.0)}}}
S.write(t_new, S.TYRES, back.tyres, {set = 0, skipped = 0})
check(math.abs(t_new.ProviderState.Tires[1].Damage.Wear.Normalized - 0.33) < 1e-6, "tyre back from JSON")

-- the setup at the line (28 Nov 2026: a driver's own setup came back as "balanced"): its settings by path, as strings
-- (the game's FString: read with ToString, written with a Lua string), its ID; back from JSON; a setting the car at the
-- line didn't list left as it is
FName = function(s) return name(s) end
local function setting(path, value)
    local raw = {Path = name(path), v = value}
    return setmetatable({}, {
        __index = function(_, k) if k == "Value" then return name(raw.v) end return raw[k] end,
        __newindex = function(_, k, v) if k == "Value" then raw.v = v else raw[k] = v end end})
end
local function setup(id, list) return {Setup = {ID = name(id), Settings = list}} end
local s_line = S.setup_read(setup("MyGravel", {setting("Suspension.Front.Spring", "85000"), setting("Brakes.Bias", "0.58")}))
check(s_line.id == "MyGravel" and s_line.n == 2 and s_line.by["Brakes.Bias"] == "0.58", "the setup read")
local s_back = S.norm(decode(S.json({setup = s_line}))).setup
local balanced = setup("Balanced", {setting("Brakes.Bias", "0.62"), setting("Suspension.Front.Spring", "70000"),
                                    setting("Diff.Preload", "80")})
local sst = {set = 0, skipped = 0}
S.setup_write(balanced, s_back, sst)
check(balanced.Setup.Settings[1].Value:ToString() == "0.58", "brake bias as at the line")
check(balanced.Setup.Settings[2].Value:ToString() == "85000", "springs as at the line")
check(balanced.Setup.Settings[3].Value:ToString() == "80", "a setting not listed at the line: left")
check(balanced.Setup.ID:ToString() == "MyGravel", "the setup's id")
check(sst.set == 2 and sst.skipped == 0, "two written")

-- a part's state from its life points, as the game set them on a Service Park (27 Nov 2026): the engine's and the
-- bodywork's thresholds as the game has them (single precision)
local ENGINE = {1.0, 0.99000000953674, 0.85000002384186, 0.34999999403954, 0.050000000745058}
local BODY = {1.0, 0.99000000953674, 0.89999997615814, 0.34999999403954}
check(D._state_of(35, 100, ENGINE) == 3, "engine 35: 3")
check(D._state_of(25, 100, ENGINE) == 3, "radiator-like 25: 3")
check(D._state_of(4, 100, ENGINE) == 4, "engine 4: 4")
check(D._state_of(40, 100, BODY) == 2, "bodywork 40: 2")
check(D._state_of(60, 100, BODY) == 2, "60: 2")
check(D._state_of(100, 100, ENGINE) == 0, "intact: 0")
check(D._state_of(99.6, 100, ENGINE) == 0, "99.6: 0")
check(D._state_of(98, 100, ENGINE) == 1, "98: 1")
print("ok")
