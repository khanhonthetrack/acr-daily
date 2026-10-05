// decomp <ucas> <out>  ; stdin: lines "offset csize usize method" (method 0 = stored), output = concatenation
use std::io::{BufRead, Read, Seek, SeekFrom, Write};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut ucas = std::fs::File::open(&args[1]).expect("open ucas");
    let mut out = std::fs::File::create(&args[2]).expect("create out");
    let mut ex = oozextract::Extractor::new();
    for line in std::io::stdin().lock().lines() {
        let line = line.expect("line");
        let v: Vec<u64> = line.split_whitespace().map(|x| x.parse().expect("num")).collect();
        if v.len() < 4 {
            continue;
        }
        let (off, csize, usize_, method) = (v[0], v[1] as usize, v[2] as usize, v[3]);
        let mut inp = vec![0u8; csize];
        ucas.seek(SeekFrom::Start(off)).expect("seek");
        ucas.read_exact(&mut inp).expect("read");
        if method == 0 {
            out.write_all(&inp[..usize_.min(csize)]).expect("write");
        } else {
            let mut buf = vec![0u8; usize_];
            let n = ex.read_from_slice(&inp, &mut buf).expect("oodle");
            out.write_all(&buf[..n]).expect("write");
        }
    }
}
