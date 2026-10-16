#!/usr/bin/env python3
# Kivadis fixtures for the predefined-CMap CJK path (not from an upstream pull request).
#
# Each fixture is a one-page PDF whose only font is a Type0 font over a non-embedded CID font: either
# Identity-H with no /ToUnicode (CID -> Adobe-<ordering>-UCS2), or a predefined Encoding CMap with a
# one-entry /ToUnicode (code -> CID by the built-in Encoding CMap -> Adobe-<ordering>-UCS2); their text has
# two-byte codes only, as the one-entry /ToUnicode declares a two-byte code space. The page shows
# the codes as a hex string; the predefined ones are produced with Python's codecs.
#
#   python3 scripts/make_cjk_fixtures.py tests/fixtures
import os
import sys

# Identity-H fonts: the text is the CIDs of the Adobe collection, read through Adobe-<ordering>-UCS2.
# (file, ordering, CIDs, the text they read as). The CIDs are from the embedded UCS2 maps, e.g.
# CID 843 is HIRAGANA LETTER A in Adobe-Japan1 (pdf-inspector issue 573).
IDENTITY_FIXTURES = [
    ("cjk_japan1_identity_h.pdf", "Japan1", [34, 35, 36, 843, 924, 1125, 3284, 3722, 1952], "ABCあん亜日本語"),
    ("cjk_gb1_identity_h.pdf", "GB1", [4559, 3795, 1193, 3435, 4162, 1597, 3288], "中文测试一二三"),
    ("cjk_cns1_identity_h.pdf", "CNS1", [5183, 5911, 661, 726, 3259, 3850], "繁體中文測試"),
    ("cjk_korea1_identity_h.pdf", "Korea1", [3296, 1204, 2479, 3114, 2333, 3167], "한국어테스트"),
]

# Predefined Encoding CMaps whose /ToUnicode is sparse (one entry): the codes are read through the built-in
# Encoding CMap and Adobe-<ordering>-UCS2. (file, Encoding name, ordering, codec, text)
PREDEFINED_FIXTURES = [
    ("cjk_japan1_90ms_rksj.pdf", "90ms-RKSJ-H", "Japan1", "cp932", "あいう日本語"),
    ("cjk_japan1_unijis_ucs2.pdf", "UniJIS-UCS2-H", "Japan1", "utf-16-be", "日本語のテキスト"),
    ("cjk_gb1_gbk_euc.pdf", "GBK-EUC-H", "GB1", "gbk", "中文测试一二三"),
    ("cjk_cns1_eten_b5.pdf", "ETen-B5-H", "CNS1", "big5", "繁體中文測試"),
    ("cjk_korea1_kscms_uhc.pdf", "KSCms-UHC-H", "Korea1", "cp949", "한국어테스트"),
]

SPARSE_TO_UNICODE = (
    b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap "
    b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def "
    b"/CMapName /Adobe-Identity-UCS def /CMapType 2 def "
    b"1 begincodespacerange <0000> <FFFF> endcodespacerange "
    b"1 beginbfchar <0041> <0041> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end"
)


def pdf(objects):
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode("ascii") + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    return bytes(out)


def stream(content):
    return b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"\nendstream"


def font_objects(encoding, ordering, with_to_unicode):
    """Objects 4 (Type0 font) and 6 (CID font; 7 is its descriptor and 8 the ToUnicode when asked)."""
    to_unicode = " /ToUnicode 8 0 R" if with_to_unicode else ""
    objects = {
        4: f"<< /Type /Font /Subtype /Type0 /BaseFont /KivadisCJK /Encoding /{encoding} "
        f"/DescendantFonts [6 0 R]{to_unicode} >>".encode("ascii"),
        6: f"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /KivadisCJK "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering ({ordering}) /Supplement 6 >> "
        f"/FontDescriptor 7 0 R /DW 1000 >>".encode("ascii"),
    }
    return objects


def build(encoding, ordering, shown_hex, with_to_unicode):
    content = f"BT /F1 24 Tf 72 700 Td <{shown_hex}> Tj ET".encode("ascii")
    font = font_objects(encoding, ordering, with_to_unicode)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        font[4],
        stream(content),
        font[6],
        b"<< /Type /FontDescriptor /FontName /KivadisCJK /Flags 6 /FontBBox [0 -200 1000 900] "
        b"/ItalicAngle 0 /Ascent 880 /Descent -120 /CapHeight 700 /StemV 80 >>",
    ]
    if with_to_unicode:
        objects.append(stream(SPARSE_TO_UNICODE))
    return pdf(objects)


def main(directory):
    for name, ordering, cids, text in IDENTITY_FIXTURES:
        shown = "".join(f"{cid:04X}" for cid in cids)
        with open(os.path.join(directory, name), "wb") as handle:
            handle.write(build("Identity-H", ordering, shown, False))
        print(f"{name}: Identity-H {ordering} {text!r}")
    for name, encoding, ordering, codec, text in PREDEFINED_FIXTURES:
        with open(os.path.join(directory, name), "wb") as handle:
            handle.write(build(encoding, ordering, text.encode(codec).hex().upper(), True))
        print(f"{name}: {encoding} {ordering} {text!r}")


if __name__ == "__main__":
    main(sys.argv[1])
