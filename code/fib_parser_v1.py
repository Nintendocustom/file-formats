from __future__ import annotations

import enum
import struct
from ctypes import c_int

from _ctypes import Structure

from fib_parser_v2 import FibFileParser as FFP, FibFileWriter as FFW


class Compression(enum.IntEnum):
    UNKNOWN = 0
    UNCOMPRESSED = 12
    COMPRESSED = 13


class FibFileParser(FFP):
    def __init__(self, fib_filename: str, csv_file: str = None):
        super().__init__(fib_filename, csv_file)
        self.compression = Compression

    def _extract_file_size_and_compression(self, binary_sequence: bytes) -> (int, Compression):
        num = int.from_bytes(binary_sequence, byteorder='little')
        mask = (1 << 5) - 1
        dropped_bits = num & mask
        shifted_num = num >> 5
        return shifted_num, self.compression(dropped_bits)

    def _u32(self) -> int:
        return struct.unpack("<I", self.fib_file.read(4))[0]

    @staticmethod
    def rfpk_decompress(file_data: bytes) -> bytearray:
        """
        The actual decompression algorithm, based on https://aluigi.altervista.org/quickbms.htm
        """

        class BlockHeaderTriple(Structure):
            _fields_ = [("toCopy", c_int),
                        ("thenCopy", c_int),
                        ("offset", c_int)]

        file_data = bytes(file_data)
        result = bytearray()

        i_pos = 0
        while i_pos < len(file_data):
            block_header_triple = BlockHeaderTriple(0, 0, 0)
            b = file_data[i_pos]
            i_pos += 1
            if (b & 128) == 0:
                b2 = file_data[i_pos]
                i_pos += 1
                block_header_triple.toCopy = (b & 12) >> 2
                block_header_triple.thenCopy = ((b & 112) >> 4) + 3
                block_header_triple.offset = (b & 3) * 256 + b2 + 1
            elif (b & 192) == 128:
                b2 = file_data[i_pos]
                i_pos += 1
                b3 = file_data[i_pos]
                i_pos += 1
                block_header_triple.toCopy = (b2 & 192) >> 6
                block_header_triple.thenCopy = (b & 63) + 4
                block_header_triple.offset = (b2 & 63) * 256 + b3 + 1
            elif (b & 224) == 192:
                b2 = file_data[i_pos]
                i_pos += 1
                b3 = file_data[i_pos]
                i_pos += 1
                b4 = file_data[i_pos]
                i_pos += 1
                block_header_triple.toCopy = (b & 24) >> 3
                num = b & 6
                block_header_triple.thenCopy = (num << 7) + b4 + 5
                block_header_triple.offset = ((b & 1) << 16) + b2 * 256 + b3 + 1
            elif b in [252, 253, 254, 255]:
                block_header_triple.toCopy = b - 252
                block_header_triple.thenCopy = 0
                block_header_triple.offset = 0
            else:
                if (b & 224) != 224:
                    raise Exception(f"{b:x2} @ {i_pos:x8}")
                block_header_triple.toCopy = ((b & 31) + 1) * 4
                block_header_triple.thenCopy = 0
                block_header_triple.offset = 0

            result += file_data[i_pos: i_pos + block_header_triple.toCopy]
            i_pos += block_header_triple.toCopy

            for _ in range(block_header_triple.thenCopy):
                result.append(result[-block_header_triple.offset])
        return result

    def _real_rfpk_decompress(self, data_size: int, decompressed_size: int) -> bytearray:
        size_sum = 0
        output = bytearray()

        while size_sum < data_size:
            chunk_size = self._u32()
            chunk = self.fib_file.read(chunk_size)
            size_sum += chunk_size + 4
            # chunk_size = min(decompressed_size - idx * 262144, 262144)

            chunk_output = self.rfpk_decompress(chunk)
            output.extend(chunk_output)
        return output


class FibFileWriter(FFW):
    def __init__(self, fib_filename: str):
        self.fib_filename = fib_filename
        self.fib_file = open(fib_filename, "wb")

        self.fst_pos = 0
        self.file_data_pos = 20

    @staticmethod
    def shift_binary_sequence_back(shifted_num, compression):
        assert isinstance(shifted_num, int), "Invalid shifted number input"
        assert isinstance(compression, Compression), "Invalid compression input"
        mask = (1 << 5) - 1
        original_num = (shifted_num << 5) | (compression.value & mask)
        return original_num.to_bytes(4, byteorder='little')

    def write_file_entry(self, filename_hash: str, decompressed_size: int, compression_kind_name: Compression.value, file_data: bytes):
        """
        Writes a file entry to the FIB file
        """
        self.fib_file.seek(self.fst_pos)

        self.fib_file.write(struct.pack("<I", self._hex2int(filename_hash)))
        self.fib_file.write(struct.pack("<I", self.file_data_pos))
        self.fib_file.write(self.shift_binary_sequence_back(decompressed_size, Compression[compression_kind_name]))

        self.fst_pos = self.fib_file.tell()
        self.fib_file.seek(self.file_data_pos)
        self.fib_file.write(file_data)
        self.file_data_pos = self.fib_file.tell()
