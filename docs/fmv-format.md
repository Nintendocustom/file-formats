## FMV  File Format

> ⚠
> This is an early version of the documentation and is incomplete or difficult to comprehend.

In the following, the structure of FMV (`.fmv`) files is described. FMV files are a container format used for storing video and
audio data by **TT Games** for their LEGO games, such as *LEGO City Undercover*. The internal name for this format
appears to be "FMV!", as indicated by the magic.

### FMV Header

The FMV header is structured as follows. All multibyte integers are **Little-Endian** unless otherwise specified.

| Offset | Size (bytes) | Description                   | Notes                                                                                                            |
|:-------|:-------------|:------------------------------|:-----------------------------------------------------------------------------------------------------------------|
| 0x0    | 4            | Magic                         | Always `FMV!` (ASCII encoded)                                                                                    |
| 0x4    | 2            | Version                       | 0x0112 or 0x0113                                                                                                 |
| 0x6    | 2            | Header size                   | Size of the whole header (30 bytes, hard-coded)                                                                  |
| 0x8    | 2            | Width                         | Video width in pixels                                                                                            |
| 0xA    | 2            | Height                        | Video height in pixels                                                                                           |
| 0xC    | 4            | Total number of frames        | Total number of frame                                                                                            |
| 0x10   | 4            | Total audio samples per track | ??? - Verify again                                                                                               |
| 0x14   | 1            | FPS fraction                  | Framerate fractional part (.97)                                                                                  |
| 0x15   | 1            | FPS integer                   | Framerate interger part (23.)                                                                                    |
| 0x16   | 4            | Flags                         | Bitmask<br/>Bit 0 = 1 frame buffer instead of 2<br/>Bit 1 = Initialise Audio pipline<br/>Bit 2 = Has audio track |
| 0x1A   | 4            | Max. chunk size               | Size of the largest chunk in the file                                                                            |
| 0x1E   | 4            | Number of Audio Tracks        | The number of audio tracks (if it has audio)                                                                     |

### Audio-Header

After the main header, the audio track headers are stored, one for each audio track. Up to 256 audio tracks are in theory
supported. Each audio track header is 12 bytes long.

| Offset | Size (bytes) | Description      | Notes                       |
|:-------|:-------------|:-----------------|:----------------------------|
| 0x0    | 4            | Sample Rate (Hz) | The sample rate in Hz       |
| 0x4    | 1            | Format Type      | 0 = PCM, 1 = ADPCM          |
| 0x8    | 1            | Track ID         | Corresponds to the language |
| 0xB    | 1            | Channels         | Possible are 1, 2, 6, 8     |
| 0xB    | 1            | Bits per Sample  | Either 8 or 16 bits         |

### Chunk-Types

Each chunk in the FMV file starts with a 4-byte FourCC code that indicates the type of data contained in the chunk.
After that, the chunk contains a 4-byte unsigned integer indicating the size of the chunk data (excluding the FourCC and size fields). 
The chunk data follows immediately after.

| FourCC         | Description                                                       |
|:---------------|:------------------------------------------------------------------|
| FMVk           | New video keyframe, new huffman tables, quality byte              |
| FMVd           | Video delta frame, reuses huffman tables, 3 different modes       |
| FMVn           | No video data, repeat previous frame                              |
| FMA + Track ID | Audio chunk, last byte tells us the Track ID the chunk belongs to |

### Video Chunk Structure

| Offset | Size (bytes) | Description         |
|:-------|:-------------|:--------------------|
| 0x0    | 2            | RLE chunk length    |
| 0x4    | x            | RLE compressed data |

#### Control Byte

| Type | Description                                                       |
|:-----|:------------------------------------------------------------------|
| 0    | Skip, the macroblock is idenitcal to the previous frame           |
| 1    | Motion, the macroblock is a motion vector from the previous frame |
| 2    | Fill, the macroblock is filled with a single color                |
| 255  | Coded, replaces pxiesl                                            |

### Looping
There is no explicit looping information in the FMV file. Looping is handled by the game engine, which can loop the
video by seeking back to the first frame and replaying it.

---

* **Notes:**
