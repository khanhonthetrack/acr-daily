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
print("ok")
