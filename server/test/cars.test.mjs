// The car ids DRIVE writes into the game's save must be rows of the game's own car table, or the game crashes when
// the stage loads (2026-10-06: "AlfaRomeoGiuliaGTAJunior1300" instead of "AlfaRomeoGTA1300").
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CARS, carByName } from '../src/cars.js';

// row names of acr/Content/Data/Database/Main/CarSelection/DT_Cars (game files, 2026-10-06; the game's 0.7, 2026-11-19:
// the two Delta S4s)
const GAME_CARS = ['AlfaRomeoGTA1300', 'HyundaiI20NRally2', 'MiniCooperS1275', 'CitroenXsaraWRC', 'Fiat131Abarth',
  'Fiat124Abarth', 'LanciaDeltaIntegraleEvo', 'LanciaRally037Evo2', 'Peugeot208Rally4', 'LanciaStratosHF', 'AlpineA110',
  'LanciaFulviaHF', 'SkodaFabiaRSRally2', 'SubaruImprezaS3', 'Peugeot306IIMaxiKitCar', 'AudiQuattroGr4', 'Peugeot206',
  'VWPoloGTIR5', 'LanciaDeltaS4', 'LanciaDeltaS4Evo2'];

test('every car id is a row of the game\'s car table, and every row is a car', () => {
  assert.deepEqual(CARS.map((c) => c.id).sort(), [...GAME_CARS].sort());
});

test('schedules made with the old names still find their car', () => {
  assert.equal(carByName('Alfa Romeo Giulia GTA Junior 1300').id, 'AlfaRomeoGTA1300');
  assert.equal(carByName('Peugeot 206 WRC').id, 'Peugeot206');
});

test('the names the game reports match their car (and no other)', async () => {
  const { sameCar } = await import('../src/cars.js');
  // (the game's 0.7 reports both Delta S4s as "Lancia Delta S4": the Evo2 answers to it too, the save tells them apart)
  const shared = (a, b) => a.telemetry === 'Lancia Delta S4' && b.id === 'LanciaDeltaS4Evo2';
  for (const c of CARS) {
    assert.ok(sameCar(c.telemetry, c), c.telemetry);
    for (const o of CARS) if (o !== c && !shared(c, o)) assert.ok(!sameCar(c.telemetry, o), c.telemetry + ' matched ' + o.id);
  }
  assert.equal(carByName('Lancia Delta S4').id, 'LanciaDeltaS4');
  assert.ok(sameCar('Lancia Delta S4', CARS.find((c) => c.id === 'LanciaDeltaS4Evo2')));
});
