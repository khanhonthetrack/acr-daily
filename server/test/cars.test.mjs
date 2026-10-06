// The car ids DRIVE writes into the game's save must be rows of the game's own car table, or the game crashes when
// the stage loads (2026-10-06: "AlfaRomeoGiuliaGTAJunior1300" instead of "AlfaRomeoGTA1300").
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { CARS, carByName } from '../src/cars.js';

// row names of acr/Content/Data/Database/Main/CarSelection/DT_Cars (game files, 2026-10-06)
const GAME_CARS = ['AlfaRomeoGTA1300', 'HyundaiI20NRally2', 'MiniCooperS1275', 'CitroenXsaraWRC', 'Fiat131Abarth',
  'Fiat124Abarth', 'LanciaDeltaIntegraleEvo', 'LanciaRally037Evo2', 'Peugeot208Rally4', 'LanciaStratosHF', 'AlpineA110',
  'LanciaFulviaHF', 'SkodaFabiaRSRally2', 'SubaruImprezaS3', 'Peugeot306IIMaxiKitCar', 'AudiQuattroGr4', 'Peugeot206',
  'VWPoloGTIR5'];

test('every car id is a row of the game\'s car table, and every row is a car', () => {
  assert.deepEqual(CARS.map((c) => c.id).sort(), [...GAME_CARS].sort());
});

test('schedules made with the old names still find their car', () => {
  assert.equal(carByName('Alfa Romeo Giulia GTA Junior 1300').id, 'AlfaRomeoGTA1300');
  assert.equal(carByName('Peugeot 206 WRC').id, 'Peugeot206');
});
