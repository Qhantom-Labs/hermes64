"""Stdlib-only Hann/FFT spectral sheets, PNG writer and numeric summaries.

These are measurements, not an audio-listening or perceptual-quality proxy.
"""

import argparse
import hashlib
import json
import math
import struct
import zlib

from . import SAMPLE_RATE
from .audit import audit_manifest
from .build import LANE, json_bytes, lane_path, write_bytes
from .validate import decode_wav, rms


# Original tiny 3x5 glyphs, used only for diagnostic labels. No external font.
GLYPHS = {
    "A": "010101111101101", "B": "110101110101110", "C": "011100100100011",
    "D": "110101101101110", "E": "111100110100111", "F": "111100110100100",
    "G": "011100101101011", "H": "101101111101101", "I": "111010010010111",
    "J": "001001001101010", "K": "101101110101101", "L": "100100100100111",
    "M": "101111111101101", "N": "101111111111101", "O": "010101101101010",
    "P": "110101110100100", "Q": "010101101111011", "R": "110101110101101",
    "S": "011100010001110", "T": "111010010010010", "U": "101101101101111",
    "V": "101101101101010", "W": "101101111111101", "X": "101101010101101",
    "Y": "101101010010010", "Z": "111001010100111",
    "0": "111101101101111", "1": "010110010010111", "2": "110001010100111",
    "3": "110001010001110", "4": "101101111001001", "5": "111100110001110",
    "6": "011100111101111", "7": "111001010010010", "8": "111101111101111",
    "9": "111101111001110", ".": "000000000000010", "-": "000000111000000",
    ":": "000010000010000", "/": "001001010100100", " ": "000000000000000",
}


def spectrum(samples):
    count = len(samples)
    if count < 4 or count & (count-1):
        raise ValueError("Hann FFT length must be a power of two >=4")
    window = [0.5-0.5*math.cos(2*math.pi*i/(count-1)) for i in range(count)]
    data = [complex(sample*weight, 0.0) for sample, weight in zip(samples, window)]
    reverse = 0
    for i in range(1, count):
        bit = count >> 1
        while reverse & bit:
            reverse ^= bit
            bit >>= 1
        reverse ^= bit
        if i < reverse:
            data[i], data[reverse] = data[reverse], data[i]
    width = 2
    while width <= count:
        angle = -2*math.pi/width
        twiddle = complex(math.cos(angle), math.sin(angle))
        for start in range(0, count, width):
            factor = complex(1.0, 0.0)
            for offset in range(width//2):
                even = data[start+offset]
                odd = factor*data[start+offset+width//2]
                data[start+offset], data[start+offset+width//2] = even+odd, even-odd
                factor *= twiddle
        width *= 2
    normalization = 2.0/sum(window)
    return [abs(value)*normalization for value in data[:count//2+1]]


def png_rgb(width, height, pixels):
    if width < 1 or height < 1 or len(pixels) != width*height*3:
        raise ValueError("invalid RGB dimensions")
    def chunk(kind, data):
        crc = zlib.crc32(kind+data) & 0xffffffff
        return struct.pack(">I", len(data))+kind+data+struct.pack(">I", crc)
    raw = bytearray()
    for row in range(height):
        raw.append(0)
        raw.extend(pixels[row*width*3:(row+1)*width*3])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR", header)
            +chunk(b"IDAT", zlib.compress(bytes(raw), 9))+chunk(b"IEND", b""))


def paint_text(pixels, width, height, x, y, text, color=(207, 222, 244), scale=2):
    for letter in text.upper():
        pattern = GLYPHS.get(letter, GLYPHS[" "])
        for row in range(5):
            for col in range(3):
                if pattern[row*3+col] == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            px, py = x+col*scale+dx, y+row*scale+dy
                            if 0 <= px < width and 0 <= py < height:
                                index = (py*width+px)*3
                                pixels[index:index+3] = bytes(color)
        x += 4*scale


def color_for(amplitude):
    db = 20*math.log10(max(1e-8, amplitude))
    level = max(0.0, min(1.0, (db+80)/72))
    return bytes((round(10+218*level**1.6), round(16+220*level**1.1), round(32+222*level**0.8)))


def analysis(samples, loop):
    columns = []
    count = len(samples)
    for column in range(96):
        center = round(column*(count-1)/95)
        values = []
        for j in range(512):
            index = center+j-256
            values.append(samples[index % count] if loop else (samples[index] if 0 <= index < count else 0.0))
        columns.append(spectrum(values))
    total = sum(value*value for column in columns for value in column)
    high = sum(value*value for column in columns for i, value in enumerate(column)
               if i*SAMPLE_RATE/512 >= 4000)
    windows = [samples[i*count//16:(i+1)*count//16] for i in range(16)]
    numeric = {"sampled_spectral_energy_above_4khz_fraction": high/max(total, 1e-20),
               "rms_by_sixteenth": [rms(window) for window in windows],
               "zero_crossings_per_second": sum(a*b < 0 for a,b in zip(samples, samples[1:])) / (count/SAMPLE_RATE)}
    return columns, numeric


def sheet(records, columns_by_id, title):
    width, row_height, top = 640, 150, 42
    height = top+row_height*len(records)
    pixels = bytearray(bytes((10, 16, 32))*width*height)
    paint_text(pixels, width, height, 12, 6, title)
    paint_text(pixels, width, height, 12, 23, "HANN 512 / DB -80 TO -8 / NOT LISTENED", scale=1)
    for row, record in enumerate(records):
        origin = top+row*row_height
        paint_text(pixels, width, height, 12, origin, record["id"])
        paint_text(pixels, width, height, 400, origin, "{:.3f} S".format(record["duration"]))
        paint_text(pixels, width, height, 2, origin+20, "11K", scale=1)
        paint_text(pixels, width, height, 2, origin+65, "5.5K", scale=1)
        paint_text(pixels, width, height, 2, origin+112, "0HZ", scale=1)
        columns = columns_by_id[record["id"]]
        for y in range(96):
            low = round((95-y)*257/96)
            high = min(257, max(low+1, round((96-y)*257/96)))
            scanline = bytearray()
            for column in columns:
                scanline.extend(color_for(max(column[low:high]))*6)
            index = ((origin+20+y)*width+52)*3
            pixels[index:index+len(scanline)] = scanline
        paint_text(pixels, width, height, 52, origin+122, "0S", scale=1)
        paint_text(pixels, width, height, 560, origin+122, "{:.3f}S".format(record["duration"]), scale=1)
        paint_text(pixels, width, height, 52, origin+135,
                   "PEAK {:.3f} RMS {:.3f}".format(record["peak"], record["rms"]), scale=1)
    return png_rgb(width, height, pixels), width, height


def generate(root):
    root = lane_path(root)
    audit_manifest(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding='utf-8'))
    columns_by_id = {}
    summaries = []
    for record in manifest["assets"]:
        samples = decode_wav(lane_path(root / record["file"]).read_bytes())
        columns, summary = analysis(samples, record["loop"])
        columns_by_id[record["id"]] = columns
        summaries.append(dict(summary, id=record["id"], sha256=record["sha256"]))
    sheets = []
    for loops, filename, title in ((True, "spectra/loops.png", "THAW - MUSIC AND AMBIENCE"),
                                    (False, "spectra/sfx.png", "THAW - ONE-SHOT SOUND KIT")):
        records = [record for record in manifest["assets"] if record["loop"] == loops]
        data, width, height = sheet(records, columns_by_id, title)
        write_bytes(root / filename, data)
        sheets.append({"file": filename, "width": width, "height": height,
                       "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                       "ids": [r["id"] for r in records]})
    report = {"fft_size": 512, "window": "Hann", "columns_per_clip": 96,
              "frequency_axis": "linear 0..11025 Hz, bottom to top",
              "magnitude_range_dbfs": [-80, -8], "assets": summaries, "sheets": sheets,
              "limitations": "Sparse sampled STFT, not LUFS/true-peak, not perceptual acceptance."}
    write_bytes(root / "spectra/numeric.json", json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(LANE))
    args = parser.parse_args()
    report = generate(args.root)
    print("DIAGNOSTICS assets={} sheets={}".format(len(report["assets"]), len(report["sheets"])))
    for image in report["sheets"]:
        print("PNG {file} {width}x{height} bytes={bytes} sha256={sha256}".format(**image))
    print("HIGH_BAND max_fraction={:.8f}".format(max(
        record["sampled_spectral_energy_above_4khz_fraction"] for record in report["assets"])))


if __name__ == "__main__":
    main()
