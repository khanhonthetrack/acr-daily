// Every drivable car in Assetto Corsa Rally. id = the car's row in the game's own car table
// (acr/Content/Data/Database/Main/CarSelection/DT_Cars): what DRIVE writes into the save - a wrong one crashes the
// game when the stage loads. The game's internal names; the name the game reports is the id with spaces (checked: "Mini Cooper S 1275",
// "Peugeot 208 Rally4"). The other names are best guesses: matching is lenient (see sameCar) so small
// differences still match, and `aliases` can be extended once the game reports a different spelling.

export const CARS = [
  { id: 'AlfaRomeoGTA1300', name: 'Alfa Romeo Giulia GTA Junior 1300', cls: 'H3', group: 'Group 2/4', aliases: ['Alfa Romeo GTA 1300 Junior', 'AlfaRomeoGiuliaGTAJunior1300'] },
  { id: 'MiniCooperS1275', name: 'Mini Cooper S 1275', cls: 'H3', group: 'Group 2/4', aliases: ['Mini Cooper S'] },
  { id: 'AlpineA110', name: 'Alpine A110 1800', cls: 'H2', group: 'Group 2/4', aliases: ['Alpine A110 1.8', 'AlpineA1101800'] },
  { id: 'AudiQuattroGr4', name: 'Audi Quattro Gr4', cls: 'H1', group: 'Group 2/4', aliases: ['Audi Quattro Gr.4'] },
  { id: 'Fiat124Abarth', name: 'Fiat 124 Abarth', cls: 'H2', group: 'Group 2/4', aliases: ['Fiat 124 Abarth Rally 16V'] },
  { id: 'Fiat131Abarth', name: 'Fiat 131 Abarth', cls: 'H1', group: 'Group 2/4' },
  { id: 'LanciaFulviaHF', name: 'Lancia Fulvia Coupe HF', cls: 'H3', group: 'Group 2/4', aliases: ['Lancia Fulvia Coupé HF', 'LanciaFulviaCoupeHF'] },
  { id: 'LanciaStratosHF', name: 'Lancia Stratos HF', cls: 'H1', group: 'Group 2/4' },
  { id: 'LanciaRally037Evo2', name: 'Lancia Rally 037 Evo2', cls: 'B2', group: 'Group B', aliases: ['Lancia Rally 037 Evoluzione 2'] },
  { id: 'LanciaDeltaIntegraleEvo', name: 'Lancia Delta HF Integrale Evo', cls: 'A8 EVO2', group: 'Group A', aliases: ['Lancia Delta Integrale Evo', 'Lancia Delta Integrale Evoluzione', 'LanciaDeltaHFIntegraleEvo'] },
  { id: 'SubaruImprezaS3', name: 'Subaru Impreza S3', cls: 'A8 EVO3', group: 'Group A' },
  { id: 'Peugeot306IIMaxiKitCar', name: 'Peugeot 306 Maxi', cls: 'K11', group: 'Group A', aliases: ['Peugeot 306 II Maxi', 'Peugeot306IIMaxi'] },
  { id: 'Peugeot206', name: 'Peugeot 206 WRC', cls: 'WR EVO1', group: 'Group WR', aliases: ['Peugeot206WRC'] },
  { id: 'CitroenXsaraWRC', name: 'Citroen Xsara WRC', cls: 'WR EVO2', group: 'Group WR' },
  { id: 'VWPoloGTIR5', name: 'VW Polo GTI R5', cls: 'Rally2/R5', group: 'Group R', aliases: ['Volkswagen Polo GTI R5'] },
  { id: 'HyundaiI20NRally2', name: 'Hyundai i20 N Rally2', cls: 'Rally2/R5', group: 'Group R', aliases: ['Hyundai i20 Rally2'] },
  { id: 'SkodaFabiaRSRally2', name: 'Skoda Fabia RS Rally2', cls: 'Rally2/R5', group: 'Group R', aliases: ['Škoda Fabia RS Rally2'] },
  { id: 'Peugeot208Rally4', name: 'Peugeot 208 Rally4', cls: 'Rally4', group: 'Group R' },
];

const norm = (s) => String(s || '').toLowerCase().normalize('NFD').replace(/[^a-z0-9]/g, '');
const digits = (s) => norm(s).replace(/[^0-9]/g, '');

// similarity of two normalised names (0..1), same idea as Python's difflib ratio
function ratio(a, b) {
  if (!a.length && !b.length) return 1;
  const m = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) {
    m[i][j] = a[i - 1] === b[j - 1] ? m[i - 1][j - 1] + 1 : Math.max(m[i - 1][j], m[i][j - 1]);
  }
  return (2 * m[a.length][b.length]) / (a.length + b.length);
}

/** Does the car name the game reports match this car? Same model numbers and nearly the same letters. */
export function sameCar(reported, car) {
  const r = norm(reported);
  if (!r || !car) return false;
  const names = [car.id, car.name, ...(car.aliases || [])];
  if (names.some((n) => norm(n) === r)) return true;
  return names.some((n) => digits(n) === digits(reported) && ratio(norm(n), r) >= 0.85);
}

export const carByName = (name) => CARS.find((c) => c.name === name || c.id === name || sameCar(name, c)) || null;
