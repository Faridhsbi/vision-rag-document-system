from app.rag.parser import make_document_id, table_to_markdown


def test_make_document_id_is_stable_slug():
    assert (
        make_document_id("Laporan Keuangan Bank Mandiri 2025.pdf")
        == "laporan_keuangan_bank_mandiri_2025"
    )


def test_table_to_markdown_preserves_rows_and_columns():
    table = [
        ["Sektor", "Nominal", "Persentase"],
        ["Tambang", "11.614.853", "7,98%"],
        ["Konstruksi", "8.264.848", "8,27%"],
    ]

    markdown = table_to_markdown(table)

    assert "| Sektor | Nominal | Persentase |" in markdown
    assert "| Tambang | 11.614.853 | 7,98% |" in markdown
    assert "| Konstruksi | 8.264.848 | 8,27% |" in markdown

