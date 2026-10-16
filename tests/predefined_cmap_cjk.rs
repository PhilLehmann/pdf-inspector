//! Kivadis qualification (not from an upstream pull request): CJK text that can only be read through the
//! built-in CMaps. Each fixture (`scripts/make_cjk_fixtures.py`) has a Type0 font over a non-embedded CID
//! font: either `Identity-H` with no /ToUnicode (read through `Adobe-<ordering>-UCS2`) or a predefined
//! Encoding CMap with a one-entry /ToUnicode (read through the built-in Encoding CMap, then the UCS2 map).

use pdf_inspector::{extract_text_with_positions_mem, process_pdf_mem};

fn read(name: &str) -> Vec<u8> {
    std::fs::read(format!(
        "{}/tests/fixtures/{name}",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap_or_else(|err| panic!("{name}: {err}"))
}

/// The text of every positioned item of the document, joined.
fn text_of(name: &str) -> String {
    extract_text_with_positions_mem(&read(name))
        .unwrap_or_else(|err| panic!("{name}: {err:?}"))
        .into_iter()
        .map(|item| item.text)
        .collect::<Vec<_>>()
        .join("")
}

/// Letters only: the fixtures show their text without depending on how spaces are rebuilt.
fn compact(text: &str) -> String {
    text.chars().filter(|c| !c.is_whitespace()).collect()
}

const FIXTURES: [(&str, &str); 9] = [
    ("cjk_japan1_identity_h.pdf", "ABCあん亜日本語"),
    ("cjk_gb1_identity_h.pdf", "中文测试一二三"),
    ("cjk_cns1_identity_h.pdf", "繁體中文測試"),
    ("cjk_korea1_identity_h.pdf", "한국어테스트"),
    ("cjk_japan1_90ms_rksj.pdf", "あいう日本語"),
    ("cjk_japan1_unijis_ucs2.pdf", "日本語のテキスト"),
    ("cjk_gb1_gbk_euc.pdf", "中文测试一二三"),
    ("cjk_cns1_eten_b5.pdf", "繁體中文測試"),
    ("cjk_korea1_kscms_uhc.pdf", "한국어테스트"),
];

/// Every fixture that does not read as its text, with what it read as.
fn misreads(read_as: impl Fn(&str) -> String) -> Vec<String> {
    FIXTURES
        .iter()
        .filter_map(|(name, expected)| {
            let got = compact(&read_as(name));
            (got != *expected).then(|| format!("{name}: {got:?}, expected {expected:?}"))
        })
        .collect()
}

#[test]
fn predefined_cmap_cjk_fixtures_read_as_their_text() {
    let misread = misreads(text_of);
    assert!(misread.is_empty(), "{misread:#?}");
}

#[test]
fn predefined_cmap_cjk_fixtures_reach_the_markdown() {
    let misread = misreads(|name| {
        process_pdf_mem(&read(name))
            .unwrap_or_else(|err| panic!("{name}: {err:?}"))
            .markdown
            .unwrap_or_default()
            .replace("## ", "")
    });
    assert!(misread.is_empty(), "{misread:#?}");
}
