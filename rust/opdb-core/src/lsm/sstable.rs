//! Experimental immutable SSTable writer (L06). Each block and index has a CRC.
use crate::{crc32, Error, Result};
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

const BLOCK_TARGET: usize = 4096;
const MAGIC: &[u8; 8] = b"OPDBSST\0";

fn invalid(msg: &'static str) -> Error {
    Error::Io(io::Error::new(io::ErrorKind::InvalidInput, msg))
}

fn u32_len(n: usize) -> Result<u32> {
    u32::try_from(n).map_err(|_| invalid("SSTable field exceeds u32"))
}

fn entry_len(k: &[u8], v: &Option<Vec<u8>>) -> Result<usize> {
    let vl = v.as_ref().map_or(0, Vec::len);
    u32_len(k.len())?;
    u32_len(vl)?;
    let n = 9usize.checked_add(k.len()).and_then(|x| x.checked_add(vl))
        .ok_or_else(|| invalid("SSTable entry length overflow"))?;
    u32_len(n.checked_add(4).ok_or_else(|| invalid("SSTable block length overflow"))?)?;
    Ok(n)
}

fn temp_path(path: &Path) -> PathBuf {
    let mut name = path.as_os_str().to_os_string();
    name.push(".tmp");
    PathBuf::from(name)
}

fn append_crc(data: &mut Vec<u8>) {
    let crc = crc32(data);
    data.extend_from_slice(&crc.to_le_bytes());
}

fn write_block(
    file: &mut impl Write, block: &mut Vec<u8>, first: &[u8],
    offset: &mut u64, index: &mut Vec<u8>,
) -> Result<()> {
    append_crc(block);
    let len = u32_len(block.len())?;
    let next = offset.checked_add(u64::from(len))
        .ok_or_else(|| invalid("SSTable offset overflow"))?;
    index.extend_from_slice(&u32_len(first.len())?.to_le_bytes());
    index.extend_from_slice(first);
    index.extend_from_slice(&offset.to_le_bytes());
    index.extend_from_slice(&len.to_le_bytes());
    file.write_all(block)?;
    *offset = next;
    block.clear();
    Ok(())
}

/// Writes sorted, unique byte keys and tombstones. Replaces the target only
/// after the temporary file is complete and synced. Existing .tmp is not ours.
pub fn write_sstable(path: impl AsRef<Path>, entries: &[(Vec<u8>, Option<Vec<u8>>)]) -> Result<u64> {
    let path = path.as_ref();
    if entries.windows(2).any(|w| w[0].0 >= w[1].0) {
        return Err(invalid("SSTable keys must be strictly increasing"));
    }
    for (key, value) in entries {
        entry_len(key, value)?;
    }
    let count = u64::try_from(entries.len()).map_err(|_| invalid("too many entries"))?;
    let tmp = temp_path(path);
    let mut file = OpenOptions::new().write(true).create_new(true).open(&tmp)?;
    let result = (|| -> Result<u64> {
        let mut block = Vec::new();
        let mut index = vec![0u8; 4];
        let mut first: &[u8] = &[];
        let mut offset = 0u64;
        let mut blocks = 0u32;
        for (key, value) in entries {
            let n = entry_len(key, value)?;
            if !block.is_empty() && block.len().saturating_add(n).saturating_add(4) > BLOCK_TARGET {
                write_block(&mut file, &mut block, first, &mut offset, &mut index)?;
                blocks = blocks.checked_add(1).ok_or_else(|| invalid("too many blocks"))?;
            }
            if block.is_empty() {
                first = key;
            }
            let bytes = value.as_deref().unwrap_or(&[]);
            block.push(u8::from(value.is_some()));
            block.extend_from_slice(&u32_len(key.len())?.to_le_bytes());
            block.extend_from_slice(&u32_len(bytes.len())?.to_le_bytes());
            block.extend_from_slice(key);
            block.extend_from_slice(bytes);
        }
        if !block.is_empty() {
            write_block(&mut file, &mut block, first, &mut offset, &mut index)?;
            blocks = blocks.checked_add(1).ok_or_else(|| invalid("too many blocks"))?;
        }
        index[..4].copy_from_slice(&blocks.to_le_bytes());
        append_crc(&mut index);
        let index_len = u32_len(index.len())?;
        file.write_all(&index)?;
        let mut footer = Vec::with_capacity(36);
        footer.extend_from_slice(MAGIC);
        footer.extend_from_slice(&0u32.to_le_bytes());
        footer.extend_from_slice(&offset.to_le_bytes());
        footer.extend_from_slice(&index_len.to_le_bytes());
        footer.extend_from_slice(&count.to_le_bytes());
        append_crc(&mut footer);
        file.write_all(&footer)?;
        file.sync_all()?;
        offset.checked_add(u64::from(index_len)).and_then(|x| x.checked_add(36))
            .ok_or_else(|| invalid("SSTable file length overflow"))
    })();
    drop(file);
    match result {
        Ok(len) => match fs::rename(&tmp, path) {
            Ok(()) => Ok(len),
            Err(e) => {
                let _ = fs::remove_file(&tmp);
                Err(e.into())
            }
        },
        Err(e) => {
            let _ = fs::remove_file(&tmp);
            Err(e)
        }
    }
}
