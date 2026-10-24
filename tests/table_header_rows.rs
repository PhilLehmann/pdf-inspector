//! The tagged table model on the public `process_pdf_mem` surface.
//!
//! A table's header rows are the ones the document's structure tree declares
//! (`/TH` cells, or the cells of a row inside `/THead`). A row recovered from
//! text above a tagged table is reported as synthesized, never as declared.
//! A table detected from geometry alone (an untagged PDF) reports no header
//! rows at all: row 0 is never assumed.

use lopdf::{dictionary, Document, Object, ObjectId, Stream};
use pdf_inspector::structure_tree::StructTree;
use pdf_inspector::tables::{TableHeaderRow, TableHeaderSource};
use pdf_inspector::{process_pdf_mem, PdfProcessResult};

/// How the synthetic document describes its table.
#[derive(Clone, Copy, PartialEq, Eq)]
enum TableTags {
    /// Every header cell is a `/TH`.
    Th,
    /// The header row is a `/THead` group of `/TD` cells.
    THead,
    /// The table has a structure tree but no header cell at all; the header
    /// text sits above the table and can only be recovered from geometry.
    UntaggedHeaderRow,
    /// No structure tree: the table is found from its geometry alone.
    UntaggedDocument,
}

const HEADER: [&str; 3] = ["Region", "Sales", "Total"];
const COLUMNS: [f32; 3] = [72.0, 200.0, 330.0];
const ROWS: [f32; 3] = [700.0, 680.0, 660.0];

struct Cell {
    text: String,
    x: f32,
    y: f32,
}

fn tagged_cells() -> Vec<Cell> {
    // The third cell of the last row is absent, so the tagged table has a
    // ragged row. Header recovery only runs for a ragged table.
    let rows: [[&str; 3]; 3] = [
        ["Name", "Age", "City"],
        ["Alice", "30", "Berlin"],
        ["Bob", "25", ""],
    ];
    let mut cells = Vec::new();
    for (row, values) in rows.iter().enumerate() {
        for (column, text) in values.iter().enumerate() {
            if text.is_empty() {
                continue;
            }
            cells.push(Cell {
                text: (*text).to_string(),
                x: COLUMNS[column],
                y: ROWS[row],
            });
        }
    }
    cells
}

fn geometry_cells() -> Vec<Cell> {
    let mut cells = Vec::new();
    for (row, y) in [700.0, 680.0, 660.0, 640.0, 620.0].into_iter().enumerate() {
        for (column, x) in [60.0, 180.0, 300.0, 420.0].into_iter().enumerate() {
            cells.push(Cell {
                text: format!("{}{}", row + 1, column + 1),
                x,
                y,
            });
        }
    }
    cells
}

fn add_struct_elem(doc: &mut Document, role: &str, kids: Vec<Object>, page: ObjectId) -> ObjectId {
    doc.add_object(dictionary! {
        "Type" => "StructElem",
        "S" => role,
        "Pg" => Object::Reference(page),
        "K" => kids,
    })
}

fn build_pdf(tags: TableTags) -> Vec<u8> {
    let mut doc = Document::with_version("1.5");
    let pages_id = doc.new_object_id();
    let page_id = doc.new_object_id();
    let font_id = doc.new_object_id();
    let content_id = doc.new_object_id();

    let untagged = tags == TableTags::UntaggedDocument;
    let cells = if untagged {
        geometry_cells()
    } else {
        tagged_cells()
    };
    let mut content = String::new();
    // The unclaimed header text above the table, for the recovery case. It
    // carries no marked content, so it is not part of the structure tree.
    if tags == TableTags::UntaggedHeaderRow {
        for (index, text) in HEADER.iter().enumerate() {
            content.push_str(&format!(
                "BT /F1 10 Tf 1 0 0 1 {} 712 Tm ({text}) Tj ET\n",
                COLUMNS[index]
            ));
        }
    }
    for (index, cell) in cells.iter().enumerate() {
        content.push_str(&format!(
            "/P <</MCID {index}>> BDC\nBT /F1 10 Tf 1 0 0 1 {} {} Tm ({}) Tj ET\nEMC\n",
            cell.x, cell.y, cell.text
        ));
    }

    doc.objects.insert(
        content_id,
        Stream::new(dictionary! {}, content.into_bytes()).into(),
    );
    doc.objects.insert(
        font_id,
        dictionary! {
            "Type" => "Font",
            "Subtype" => "Type1",
            "BaseFont" => "Helvetica",
        }
        .into(),
    );
    doc.objects.insert(
        page_id,
        dictionary! {
            "Type" => "Page",
            "Parent" => pages_id,
            "MediaBox" => vec![0.into(), 0.into(), 612.into(), 792.into()],
            "Resources" => dictionary! {
                "Font" => dictionary! { "F1" => font_id },
            },
            "Contents" => content_id,
        }
        .into(),
    );
    doc.objects.insert(
        pages_id,
        dictionary! {
            "Type" => "Pages",
            "Kids" => vec![page_id.into()],
            "Count" => 1,
        }
        .into(),
    );
    let mut catalog = dictionary! { "Type" => "Catalog", "Pages" => pages_id };

    if !untagged {
        // Rows in document order. One object per cell, one per row, then the
        // table; the `/Pg` on the table is inherited by every row and cell.
        // MCIDs follow the content stream's row-major order, so tagged and
        // rendered cells line up.
        let mut mcid = 0i64;
        let mut rows: Vec<ObjectId> = Vec::new();
        for row in 0..3 {
            let mut cells_for_row = Vec::new();
            for column in 0..3 {
                let role = if tags == TableTags::Th && row == 0 {
                    "TH"
                } else {
                    "TD"
                };
                let kids = if row == 2 && column == 2 {
                    // The ragged row keeps a cell with no marked content.
                    Vec::new()
                } else {
                    let kid = vec![Object::Integer(mcid)];
                    mcid += 1;
                    kid
                };
                cells_for_row.push(Object::Reference(add_struct_elem(
                    &mut doc, role, kids, page_id,
                )));
            }
            rows.push(add_struct_elem(&mut doc, "TR", cells_for_row, page_id));
        }

        let kids: Vec<Object> = if tags == TableTags::THead {
            let thead =
                add_struct_elem(&mut doc, "THead", vec![Object::Reference(rows[0])], page_id);
            vec![
                Object::Reference(thead),
                Object::Reference(rows[1]),
                Object::Reference(rows[2]),
            ]
        } else {
            rows.iter().map(|&id| Object::Reference(id)).collect()
        };
        let table_id = add_struct_elem(&mut doc, "Table", kids, page_id);
        let root_id = doc.add_object(dictionary! {
            "Type" => "StructTreeRoot",
            "K" => vec![Object::Reference(table_id)],
        });
        catalog.set("StructTreeRoot", Object::Reference(root_id));
    }

    let catalog_id = doc.add_object(catalog);
    doc.trailer.set("Root", catalog_id);

    let mut bytes = Vec::new();
    doc.save_to(&mut bytes).unwrap();
    bytes
}

fn result(bytes: &[u8]) -> PdfProcessResult {
    process_pdf_mem(bytes).expect("the synthetic document processes")
}

fn header_rows(result: &PdfProcessResult) -> Vec<TableHeaderRow> {
    let mut rows: Vec<TableHeaderRow> = result
        .tables
        .iter()
        .flat_map(|page_table| page_table.table.header_rows.iter().copied())
        .collect();
    rows.sort_by_key(|row| row.row);
    rows
}

#[test]
fn a_tagged_table_reports_which_rows_are_header_rows() {
    let result = result(&build_pdf(TableTags::Th));
    assert_eq!(
        result.tables.len(),
        1,
        "one table on page 1; pages_with_tables={:?}",
        result.layout.pages_with_tables
    );
    assert_eq!(result.tables[0].page, 1);
    assert_eq!(
        result.tables[0].table.header_rows,
        vec![TableHeaderRow {
            row: 0,
            source: TableHeaderSource::Tagged,
        }]
    );
    assert_eq!(result.tables[0].table.cells[0], vec!["Name", "Age", "City"]);
}

#[test]
fn a_thead_row_is_a_tagged_header_row() {
    let result = result(&build_pdf(TableTags::THead));
    assert_eq!(result.tables.len(), 1);
    assert_eq!(
        result.tables[0].table.header_rows,
        vec![TableHeaderRow {
            row: 0,
            source: TableHeaderSource::Tagged,
        }]
    );
}

#[test]
fn a_synthesized_header_is_marked_synthesized() {
    let result = result(&build_pdf(TableTags::UntaggedHeaderRow));
    assert_eq!(result.tables.len(), 1);
    assert_eq!(
        result.tables[0].table.header_rows,
        vec![TableHeaderRow {
            row: 0,
            source: TableHeaderSource::Synthesized,
        }]
    );
    // The recovered header row is the page's own text above the table.
    assert_eq!(result.tables[0].table.cells[0], HEADER);
}

#[test]
fn an_untagged_table_reports_no_header_rows() {
    let bytes = build_pdf(TableTags::UntaggedDocument);
    let doc = Document::load_mem(&bytes).expect("the synthetic document loads");
    assert!(
        StructTree::from_doc(&doc).is_none(),
        "the fixture must have no structure tree"
    );

    let result = result(&bytes);
    assert!(
        !result.tables.is_empty(),
        "the geometry-only table must be detected; pages_with_tables={:?}",
        result.layout.pages_with_tables
    );
    for page_table in &result.tables {
        assert!(
            page_table.table.header_rows.is_empty(),
            "page {}: geometry invented a header: {:?}",
            page_table.page,
            page_table.table.header_rows
        );
    }
    assert!(header_rows(&result).is_empty());
}
