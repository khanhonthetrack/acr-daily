// Bad language in comments (src/wordfilter.js): swearing and slurs refused in every language the site has, ordinary
// words of any of them let through (an entry applies to every comment: its language isn't known).
import test from 'node:test';
import assert from 'node:assert/strict';
import { badWord } from '../src/wordfilter.js';

test('swearing and slurs, in the site\'s languages and their usual disguises', () => {
  for (const s of ['what a fucking stage', 'sh1t gearbox', '$hit', 'fuuuuck this', 'ASSHOLE', 'bullshit split',
    'kurwa mać', 'ja pierdolę ten zakręt', 'bazdmeg', 'kibaszott köd', 'Scheiße Kurve', 'du Hurensohn', 'fick dich',
    'putain de virage', 'connard', 'me cago en la puta', 'qué coño', 'gilipollas', 'vaffanculo', 'porco dio', 'que porra',
    'caralho', '死ねよ', 'ｶﾞｲｼﾞ', '傻逼', '他妈的什么', 'kill yourself', 'dick move', 'nigga', 'faggot']) {
    assert.ok(badWord(s), s);
  }
});

test('ordinary words of any of the languages, and car talk, pass', () => {
  for (const s of ['Great stage, lost time at the hairpin', 'spark retard on that engine', 'Wankel engine', 'a niggle with the brakes',
    'pedał gazu się zaciął', 'szárny letört', 'el cono de tráfico', 'pintura negro mate', 'vergangene Woche', 'that fickle grip',
    'shiitake', 'Scunthorpe', 'fodder', 'basszus', 'cazzuola', 'putative', '操作很难', 'カスタム設定', 'assist', 'class win',
    'Dickson corner', 'cocktail', 'cockpit', 'damn crap hell', 'くそ難しい', 'SS1 R5 i20 lost 0.5s!', 'analysis', 'passed',
    'the bite point', 'cumulative', 'f*ck this stage', '', null]) {
    assert.equal(badWord(s), null, s);
  }
});
