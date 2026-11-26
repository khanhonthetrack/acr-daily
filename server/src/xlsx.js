// A small .xlsx writer and reader for the event sheets (src/eventsheet.js): no library, so the Worker stays as it is.
// The writer makes what the template needs: sheets of text and numbers, a few styles (header colours, text format so
// Excel leaves "09:00" and "2026-12-05 18:00" alone), column widths, a frozen header row and DROP-DOWN LISTS (data
// validation) over cell ranges. The reader takes any .xlsx Excel, LibreOffice, Google Sheets or openpyxl saved: the
// sheet's cells as rows of text (dates and times Excel stored as numbers come back as "2026-12-05 18:00" / "09:30").
// A .xlsx is a zip of XML files; the writer stores them uncompressed, the reader also inflates (DecompressionStream,
// in the Workers runtime and Node alike).

const enc = new TextEncoder();
const dec = new TextDecoder('utf-8');

// ------------------------------------------------------------------ zip

const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
export function crc32(bytes) {
  let c = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** files: [{name, data: string | Uint8Array}] -> a zip (stored, not compressed) as a Uint8Array. */
export function zipStore(files) {
  const parts = [], central = [];
  let offset = 0;
  const DOS_DATE = ((2026 - 1980) << 9) | (1 << 5) | 1;       // (a fixed stamp: the same bytes for the same sheet)
  for (const f of files) {
    const name = enc.encode(f.name);
    const data = typeof f.data === 'string' ? enc.encode(f.data) : f.data;
    const crc = crc32(data);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true); local.setUint16(4, 20, true); local.setUint16(6, 0x0800, true);
    local.setUint16(8, 0, true); local.setUint16(10, 0, true); local.setUint16(12, DOS_DATE, true);
    local.setUint32(14, crc, true); local.setUint32(18, data.length, true); local.setUint32(22, data.length, true);
    local.setUint16(26, name.length, true); local.setUint16(28, 0, true);
    parts.push(new Uint8Array(local.buffer), name, data);
    const cd = new DataView(new ArrayBuffer(46));
    cd.setUint32(0, 0x02014b50, true); cd.setUint16(4, 20, true); cd.setUint16(6, 20, true); cd.setUint16(8, 0x0800, true);
    cd.setUint16(10, 0, true); cd.setUint16(12, 0, true); cd.setUint16(14, DOS_DATE, true);
    cd.setUint32(16, crc, true); cd.setUint32(20, data.length, true); cd.setUint32(24, data.length, true);
    cd.setUint16(28, name.length, true); cd.setUint32(42, offset, true);
    central.push(new Uint8Array(cd.buffer), name);
    offset += 30 + name.length + data.length;
  }
  const size = central.reduce((a, p) => a + p.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
  end.setUint32(12, size, true); end.setUint32(16, offset, true);
  const all = [...parts, ...central, new Uint8Array(end.buffer)];
  const out = new Uint8Array(all.reduce((a, p) => a + p.length, 0));
  let at = 0;
  for (const p of all) { out.set(p, at); at += p.length; }
  return out;
}

export const MAX_UNZIPPED = 12 * 1024 * 1024;      // a sheet is a few hundred KB: more is not one (a zip bomb)

async function inflate(data) {
  const s = new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
  const buf = new Uint8Array(await new Response(s).arrayBuffer());
  if (buf.length > MAX_UNZIPPED) throw new Error('the file is too big to be a sheet');
  return buf;
}

/** A zip's files, by name: {name: Uint8Array}. Reads the central directory (stored and deflated entries). */
export async function unzip(bytes) {
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let e = bytes.length - 22;
  while (e >= 0 && v.getUint32(e, true) !== 0x06054b50) e--;
  if (e < 0) throw new Error('not a zip file');
  const n = v.getUint16(e + 10, true);
  let p = v.getUint32(e + 16, true), total = 0;
  const out = {};
  for (let i = 0; i < n; i++) {
    if (p + 46 > bytes.length || v.getUint32(p, true) !== 0x02014b50) throw new Error('damaged zip file');
    const method = v.getUint16(p + 10, true), csize = v.getUint32(p + 20, true), usize = v.getUint32(p + 24, true);
    const nl = v.getUint16(p + 28, true), xl = v.getUint16(p + 30, true), cl = v.getUint16(p + 32, true), lo = v.getUint32(p + 42, true);
    const name = dec.decode(bytes.subarray(p + 46, p + 46 + nl));
    p += 46 + nl + xl + cl;
    total += usize;
    if (total > MAX_UNZIPPED) throw new Error('the file is too big to be a sheet');
    if (!/\.(xml|rels)$/.test(name)) continue;                         // (only the XML parts are read)
    const ln = v.getUint16(lo + 26, true), lx = v.getUint16(lo + 28, true);
    const raw = bytes.subarray(lo + 30 + ln + lx, lo + 30 + ln + lx + csize);
    out[name] = method === 0 ? raw : method === 8 ? await inflate(raw) : null;
  }
  return out;
}

// ------------------------------------------------------------------ writing

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, '');
const colName = (i) => { let s = ''; for (i++; i > 0; i = Math.floor((i - 1) / 26)) s = String.fromCharCode(65 + ((i - 1) % 26)) + s; return s; };

/** The styles a sheet's cells and columns use by name (an index into cellXfs below). */
export const STYLE = { plain: 0, headRequired: 1, headOptional: 2, text: 3, wrap: 4, bold: 5, headList: 6, title: 7, muted: 8 };

const STYLES_XML = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="5">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="16"/><name val="Calibri"/></font>
<font><i/><sz val="11"/><color rgb="FF666666"/><name val="Calibri"/></font>
</fonts>
<fills count="5">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFC8102E"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF4A4F57"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE7E9EC"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="9">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="4" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;

function cellXml(ref, c) {
  const o = c !== null && typeof c === 'object' ? c : { v: c };
  const s = o.s ? ` s="${o.s}"` : '';
  if (o.v === null || o.v === undefined || o.v === '') return o.s ? `<c r="${ref}"${s}/>` : '';
  if (typeof o.v === 'number') return `<c r="${ref}"${s}><v>${o.v}</v></c>`;
  return `<c r="${ref}"${s} t="inlineStr"><is><t xml:space="preserve">${esc(o.v)}</t></is></c>`;
}

function sheetXml(sh, active) {
  const rows = sh.rows.map((r, i) => {
    const cells = r.map((c, j) => cellXml(colName(j) + (i + 1), c)).join('');
    const h = sh.heights && sh.heights[i] ? ` ht="${sh.heights[i]}" customHeight="1"` : '';
    return cells || h ? `<row r="${i + 1}"${h}>${cells}</row>` : '';
  }).join('');
  const cols = (sh.cols || []).map((c, i) => `<col min="${i + 1}" max="${i + 1}" width="${c.width || 12}" customWidth="1"${c.style ? ` style="${c.style}"` : ''}/>`).join('');
  const pane = sh.freeze ? `<pane ${sh.freeze.cols ? `xSplit="${sh.freeze.cols}" ` : ''}ySplit="${sh.freeze.rows}" topLeftCell="${colName(sh.freeze.cols || 0)}${sh.freeze.rows + 1}" activePane="${sh.freeze.cols ? 'bottomRight' : 'bottomLeft'}" state="frozen"/>` : '';
  const merges = (sh.merges || []).length ? `<mergeCells count="${sh.merges.length}">${sh.merges.map((m) => `<mergeCell ref="${m}"/>`).join('')}</mergeCells>` : '';
  const dv = (sh.validations || []).map((v) => {
    const attrs = [v.type ? `type="${v.type}"` : '', v.op ? `operator="${v.op}"` : '', 'allowBlank="1"', 'showInputMessage="1"', 'showErrorMessage="1"',
      v.warn ? 'errorStyle="warning"' : '', v.title ? `promptTitle="${esc(v.title.slice(0, 32))}"` : '', v.prompt ? `prompt="${esc(v.prompt.slice(0, 255))}"` : '',
      v.errorTitle ? `errorTitle="${esc(v.errorTitle.slice(0, 32))}"` : '', v.error ? `error="${esc(v.error.slice(0, 255))}"` : '',
      `sqref="${v.sqref}"`].filter(Boolean).join(' ');
    return `<dataValidation ${attrs}>${v.f1 ? `<formula1>${esc(v.f1)}</formula1>` : ''}${v.f2 ? `<formula2>${esc(v.f2)}</formula2>` : ''}</dataValidation>`;
  }).join('');
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetViews><sheetView workbookViewId="0"${active ? ' tabSelected="1"' : ''}${sh.noGrid ? ' showGridLines="0"' : ''}>${pane}</sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="15"/>${cols ? `<cols>${cols}</cols>` : ''}<sheetData>${rows}</sheetData>${merges}${dv ? `<dataValidations count="${(sh.validations || []).length}">${dv}</dataValidations>` : ''}
<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>
</worksheet>`;
}

/** sheets: [{name, rows: [[cell]], cols: [{width, style}], heights: {rowIndex: points}, freeze: {rows, cols}, noGrid,
 *  merges: ['A3:B3'], validations: [{sqref, type: 'list' | 'whole' | none, f1, f2, op, warn, title, prompt, errorTitle,
 *  error}]}]; a cell is a
 *  string, a number or {v, s: STYLE.x}. The first sheet is the one open when the file is. -> the .xlsx as a Uint8Array. */
export function xlsxWrite(sheets) {
  const n = sheets.length;
  const files = [
    { name: '[Content_Types].xml', data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>${sheets.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('')}<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>` },
    { name: '_rels/.rels', data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>` },
    { name: 'xl/workbook.xml', data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView activeTab="0"/></bookViews><sheets>${sheets.map((s, i) => `<sheet name="${esc(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('')}</sheets></workbook>` },
    { name: 'xl/_rels/workbook.xml.rels', data: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${sheets.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('')}<Relationship Id="rId${n + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>` },
    { name: 'xl/styles.xml', data: STYLES_XML },
    ...sheets.map((s, i) => ({ name: `xl/worksheets/sheet${i + 1}.xml`, data: sheetXml(s, i === 0) })),
  ];
  return zipStore(files);
}

// ------------------------------------------------------------------ reading

const unesc = (s) => s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (m, e) => {
  if (e[0] === '#') {
    const cp = e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
    return cp > 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : '';
  }
  return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }[e.toLowerCase()];
});
// (_x000D_ and its like: characters Excel escapes in text)
const unx = (s) => s.replace(/_x([0-9A-Fa-f]{4})_/g, (m, h) => String.fromCharCode(parseInt(h, 16)));
const textOf = (xml) => {
  const out = [];
  for (const m of xml.replace(/<rPh\b[\s\S]*?<\/rPh>/g, '').matchAll(/<t\b[^>]*?(?:\/>|>([\s\S]*?)<\/t>)/g)) out.push(m[1] || '');
  return unx(unesc(out.join('')));
};
const attr = (s, name) => { const m = new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(s); return m ? unesc(m[1]) : null; };
const colIndex = (ref) => { let n = 0; for (const ch of /^[A-Z]+/.exec(ref)[0]) n = n * 26 + ch.charCodeAt(0) - 64; return n - 1; };

const BUILTIN_DATE = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 45, 46, 47, 50, 51, 52, 53, 54, 55, 56, 57, 58]);
function dateStyles(styles) {
  const custom = new Map();
  for (const m of (styles.match(/<numFmt\b[^>]*>/g) || [])) custom.set(attr(m, 'numFmtId'), attr(m, 'formatCode') || '');
  const cellXfs = /<cellXfs\b[^>]*>([\s\S]*?)<\/cellXfs>/.exec(styles);
  const out = [];
  for (const m of (cellXfs ? cellXfs[1].match(/<xf\b[^>]*?(?:\/>|>)/g) || [] : [])) {
    const id = attr(m, 'numFmtId');
    const code = (custom.get(id) || '').replace(/"[^"]*"|\\.|\[[^\]]*\]/g, '');
    out.push(BUILTIN_DATE.has(+id) || (custom.has(id) && /[ymdhs]/i.test(code) && !/^general$/i.test(code)));
  }
  return out;
}
const p2 = (n) => String(n).padStart(2, '0');
/** An Excel date/time serial -> "2026-12-05 18:00", "2026-12-05" or "09:30" (a time of day alone). */
export function serialText(x) {
  const mins = Math.round(x * 1440);
  const days = Math.floor(mins / 1440), rest = mins - days * 1440;
  const time = `${p2(Math.floor(rest / 60))}:${p2(rest % 60)}`;
  if (x < 1) return time;
  const d = new Date(Date.UTC(1899, 11, 30) + days * 86400000);
  const date = `${d.getUTCFullYear()}-${p2(d.getUTCMonth() + 1)}-${p2(d.getUTCDate())}`;
  return rest ? `${date} ${time}` : date;
}
const numText = (v) => { const x = Number(v); return Number.isFinite(x) ? (Number.isInteger(x) ? String(x) : String(+x.toPrecision(12))) : String(v); };

/** The cells of an .xlsx's sheet (the one named `want`, else the first) as rows of text. A row with nothing in it comes
 *  back as []. -> {rows: string[][], sheet: its name, sheets: all names} */
export async function xlsxRead(bytes, want = 'Events') {
  const files = await unzip(bytes);
  const get = (n) => (files[n] ? dec.decode(files[n]) : '');
  const wb = get('xl/workbook.xml'), rels = get('xl/_rels/workbook.xml.rels');
  if (!wb) throw new Error('not an Excel workbook');
  const target = new Map();
  for (const m of rels.match(/<Relationship\b[^>]*>/g) || []) target.set(attr(m, 'Id'), attr(m, 'Target'));
  const sheets = (wb.match(/<sheet\b[^>]*>/g) || []).map((m) => {
    const t = target.get(attr(m, 'r:id') || attr(m, 'id'));
    return { name: attr(m, 'name'), path: t ? (t.startsWith('/') ? t.slice(1) : `xl/${t}`) : null, hidden: attr(m, 'state') === 'hidden' };
  }).filter((s) => s.path);
  const pick = sheets.find((s) => s.name.toLowerCase() === String(want).toLowerCase()) || sheets.find((s) => !s.hidden) || sheets[0];
  if (!pick || !files[pick.path]) throw new Error('the workbook has no sheet');
  const shared = [];
  for (const m of get('xl/sharedStrings.xml').matchAll(/<si\b[^>]*?(?:\/>|>([\s\S]*?)<\/si>)/g)) shared.push(textOf(m[1] || ''));
  const isDate = dateStyles(get('xl/styles.xml'));
  const xml = dec.decode(files[pick.path]);
  const rows = [];
  for (const rm of xml.matchAll(/<row\b([^>]*?)(?:\/>|>([\s\S]*?)<\/row>)/g)) {
    const rn = (+attr(rm[1], 'r') || rows.length + 1) - 1;
    if (rn > 20000) break;
    const cells = [];
    for (const cm of (rm[2] || '').matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
      const ref = attr(cm[1], 'r');
      const j = ref ? colIndex(ref) : cells.length;
      if (j > 200) continue;
      const t = attr(cm[1], 't'), inner = cm[2] || '';
      const v = (/<v\b[^>]*>([\s\S]*?)<\/v>/.exec(inner) || [])[1];
      let val = '';
      if (t === 'inlineStr') val = textOf(inner);
      else if (v === undefined) val = '';
      else if (t === 's') val = shared[+v] === undefined ? '' : shared[+v];
      else if (t === 'str') val = unx(unesc(v));
      else if (t === 'b') val = v === '1' ? 'TRUE' : 'FALSE';
      else if (t === 'e') val = '';
      else val = isDate[+attr(cm[1], 's') || 0] && Number.isFinite(+v) ? serialText(+v) : numText(unesc(v));
      cells[j] = val;
    }
    rows[rn] = Array.from(cells, (x) => x === undefined ? '' : x);
  }
  return { rows: Array.from(rows, (r) => r || []), sheet: pick.name, sheets: sheets.map((s) => s.name) };
}
