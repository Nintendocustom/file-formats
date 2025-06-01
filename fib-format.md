## FIB (FUSE) File Format

This document describes the structure of FIB (`.fib`) files, an archive format primarily associated with **TT Fusion**
for their LEGO handheld games, such as *LEGO City Undercover: The Chase Begins* for the Nintendo 3DS. The internal name
for this format appears to be "FUSE," as indicated by the magic.

These files serve as containers for multiple individual files, which can be stored uncompressed or compressed. A `.csv` file is often alongside the `.fib` file and contains actual filenames for the hashed entries within the FIB's File
System Table.

### File Structure

The FIB file is structured as follows. All multibyte integers are **Little-Endian** unless otherwise specified.

| Offset                | Size (bytes)     | Description                        | Notes                                                                                                |
|:----------------------|:-----------------|:-----------------------------------|:-----------------------------------------------------------------------------------------------------|
| 0x0                   | 8                | Magic Number                       | Always `FUSE1.00` (ASCII encoded)                                                                    |
| 0x8                   | 4                | Number of Files (`num_files`)      | Unsigned 4-byte integer. Total files in the archive                                                  |
| 0xC                   | 4                | Unknown (Zeros)                    | Typically observed as all zeros                                                                      |
| 0x10                  | 4                | FST Offset (`start_of_fst_offset`) | Unsigned 4-byte integer. Offset from the beginning of the file to the start of the File System Table |
| 0x14                  | Variable         | File Data Blocks                   | Concatenated data for all files. See "File Data" section                                             |
| `start_of_fst_offset` | `num_files * 12` | File System Table (FST)            | An array of FST entries, **sorted by `Filename Hash`**. See "FST Entry Structure"                    |

### FST Entry Structure (V1)

The File System Table (FST) starts at `start_of_fst_offset` and consists of `num_files` entries, each 12 bytes long.
Entries within the FST block in the file are **sorted in ascending order by their `Filename Hash`**.

| Offset (relative to entry start) | Size (bytes) | Description            | Notes                                                                                                    |
|:---------------------------------|:-------------|:-----------------------|:---------------------------------------------------------------------------------------------------------|
| 0x0                              | 4            | Filename Hash          | Unsigned 4-byte integer. This is a CRC32 hash of the full file path/name. See "Filename Hash Generation" |
| 0x4                              | 4            | File Data Offset       | Unsigned 4-byte integer. Offset from the beginning of the FIB file to this specific file's data block    |
| 0x8                              | 3            | Decompressed File Size | Unsigned 3-byte integer. The size of the file after decompression                                        |
| 0xB                              | 1            | Compression Type       | Unsigned 1-byte integer. See "Compression Types" table                                                   |


### FST Entry Structure (Version 2)

| Offset (relative to entry start) | Size (bytes) | Description                          | Notes                                                                                             |
|:---------------------------------|:-------------|:-------------------------------------|:--------------------------------------------------------------------------------------------------|
| 0x0                              | 4            | Filename Hash                        | Unsigned 4-byte integer. Same as V1.                                                              |
| 0x4                              | 4            | File Data Offset                     | Unsigned 4-byte integer. Same as V1.                                                              |
| 0x8                              | 4            | Decompressed Size & Compression Type | A 4-byte field. See "Decompressed Size & Compression Type Field (V2)" for details.                |

#### Decompressed Size & Compression Type Field (V2)

This 4-byte field (read as an unsigned 32-bit Little-Endian integer, `num`) is interpreted as:

* **Compression Type:** The lower 5 bits of `num`.
  `compression_type = num & 0x1F` (where `0x1F` is `(1 << 5) - 1`)
* **Decompressed File Size:** The upper 27 bits of `num`.
  `decompressed_size = num >> 5`

### Filename Hash Generation

The `Filename Hash` is generated using a CRC32 algorithm on the UTF-8 encoded filename string. The specific calculation
observed is:
`hash = ~zlib.crc32(filename.encode('utf-8')) & 0xFFFFFFFF`

### File Data

Each file's data is stored contiguously in the "File Data Blocks" section of the FIB file.
*   The **offset** for a specific file's data is given by its `File Data Offset` in its FST entry.
*   The **compressed size** of a file is not explicitly stored per entry. It is calculated by:
    *   For all but the last file (when sorted by `File Data Offset`): `(Next File's Data Offset) - (Current File's Data Offset)`
    *   For the last file (when sorted by `File Data Offset`): `(FST Offset) - (Current File's Data Offset)`
    *   *(Note: This requires FST entries to be sorted by `File Data Offset` for calculation, though they are stored sorted by `Filename Hash` in the FST block itself.)*
*   The **decompressed size** is given by `Decompressed File Size` in its FST entry. (differs between V1 and V2).

If `Compression Type` is `UNCOMPRESSED`, the data block contains the raw file data, and its length is equal to `Decompressed File Size`.
If `Compression Type` is `COMPRESSED`, the data block compressed.

#### Compressed Blocks

* **V1:** The compressed data block starts with a 3-byte (24-bit) little-endian unsigned integer indicating the decompressed chunk size, followed by 1 byte for the compression type (same as in the FST entry). The compressed data follows immediately after.
* **V2:** The compressed data block starts with a 4-byte (32-bit) little-endian unsigned integer indicating the decompressed chunk size. The compressed data follows immediately after.

See the "Compressions" section for details on the compression algorithm.
The `Compression Type` byte in the V1 FST entry can have the following values:

### Compression Types (Version 1)
| Value | Name           | Description                                  |
|:------|:---------------|:---------------------------------------------|
| 0x00  | `UNCOMPRESSED` | The file data is stored raw.                 |
| 0x40  | `COMPRESSED`   | The file data is RFPK compressed (V1 style). |


### Compression Types (Version 2)

The 5-bit `Compression Type` extracted from the V2 FST entry can have the following values:

| Value (Decimal) | Value (Hex) | Name           | Description                       |
|:----------------|:------------|:---------------|:----------------------------------|
| 0               | 0x00        | `UNKNOWN`      | Purpose not clear, but compressed |
| 12              | 0x0C        | `UNCOMPRESSED` | The file data is stored raw       |
| 13              | 0x0D        | `COMPRESSED`   | The file data is compressed       |

---

### CSV File

* FIB files often come with an external `.csv` file (e.g., `archive.fib` would use `archive.csv`) to map `Filename Hash`
  values to human-readable filenames.
* Those aren't needed for parsing the FIB file itself since the game hashes filenames/paths directly, but they can be useful for understanding the contents of the archive.
* The CSV file typically has a header and columns such as:
    1. `Filename CRC`
    2. `Filename`
    3. `Compressed Size`
    4. `File Size` (Decompressed Size)
    5. `Offset`
* **Example CSV content:**
  ```csv
  Filename CRC,Filename,Compressed Size,File Size,Offset
  0x09f2c6d1,models/textures/pc01_lombardstreet.btga,48383,87352,0x00000014
  0x70f02c44,models/textures/pc02_brooklynbridge.btga,46404,87352,0x00017257
  0xf33f098b,models/textures/pc03_spaceneedle.btga,44170,87352,0x00017257
  ```
  
### Compressions

FIB files use a custom LZ77-based compression algorithm.
An implementation of the algorithm can be found in the [quickbms source code](https://github.com/LittleBigBug/QuickBMS/blob/5315ffe664b88dc09ae783ad17d9dfd252b1c927/src/included/unrfpk.c#L5).
Note: This implementation only applies to Version 1 - Version 2 uses a slightly different method.

---

* **Note:**
  * Files with a `Decompressed File Size` of 0 should generally be skipped during extraction and considered as empty/placeholder entries.
