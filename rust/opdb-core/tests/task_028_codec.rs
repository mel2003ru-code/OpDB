use opdb_core::{decode_ops, encode_ops, Op};

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545F4914F6CDD1D)
    }
    fn bytes(&mut self, max: usize) -> Vec<u8> {
        let n = (self.next() as usize) % (max + 1);
        (0..n).map(|_| self.next() as u8).collect()
    }
}

#[test]
fn exact_layout() {
    let put = encode_ops(&[Op::Put(b"k".to_vec(), b"vv".to_vec())]);
    assert_eq!(
        put,
        vec![1, 1, 0, 0, 0, 2, 0, 0, 0, b'k', b'v', b'v']
    );
    let del = encode_ops(&[Op::Delete(b"k".to_vec())]);
    assert_eq!(del, vec![2, 1, 0, 0, 0, 0, 0, 0, 0, b'k']);
    assert_eq!(encode_ops(&[]), Vec::new());
}

#[test]
fn empty_decodes_to_empty() {
    assert_eq!(decode_ops(&[]), Some(vec![]));
}

#[test]
fn round_trip_random_batches() {
    for seed in 1..=30u64 {
        let mut rng = Rng(seed.wrapping_mul(0x9E3779B97F4A7C15) | 1);
        for _ in 0..50 {
            let count = (rng.next() as usize) % 9;
            let mut ops = Vec::new();
            for _ in 0..count {
                let key = rng.bytes(12);
                if rng.next() % 2 == 0 {
                    let value = rng.bytes(40);
                    ops.push(Op::Put(key, value));
                } else {
                    ops.push(Op::Delete(key));
                }
            }
            assert_eq!(
                decode_ops(&encode_ops(&ops)),
                Some(ops.clone()),
                "seed {seed}"
            );
        }
    }
}

#[test]
fn binary_and_large() {
    let all: Vec<u8> = (0..=255u8).collect();
    let big = vec![0xABu8; 1 << 20];
    let ops = vec![
        Op::Put(all.clone(), big.clone()),
        Op::Put(Vec::new(), b"empty-key".to_vec()),
        Op::Put(b"empty-value".to_vec(), Vec::new()),
        Op::Delete(Vec::new()),
    ];
    let encoded = encode_ops(&ops);
    assert_eq!(decode_ops(&encoded), Some(ops.clone()));
}

#[test]
fn cut_prefixes_are_rejected() {
    let put = encode_ops(&[Op::Put(b"k".to_vec(), b"vv".to_vec())]);
    for cut in 1..put.len() {
        assert_eq!(decode_ops(&put[..cut]), None, "cut {cut}");
    }
    let two = encode_ops(&[
        Op::Put(b"a".to_vec(), b"1".to_vec()),
        Op::Put(b"b".to_vec(), b"2".to_vec()),
    ]);
    let first_end = 1 + 4 + 4 + 1 + 1;
    for cut in first_end + 1..two.len() {
        assert_eq!(decode_ops(&two[..cut]), None, "cut {cut}");
    }
}

#[test]
fn malformed_inputs_give_none() {
    assert_eq!(decode_ops(&[3, 0, 0, 0, 0, 0, 0, 0, 0]), None);
    assert_eq!(
        decode_ops(&[2, 1, 0, 0, 0, 1, 0, 0, 0, b'k', b'v']),
        None
    );
    assert_eq!(decode_ops(&[1, 255, 255, 255, 255, 255, 255, 255, 255]), None);
    let valid = encode_ops(&[Op::Put(b"k".to_vec(), b"v".to_vec())]);
    let mut stray = valid.clone();
    stray.push(0xFF);
    assert_eq!(decode_ops(&stray), None);
    assert_eq!(decode_ops(&valid), Some(vec![Op::Put(b"k".to_vec(), b"v".to_vec())]));
}
