// Bad language in what drivers write for others to read (src/comments.js): swearing and slurs, in English and in the
// site's languages (Polish, Hungarian, Japanese, German, French, Spanish, Italian, Portuguese, Chinese). A comment
// with one is refused when sent ("say it another way"); everything else stays the site's admin's to take down.
//
// A comment's language isn't known, so every list applies to every comment: an entry must not be an ordinary word in
// any of them. Left out for that reason: Polish "pedał" (a car's pedal), English "tranny" (a gearbox), "retard"
// (ignition timing), French "bite" (English "bite"), Spanish "cono" (a cone), "negro", Chinese 操 alone (操作),
// Japanese カス (カスタム); only as whole words: "wank" (Wankel), Hungarian "szar" (szárny, a wing), German "fick"
// (fickle), Spanish "verga" (vergangen). Mild words (damn, crap, hell, くそ) are fine.
//
// How a word is matched: the text in lower case, accents dropped (ą, é, ő; ß as ss, ł as l; ñ kept: coño is not
// cono), the usual stand-ins read as letters (sh1t, @ss, $hit), and a letter of an entry drawn out (fuuuck).
// Latin-script entries are matched where a word starts: PREFIX entries with anything after them (fucking,
// kurwa mać), WORD entries as the whole word only. Japanese and Chinese ones anywhere in the text (no spaces there).

/** English, and the words every language borrows. */
const EN_PREFIX = ['fuck', 'motherfuck', 'mothafuck', 'shit', 'bullshit', 'cunt', 'bitch', 'asshole', 'arsehole',
  'dickhead', 'whore', 'slut', 'faggot', 'twat'];
const EN_WORD = ['dick', 'dicks', 'cock', 'cocks', 'pussy', 'pussies', 'fag', 'fags', 'wank', 'wanker', 'wankers',
  'wanking', 'nigger', 'niggers', 'nigga', 'niggas', 'niggaz', 'kike', 'kikes', 'spic', 'spics', 'wetback', 'rape',
  'raped', 'rapist', 'kys', 'stfu'];
const PHRASES = ['kill yourself', 'kill urself', 'sieg heil', 'heil hitler'];

const PREFIX = {
  pl: ['kurw', 'chuj', 'huj', 'pierdol', 'spierdal', 'wypierdal', 'odpierdal', 'zajeb', 'jeban', 'jebac', 'jebie',
    'jebni', 'pizd', 'skurwysyn', 'skurwiel', 'cwel', 'ciota', 'dziwk', 'kutas'],
  hu: ['kurva', 'basz', 'kibasz', 'megbasz', 'elbasz', 'bazd', 'bazm', 'fasz', 'geci', 'picsa', 'buzi'],
  de: ['ficken', 'ficker', 'gefickt', 'verfickt', 'fotze', 'hurensohn', 'hure', 'wichser', 'arschloch', 'scheiss', 'schwuchtel', 'missgeburt', 'spast',
    'kanake'],
  fr: ['putain', 'pute', 'encul', 'salope', 'connard', 'connasse', 'niqu', 'merde', 'batard', 'bougnoul'],
  es: ['puta', 'puto', 'cabron', 'gilipoll', 'joder', 'jodid', 'jodete', 'coño', 'mierda', 'maricon', 'pendejo',
    'chinga', 'culero'],
  it: ['cazzo', 'cazzi', 'cazzat', 'incazz', 'vaffancul', 'fancul', 'stronz', 'merd', 'puttan', 'troia', 'coglion', 'minchia', 'froci', 'frocio',
    'ricchion', 'porcodio', 'diocane', 'mignott'],
  pt: ['porra', 'caralh', 'foda', 'foder', 'fodid', 'fodas', 'buceta', 'viado', 'arrombad', 'cuzao'],
};
const WORD = {
  pl: ['cipa', 'cipy'],
  hu: ['szar', 'szaros', 'szarsag'],
  de: ['fick', 'fickt', 'fickst', 'neger'],
  fr: ['pede', 'pedes', 'negre', 'negres', 'fdp', 'ntm'],
  es: ['marica', 'maricas', 'sudaca', 'sudacas', 'verga', 'vergas'],
  it: ['porco dio', 'dio cane'],
  pt: [],
};
/** Japanese and Chinese: anywhere in the text. */
const CJK = [
  '死ね', 'ぶっ殺', 'ちんこ', 'ちんぽ', 'まんこ', 'ファック', 'クソ野郎', 'くそ野郎', 'くそやろう', 'キチガイ', 'きちがい', '気違い',
  'ガイジ', 'レイプ',
  '操你', '肏', '傻逼', '煞笔', '鸡巴', '婊子', '他妈的', '你妈的', '去你妈', '日你妈', '王八蛋', '狗日', '草泥马', '贱人', '屌',
];
/** Ordinary words an entry starts (the letters' repeats read as one): let through. */
const ALLOW = ['shiitake', 'shitake', 'putative', 'putatively'];

const LEET = { 0: 'o', 1: 'i', 3: 'e', 4: 'a', 5: 's', 7: 't', '@': 'a', $: 's', '!': 'i' };

const isLetter = (c) => !!c && /\p{L}/u.test(c);
/** The text as Latin-script entries are matched: lower case, accents dropped (ñ kept), ß / ł / ø / æ / œ spelt out,
 *  stand-ins next to a letter read as letters (sh1t, $hit; '!' only between two: "run!" stays). */
export function plain(s) {
  return String(s == null ? '' : s).toLowerCase()
    .replace(/ñ/g, '\u0000')
    .normalize('NFKD').replace(/\p{M}+/gu, '')
    .replace(/\u0000/g, 'ñ')
    .replace(/ß/g, 'ss').replace(/ł/g, 'l').replace(/ø/g, 'o').replace(/æ/g, 'ae').replace(/œ/g, 'oe').replace(/đ/g, 'd')
    .replace(/[013457@$!]/g, (c, i, str) => {
      const before = isLetter(str[i - 1]), after = isLetter(str[i + 1]);
      return (c === '!' ? before && after : before || after) ? LEET[c] : c;
    });
}

const esc = (c) => c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
/** An entry as a pattern: a letter once in it matches once, or three times and more (fuuuck; never twice, which is
 *  how ordinary words spell it: fodder is not foder); a letter twice or more, that many or more; a space, any run of
 *  non-letters. */
const pattern = (w) => (plain(w).match(/(.)\1*/gu) || []).map((run) => {
  const c = run[0];
  if (c === ' ') return '[^\\p{L}]+';
  return run.length === 1 ? `${esc(c)}(?:${esc(c)}{2,})?` : `${esc(c)}{${run.length},}`;
}).join('');

const LATIN_PREFIX = [...EN_PREFIX, ...Object.values(PREFIX).flat()];
const LATIN_WORD = [...EN_WORD, ...PHRASES, ...Object.values(WORD).flat()];
const LATIN_RE = new RegExp(
  `(?<!\\p{L})(?:(?:${LATIN_PREFIX.map(pattern).join('|')})|(?:${LATIN_WORD.map(pattern).join('|')})(?!\\p{L}))`, 'u');
const ALLOW_RE = new RegExp(`(?<!\\p{L})(?:${ALLOW.map(pattern).join('|')})(?!\\p{L})`, 'gu');
const CJK_RE = new RegExp(CJK.map(esc).join('|'), 'u');     // (on the text as NFKC: half-width kana made whole)

/** The first bad word in s (as matched, for the tests and the log), or null. */
export function badWord(s) {
  const m = LATIN_RE.exec(plain(s).replace(ALLOW_RE, ' ')) || CJK_RE.exec(String(s == null ? '' : s).normalize('NFKC'));
  return m ? m[0] : null;
}
