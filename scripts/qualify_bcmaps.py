#!/usr/bin/env python3
# Kivadis qualification of the 168 built-in CMaps (not from an upstream pull request).
#
# Reads the code points that `cargo test bcmap_qualification` sampled (BCMAP_QUALIFICATION_SAMPLES) and
# checks each against an independent source: Python's own codecs. A sample is a code of a map, the CID the
# crate reads for it, and the text the crate's Adobe-<ordering>-UCS2 map gives that CID. For a map whose
# code space a Python codec covers, the text must be the character the codec decodes from the code.
#
#   BCMAP_QUALIFICATION_SAMPLES=/tmp/samples.tsv cargo test --lib --no-default-features bcmap_qualification
#   python3 scripts/qualify_bcmaps.py /tmp/samples.tsv
#
# Letters, digits, kana, ideographs and hangul decide pass or fail. Punctuation and symbols are counted but
# never decide it: the Adobe collections and the codecs deliberately differ there (backslash and yen, wave
# dash, full-width tilde, ...).
import collections
import re
import sys
import unicodedata


def legacy_codec(name):
    """The Python codec for a legacy map's codes, with the bytes' transform, or None."""
    if "RKSJ" in name:
        return "cp932", lambda raw: raw
    if name in ("78-EUC-H", "78-EUC-V", "EUC-H", "EUC-V"):
        return "euc_jp", lambda raw: raw
    if name in ("H", "V", "78-H", "78-V", "Add-H", "Add-V", "Ext-H", "Ext-V"):
        # ISO-2022-JP two-byte codes, which are the EUC bytes without the high bits.
        return "euc_jp", lambda raw: bytes(b | 0x80 for b in raw) if len(raw) == 2 else raw
    if name.startswith(("GB-EUC", "GBpc-EUC")):
        return "gb2312", lambda raw: raw
    if name in ("GB-H", "GB-V"):
        return "gb2312", lambda raw: bytes(b | 0x80 for b in raw) if len(raw) == 2 else raw
    if name.startswith(("GBK-EUC", "GBKp-EUC")):
        return "gbk", lambda raw: raw
    if name.startswith("GBK2K"):
        return "gb18030", lambda raw: raw
    if name.startswith(("B5-", "B5pc-", "ETen-B5", "ETenms-B5")):
        return "big5", lambda raw: raw
    if name.startswith(("ETHK-B5", "HK")):
        return "big5hkscs", lambda raw: raw
    if name.startswith(("KSC-EUC", "KSCpc-EUC")):
        return "euc_kr", lambda raw: raw
    if name in ("KSC-H", "KSC-V"):
        return "euc_kr", lambda raw: bytes(b | 0x80 for b in raw) if len(raw) == 2 else raw
    if name.startswith("KSCms-UHC"):
        return "cp949", lambda raw: raw
    if name.startswith("KSC-Johab"):
        return "johab", lambda raw: raw
    return None


def single_byte_japanese(name, code):
    """JIS X 0201 reading of the four single-byte Japanese helper maps, for the codes that have one."""
    if name in ("Hankaku", "Roman") and 0x20 <= code <= 0x7E:
        return chr(code)
    if name == "Hankaku" and 0xA1 <= code <= 0xDF:
        return chr(0xFF61 + code - 0xA1)
    if name in ("Katakana", "Hiragana") and 0x21 <= code <= 0x5F:
        half = chr(0xFF61 + code - 0x21)
        if name == "Katakana":
            return half
        full = unicodedata.normalize("NFKC", half)
        return chr(ord(full) - 0x60) if "\u30a1" <= full <= "\u30f6" else full
    raise ValueError("no JIS X 0201 reading")


def expected_text(name, size, code):
    """The character a Python codec decodes from the code, or None when no codec covers the map."""
    raw = code.to_bytes(size, "big")
    if name in ("Hankaku", "Roman", "Katakana", "Hiragana"):
        return single_byte_japanese(name, code)
    if name.startswith("Uni"):
        codec = {"UCS2": "utf-16-be", "UTF16": "utf-16-be", "UTF32": "utf-32-be", "UTF8": "utf-8"}
        for key, value in codec.items():
            if f"-{key}-" in name:
                return raw.decode(value)
        return None
    found = legacy_codec(name)
    if found is None:
        return None
    codec, transform = found
    return transform(raw).decode(codec)


# Maps whose extension rows (vendor and Hong Kong additions) are not in Python's codecs, or are there as
# another character: a disagreement inside them is counted and listed, never silently passed.
VENDOR_EXTENSION_MAPS = re.compile(r"(83pv|90pv)-RKSJ|^ETen(ms)?-B5|^HK[a-z0-9]+-B5|^ETHK-B5")


def is_ideograph(text):
    return len(text) == 1 and "IDEOGRAPH" in unicodedata.name(text, "")


def decides(text):
    """Whether the expected text is one a collection and a codec must agree on."""
    return len(text) >= 1 and all(unicodedata.category(c)[0] in "LN" for c in text)


def main(path):
    per_map = collections.OrderedDict()
    with open(path, encoding="utf-8") as handle:
        next(handle)
        for line in handle:
            name, size, code, cid, text = line.rstrip("\n").split("\t")
            per_map.setdefault(name, []).append((int(size), int(code, 16), int(cid), text))

    failures, variants, extensions = [], [], []
    compatibility = 0
    oracle_maps, structural_maps = [], []
    verified_total = symbols_total = skipped_total = 0
    for name, samples in per_map.items():
        identity = re.fullmatch(r"Adobe-(Japan1|GB1|CNS1|Korea1)-\d", name)
        if identity:
            bad = [(c, cid) for _, c, cid, _ in samples if c != cid]
            if bad:
                failures.append(f"{name}: code is not its CID: {bad[:3]}")
            oracle_maps.append((name, len(samples), 0, 0))
            verified_total += len(samples)
            continue
        verified = symbols = skipped = 0
        uses_codec = False
        for size, code, cid, text in samples:
            try:
                expected = expected_text(name, size, code)
            except (UnicodeDecodeError, ValueError):
                skipped += 1
                continue
            if expected is None:
                break
            uses_codec = True
            got = "".join(chr(int(part, 16)) for part in text.split(",")) if text else ""
            if not decides(expected):
                symbols += 1
                continue
            if got == expected:
                verified += 1
            elif unicodedata.normalize("NFKC", got) == unicodedata.normalize("NFKC", expected):
                # A compatibility ideograph and its unified form are one character.
                verified += 1
                compatibility += 1
            elif is_ideograph(got) and is_ideograph(expected):
                # The collection reads the glyph variant its CID shows (e.g. U+85AE for U+85AA).
                variants.append(f"{name}: code {code:#x} -> CID {cid}: {got!r}, the codec reads {expected!r}")
            elif VENDOR_EXTENSION_MAPS.search(name):
                extensions.append(f"{name}: code {code:#x} -> CID {cid}: {got!r}, the codec reads {expected!r}")
            else:
                failures.append(f"{name}: code {code:#x} -> CID {cid}: {got!r}, the codec reads {expected!r}")
        if not uses_codec:
            structural_maps.append((name, len(samples)))
            continue
        oracle_maps.append((name, verified, symbols, skipped))
        verified_total += verified
        symbols_total += symbols
        skipped_total += skipped
        if verified == 0:
            failures.append(f"{name}: no sample decided by the codec ({symbols} symbols, {skipped} undecodable)")

    decided = verified_total + len(variants) + len(extensions)
    if len(variants) + len(extensions) > decided // 20:
        failures.append(f"{len(variants) + len(extensions)} of {decided} deciding samples disagree (limit 5%)")
    print(f"maps sampled: {len(per_map)} (+4 Adobe-<ordering>-UCS2 maps read as the CID-to-text side)")
    print(f"maps checked against a codec or by identity: {len(oracle_maps)}")
    print(f"letters, digits, kana, ideographs and hangul verified: {verified_total}")
    print(f"  of which a compatibility ideograph read as its unified form: {compatibility}")
    print(f"ideograph glyph variants (both sides ideographs): {len(variants)}")
    print(f"vendor-extension disagreements in listed maps: {len(extensions)}")
    for line in variants + extensions:
        print("  disagreement: " + line)
    print(f"symbols counted, not deciding: {symbols_total}; codes the codec cannot decode: {skipped_total}")
    print(f"maps with no covering codec (decoded and chain-checked by the crate test only): {len(structural_maps)}")
    for name, count in structural_maps:
        print(f"  structural: {name} ({count} samples)")
    for name, verified, symbols, skipped in oracle_maps:
        print(f"  checked: {name}: {verified} verified, {symbols} symbols, {skipped} undecodable")
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for failure in failures:
            print("  " + failure)
        return 1
    print("OK: no mismatch")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
