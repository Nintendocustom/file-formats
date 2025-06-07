from __future__ import annotations

import csv
import enum
import os.path
import struct
from ctypes import Structure, c_int
from typing import BinaryIO
from zlib import crc32


class Compression(enum.IntEnum):
    UNCOMPRESSED = 0
    COMPRESSED = 64


class FibFileParser:
    def __init__(self, fib_filename: str, csv_file: str = None):
        self.fib_filename: str = fib_filename
        self.fib_file: BinaryIO = open(fib_filename, "rb")

        self.csv_fst_file: str = csv_file or fib_filename.replace(".fib", ".csv")
        self.csv_fst_data: dict | None = self._load_csv_data()
        self.fst: list = []

        self.compression = Compression

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fib_file.close()

    def _load_csv_data(self) -> dict:
        if not os.path.isfile(self.csv_fst_file):
            return {}
        csv_data = {}
        with open(self.csv_fst_file, "r") as csvfile:
            has_header = csv.Sniffer().has_header(csvfile.read(1024))
            csvfile.seek(0)

            reader = csv.reader(csvfile)
            if has_header:
                next(reader)  # Skip header if it exists

            for row in reader:
                hash_key = "0x" + row[0].lower() if not row[0].startswith("0x") else row[0].lower()
                csv_data[hash_key] = row[1]  # Store directly as hex key
        return csv_data

    def _validate_magic(self) -> None:
        magic = self.fib_file.read(8)
        assert b'FUSE1.00' == magic, "Invalid file magic"

    def _read_header(self) -> (int, int, int):
        """
        Reads the FIB file header and returns number of files, zeros, and FST offset.
        """
        return struct.unpack("III", self.fib_file.read(12))

    def _parse_file_entry(self) -> list | None:
        """
        Parses a single file entry in the FST and returns
         - filename hash
         - filename (if available),
         - size
         - decompressed size
         - file offset
         - compression
        """
        filename_hash = self._int2hex(struct.unpack("<I", self.fib_file.read(4))[0])
        file_offset = struct.unpack("<I", self.fib_file.read(4))[0]
        decompressed_file_size, compression_kind = self._extract_file_size_and_compression(self.fib_file.read(4))

        if decompressed_file_size == 0:
            print(f"Skipping file with offset {self._int2hex(file_offset)}")
            return None

        filename = self.csv_fst_data.get(filename_hash, "unknown filename")
        return [filename_hash, filename, 0, decompressed_file_size, self._int2hex(file_offset), compression_kind.name]

    def _calculate_compressed_size(self, start_of_fst_offset: int) -> None:
        """
        Calculates the compressed size for each file entry in the FST.
        """
        for i in range(len(self.fst) - 1):
            current_file, next_file = self.fst[i], self.fst[i + 1]
            calculated_size = int(next_file[-2], 16) - int(current_file[-2], 16)
            current_file[2] = calculated_size

        self.fst[-1][2] = start_of_fst_offset - int(self.fst[-1][-2], 16)

    def _extract_file_size_and_compression(self, binary_sequence: bytes) -> (int, Compression):
        """
        Extracts decompressed file size and compression type
        """
        shifted_num = int.from_bytes(binary_sequence[:3], byteorder='little')
        compression_value = int.from_bytes(binary_sequence[3:4], byteorder='little')
        return shifted_num, self.compression(compression_value)

    @staticmethod
    def _int2hex(data: int) -> str:
        return f"0x{data:08x}"

    def _u24(self) -> int:
        return struct.unpack("<I", self.fib_file.read(3) + b"\x00")[0]

    def _real_rfpk_decompress(self, data_size: int, decompressed_size: int) -> bytearray:
        """
        Decompresses RFPK-compressed data within the FIB file
        """
        size_sum = 0
        output = bytearray()

        while size_sum < data_size:
            chunk_size = self._u24()
            compressed = Compression(int.from_bytes(self.fib_file.read(1), byteorder='little'))

            if compressed != Compression.COMPRESSED:
                raise ValueError("Data is not compressed.")

            chunk = self.fib_file.read(chunk_size)
            size_sum += chunk_size + 4
            # chunk_size = min(decompressed_size - idx * 32768, 32768)

            chunk_output = self.rfpk_decompress(chunk)
            output.extend(chunk_output)
        return output

    @staticmethod
    def rfpk_decompress(file_data: bytes) -> bytearray:
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
                num = b & 7
                block_header_triple.thenCopy = (num << 7) + b4 + 5
                block_header_triple.offset = b2 * 256 + b3 + 1
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

    def parse_fst(self) -> list:
        """
        Parses the FST and returns a list of file entries
        """
        self._validate_magic()
        number_files, zeros, start_of_fst_offset = self._read_header()
        self.fib_file.seek(start_of_fst_offset)

        for _ in range(number_files):
            entry = self._parse_file_entry()
            if entry:
                self.fst.append(entry)

        original_order = self.fst.copy()
        self.fst.sort(key=lambda x: int(x[-2], 16))
        self._calculate_compressed_size(start_of_fst_offset)
        self.fst = original_order
        return self.fst

    def extract_all_files(self, output_folder: str) -> None:
        """
        Extracts all files from the FIB file to the specified output folder
        """
        total_files = len(self.fst)
        files_processed = 0

        for _, filename, compressed_size, decompressed_size, offset, compression in self.fst:
            filepath = os.path.join(output_folder, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            self.fib_file.seek(int(offset, 16))

            if "unknown" in filename:
                continue
            if self.compression[compression] == self.compression.COMPRESSED:
                try:
                    decompressed_data = self._real_rfpk_decompress(compressed_size, decompressed_size)
                    if len(decompressed_data) != decompressed_size:
                        print(f"Warning: Decompressed size mismatch for {filename}")
                except Exception as e:
                    print(f"Error decompressing {filename}: {e}")
                    continue
            else:
                decompressed_data = self.fib_file.read(decompressed_size)

            with open(filepath, "wb") as f:
                f.write(decompressed_data)

            files_processed += 1
            percentage = (files_processed / total_files) * 100
            print(f"\r{percentage:.2f} % complete", end="")


class FibFileWriter:
    def __init__(self, fib_filename: str):
        self.fib_filename: str = fib_filename
        self.fib_file: BinaryIO = open(fib_filename, "wb")

        self.fst_pos: int = 0
        self.file_data_pos: int = 20

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.fib_file.close()

    def _write_magic(self) -> None:
        self.fib_file.write(b'FUSE1.00')

    def write_header(self, number_files: int, start_of_fst_offset: int) -> None:
        self._write_magic()
        self.fib_file.write(struct.pack("<III", number_files, 0, start_of_fst_offset))

        self.fst_pos = start_of_fst_offset

    def write_file_entry(self, filename_hash: str, decompressed_size: int, compression_kind_name: Compression.value, file_data: bytes) -> None:
        self.fib_file.seek(self.fst_pos)

        self.fib_file.write(struct.pack("<I", self._hex2int(filename_hash)))
        self.fib_file.write(struct.pack("<I", self.file_data_pos))
        self.fib_file.write(self._encode_file_size_and_compression(decompressed_size, Compression[compression_kind_name]))

        self.fst_pos = self.fib_file.tell()
        self.fib_file.seek(self.file_data_pos)
        self.fib_file.write(file_data)
        self.file_data_pos = self.fib_file.tell()

    @staticmethod
    def _encode_file_size_and_compression(shifted_num: int, compression: Compression) -> bytes:
        assert isinstance(shifted_num, int), "Invalid shifted number input"
        assert isinstance(compression, Compression), "Invalid compression input"
        mask = (1 << 5) - 1
        original_num = (shifted_num << 5) | (compression.value & mask)
        return original_num.to_bytes(4, byteorder='little')

    @staticmethod
    def _hex2int(data: str) -> int:
        assert isinstance(data, str) and data.startswith('0x'), "Invalid hex input"
        return int(data, 16)

    @staticmethod
    def _int2hex(data: int) -> str:
        return f"0x{data:08x}"

    def _crc32_native(self, filename: str) -> str:
        return self._int2hex(~crc32(filename.encode()) & 0xFFFFFFFF)
